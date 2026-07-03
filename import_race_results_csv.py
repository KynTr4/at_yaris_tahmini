"""Import TJK daily race results from CSV files directly into race_results.

Bypasses the GET:Tjk/Get HORSE_TABLE dependency when TJK API is slow to update.
Matches CSV horses to program_snapshots by track + race_no + normalized name.

Usage:
    python import_race_results_csv.py <file1.csv> [<file2.csv> ...]

Example:
    python import_race_results_csv.py \
        "03.07.2026-Bursa-GunlukYarisSonuclari-TR.csv" \
        "03.07.2026-Istanbul-GunlukYarisSonuclari-TR.csv"
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sqlite3
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app_config import DB_PATH
from migrate_provenance_schema import apply_migrations
from race_scope import clean_track, fold

SOURCE_ENDPOINT = "CSV:TJK/GunlukYarisSonuclari"


# ---------------------------------------------------------------------------
# Name normalisation
# ---------------------------------------------------------------------------

_SUFFIX_RE = re.compile(
    r"""(\s+(?:DB|SK|KG|SKG|SG|KGR|SGKR|ÖG|AP|K|G|E|A|D)\b)+\s*$""",
    re.IGNORECASE,
)


def strip_suffixes(name: str) -> str:
    """Remove TJK handicap / breeding codes appended to horse names."""
    return _SUFFIX_RE.sub("", name.strip()).strip()


def fold_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.upper().strip()


def name_key(name: str) -> str:
    return fold_name(strip_suffixes(name))


# ---------------------------------------------------------------------------
# CSV parser
# ---------------------------------------------------------------------------


def parse_csv(path: Path) -> list[dict[str, Any]]:
    """Return list of race dicts, each with a 'horses' list."""
    raw = path.read_bytes()
    # Strip BOM if present
    for enc in ("utf-8-sig", "utf-8", "cp1254", "latin-1"):
        try:
            content = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue

    # Extract track name from first line
    lines = content.splitlines()
    track_raw = lines[0].split(";")[0].strip() if lines else "?"

    races: list[dict] = []
    current_race: dict | None = None
    in_horses = False

    for line in lines:
        line = line.strip()
        if not line:
            in_horses = False
            continue

        # Race header: "1. Kosu :   13.30;..."  or "1. Kosu :  MENDIP KOŞUSU 17.45;..."
        m = re.match(
            r"(\d+)\.\s*Kosu\s*:\s*(?:[A-ZÇŞĞÜÖİa-zçşğüöı\s]+\s+)?(\d{1,2})[.:h](\d{2})",
            line,
            re.I,
        )
        if m:
            in_horses = False
            current_race = {
                "race_no": int(m.group(1)),
                "start_hhmm": f"{int(m.group(2)):02d}:{m.group(3)}",
                "track_raw": track_raw,
                "horses": [],
                "raw_header": line,
            }
            races.append(current_race)
            continue

        # Column header row
        if "At No" in line and "At İsmi" in line and current_race is not None:
            in_horses = True
            continue

        # Horse row
        if in_horses and current_race is not None:
            parts = [p.strip() for p in line.split(";")]
            # At No must be a plain integer (1..20)
            if not parts or not re.fullmatch(r"\d{1,2}", parts[0]):
                # Could be ganyan / other footer lines
                in_horses = False
                continue
            try:
                finish_pos = int(parts[0])
            except ValueError:
                continue

            horse_name_raw = parts[1] if len(parts) > 1 else ""
            # Skip "Koşmaz" entries
            if "koşmaz" in horse_name_raw.lower() or "kosmaz" in horse_name_raw.lower():
                continue

            derece = parts[12] if len(parts) > 12 else None
            ganyan = parts[13] if len(parts) > 13 else None

            current_race["horses"].append(
                {
                    "finish_position": finish_pos,
                    "horse_name_raw": horse_name_raw,
                    "horse_name_key": name_key(horse_name_raw),
                    "race_time": derece,
                    "result_odds": _parse_odds(ganyan),
                }
            )

    return races


def _parse_odds(value: str | None) -> float | None:
    if not value:
        return None
    m = re.search(r"([\d]+[.,][\d]+)", str(value))
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------------------
# DB matching & insertion
# ---------------------------------------------------------------------------


def build_snapshot_index(
    conn: sqlite3.Connection, target_date: str
) -> dict[tuple[str, int, str], dict]:
    """Build (track_key, race_no, name_key) → snapshot info index."""
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT DISTINCT race_id, horse_id, race_start_at, race_no, track, horse_name
           FROM program_snapshots
           WHERE substr(race_start_at, 1, 10) = ?""",
        (target_date,),
    ).fetchall()

    index: dict[tuple[str, int, str], dict] = {}
    for row in rows:
        t_key = fold(clean_track(row["track"]))
        r_no = row["race_no"] or 0
        h_key = name_key(row["horse_name"] or "")
        index[(t_key, r_no, h_key)] = dict(row)
    return index


def result_already_exists(
    conn: sqlite3.Connection, horse_id: str, target_date: str
) -> bool:
    return (
        conn.execute(
            """SELECT 1 FROM race_results
           WHERE horse_id=? AND date(race_start_at,'+3 hours')=?
             AND result_status='finished' AND finish_position IS NOT NULL
           LIMIT 1""",
            (horse_id, target_date),
        ).fetchone()
        is not None
    )


def import_csv(
    csv_path: Path,
    db_path: Path,
    target_date: str,
    dry_run: bool = False,
) -> dict[str, int]:
    apply_migrations(db_path)
    conn = sqlite3.connect(str(db_path), timeout=60)
    conn.row_factory = sqlite3.Row

    races = parse_csv(csv_path)
    index = build_snapshot_index(conn, target_date)

    stats = {
        "matched": 0,
        "inserted": 0,
        "skipped_exists": 0,
        "no_match": 0,
        "no_program": 0,
    }
    captured_at = datetime.now(timezone.utc).isoformat()
    # Unique synthetic source_request_id per CSV file import
    source_req = (
        "csv:"
        + hashlib.sha256(f"{csv_path.name}:{captured_at}".encode()).hexdigest()[:40]
    )

    for race in races:
        t_key = fold(clean_track(race["track_raw"]))
        r_no = race["race_no"]

        for horse in race["horses"]:
            h_key = horse["horse_name_key"]
            lookup = index.get((t_key, r_no, h_key))

            # Fuzzy fallback: try partial name match
            if lookup is None:
                for (tk, rn, nk), snap in index.items():
                    if (
                        tk == t_key
                        and rn == r_no
                        and (nk.startswith(h_key) or h_key.startswith(nk))
                    ):
                        lookup = snap
                        break

            if lookup is None:
                stats["no_match"] += 1
                print(
                    f"  NO_MATCH  race={r_no} horse={horse['horse_name_raw']!r} key={h_key!r}",
                    file=sys.stderr,
                )
                continue

            entity = lookup["horse_id"]
            race_id = lookup["race_id"]
            race_start_at = lookup["race_start_at"]

            stats["matched"] += 1

            if result_already_exists(conn, entity, target_date):
                stats["skipped_exists"] += 1
                continue

            if dry_run:
                print(
                    f"  DRY_RUN  race={r_no} pos={horse['finish_position']} "
                    f"horse={horse['horse_name_raw']!r} entity={entity} race_id={race_id}"
                )
                stats["inserted"] += 1
                continue

            cursor = conn.execute(
                """INSERT OR IGNORE INTO race_results(
                       race_id, horse_id, race_start_at, race_no, captured_at,
                       source_endpoint, source_request_id, finish_position, finish_time,
                       prize, margin, result_odds, result_status)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    race_id,
                    entity,
                    race_start_at,
                    r_no,
                    captured_at,
                    SOURCE_ENDPOINT,
                    source_req,
                    float(horse["finish_position"]),
                    horse["race_time"],
                    None,  # prize — not in CSV in a parseable form
                    None,  # margin
                    horse["result_odds"],
                    "finished",
                ),
            )
            if cursor.rowcount > 0:
                stats["inserted"] += 1

    if not dry_run:
        conn.commit()
    conn.close()
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csvfiles", nargs="+", help="TJK CSV result file(s)")
    parser.add_argument(
        "--date", default=None, help="Race date YYYY-MM-DD (default: today)"
    )
    parser.add_argument("--db", default=str(DB_PATH), help="SQLite DB path")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    target_date = args.date or datetime.now().strftime("%Y-%m-%d")
    db_path = Path(args.db)

    total = {
        "matched": 0,
        "inserted": 0,
        "skipped_exists": 0,
        "no_match": 0,
        "no_program": 0,
    }

    for csv_file in args.csvfiles:
        path = Path(csv_file)
        if not path.exists():
            print(f"FILE NOT FOUND: {path}", file=sys.stderr)
            continue
        print(f"\n=== {path.name} ===")
        stats = import_csv(path, db_path, target_date, dry_run=args.dry_run)
        print(
            f"  matched={stats['matched']}  inserted={stats['inserted']}  "
            f"skipped_exists={stats['skipped_exists']}  no_match={stats['no_match']}"
        )
        for k, v in stats.items():
            total[k] += v

    print(
        f"\nTOPLAM: inserted={total['inserted']} matched={total['matched']} no_match={total['no_match']}"
    )
    if args.dry_run:
        print("(dry-run — hiçbir şey yazılmadı)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
