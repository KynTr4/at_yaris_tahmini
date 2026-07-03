"""Fetch and import TJK daily race results from the TJK CDN.

Bypasses the GET:Tjk/Get HORSE_TABLE latency by reading results directly from
TJK's official daily CSV exports hosted at medya-cdn.tjk.org.

URL pattern:
  https://medya-cdn.tjk.org/raporftp/TJKPDF/{YEAR}/{YYYY-MM-DD}/CSV/
      GunlukYarisSonuclari/{DD.MM.YYYY}-{City}-GunlukYarisSonuclari-TR.csv

Usage – fetch from web (recommended):
    python import_race_results_csv.py --date 2026-07-03
    python import_race_results_csv.py --today
    python import_race_results_csv.py --date 2026-07-03 --cities Bursa Istanbul

Usage – import local CSV files:
    python import_race_results_csv.py file1.csv file2.csv
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sqlite3
import sys
import unicodedata
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from app_config import DB_PATH
from migrate_provenance_schema import apply_migrations
from race_scope import clean_track, fold

# ---------------------------------------------------------------------------
# TJK CDN fetcher
# ---------------------------------------------------------------------------

CDN_BASE = (
    "https://medya-cdn.tjk.org/raporftp/TJKPDF"
    "/{year}/{iso_date}/CSV/GunlukYarisSonuclari"
    "/{dot_date}-{city}-GunlukYarisSonuclari-TR.csv"
)

# Map of clean_track() output → CDN city name variants to try
_CITY_ALIASES: dict[str, list[str]] = {
    "ISTANBUL": ["\u0130stanbul", "Istanbul"],
    "IZMIR": ["\u0130zmir", "Izmir"],
    "ANKARA": ["Ankara"],
    "BURSA": ["Bursa"],
    "ADANA": ["Adana"],
    "ANTALYA": ["Antalya"],
    "DIYARBAKIR": ["Diyarbak\u0131r", "Diyarbakir"],
    "ELAZIG": ["Elaz\u0131\u011f", "Elazig"],
    "KOCAELI": ["Kocaeli"],
    "SANLIURFA": ["\u015eanl\u0131urfa", "Sanliurfa"],
}


def _cdn_url(race_date: date, city_cdn: str) -> str:
    return CDN_BASE.format(
        year=race_date.year,
        iso_date=race_date.strftime("%Y-%m-%d"),
        dot_date=race_date.strftime("%d.%m.%Y"),
        city=city_cdn,
    )


def fetch_csv_from_cdn(race_date: date, city_clean: str) -> str | None:
    """Try fetching CSV for the given city from TJK CDN.

    `city_clean` is the output of fold(clean_track(raw_city_name)), e.g. 'ISTANBUL'.
    Returns CSV text on success, None if not found.
    """
    aliases = _CITY_ALIASES.get(city_clean, [city_clean.title()])
    for alias in aliases:
        # Try raw unicode first, then percent-encoded
        encoded = urllib.parse.quote(alias, safe="")
        candidates = [encoded] if alias == encoded else [encoded, alias]
        for city_variant in candidates:
            url = _cdn_url(race_date, city_variant)
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 AtYarisTahmini/1.0"},
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    raw = resp.read()
                for enc in ("utf-8-sig", "utf-8", "cp1254", "latin-1"):
                    try:
                        return raw.decode(enc)
                    except UnicodeDecodeError:
                        continue
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    continue
                raise
            except Exception:
                continue
    return None


def domestic_cities_for_date(
    db_path: Path | str, target_date: str
) -> list[tuple[str, str]]:
    """Return [(clean_track_key, raw_city_name), ...] for supported domestic tracks."""
    from results_coverage import track_policy

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT DISTINCT city_name FROM race_program_entries WHERE program_date=?",
        (target_date,),
    ).fetchall()
    conn.close()
    result = []
    seen: set[str] = set()
    for row in rows:
        raw = row["city_name"] or ""
        cleaned = clean_track(raw)
        key = fold(cleaned)
        policy = track_policy(cleaned)
        if policy == "unsupported" or key in seen:
            continue
        seen.add(key)
        result.append((key, cleaned))
    return result


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


def import_csv_text(
    csv_text: str,
    label: str,
    db_path: Path,
    target_date: str,
    dry_run: bool = False,
) -> dict[str, int]:
    """Import race results from CSV text (already decoded string)."""
    apply_migrations(db_path)
    conn = sqlite3.connect(str(db_path), timeout=60)
    conn.row_factory = sqlite3.Row

    # write to a temp path so parse_csv can work
    import os
    import tempfile

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="utf-8"
    )
    tmp.write(csv_text)
    tmp.close()
    try:
        races = parse_csv(Path(tmp.name))
    finally:
        os.unlink(tmp.name)

    return _do_import(races, label, conn, target_date, dry_run)


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
    return _do_import(races, csv_path.name, conn, target_date, dry_run)


def _do_import(
    races: list[dict],
    label: str,
    conn: sqlite3.Connection,
    target_date: str,
    dry_run: bool = False,
) -> dict[str, int]:
    index = build_snapshot_index(conn, target_date)

    stats = {
        "matched": 0,
        "inserted": 0,
        "skipped_exists": 0,
        "no_match": 0,
        "no_program": 0,
    }
    captured_at = datetime.now(timezone.utc).isoformat()
    source_req = (
        "csv:" + hashlib.sha256(f"{label}:{captured_at}".encode()).hexdigest()[:40]
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


def _accumulate(total: dict, stats: dict) -> None:
    for k, v in stats.items():
        total[k] = total.get(k, 0) + v


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    # --- web fetch mode ---
    parser.add_argument(
        "--today", action="store_true", help="Fetch today's results from TJK CDN"
    )
    parser.add_argument("--date", default=None, help="Race date YYYY-MM-DD")
    parser.add_argument(
        "--cities",
        nargs="+",
        default=None,
        help="City names to fetch (e.g. Bursa Istanbul). Defaults to all domestic tracks.",
    )
    # --- local file mode ---
    parser.add_argument("csvfiles", nargs="*", help="Local TJK CSV result file(s)")
    # --- common ---
    parser.add_argument("--db", default=str(DB_PATH), help="SQLite DB path")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db_path = Path(args.db)
    total: dict[str, int] = {}

    # ── Mode A: fetch from TJK CDN ──────────────────────────────────────────
    if args.today or (args.date and not args.csvfiles):
        if args.today and not args.date:
            race_date = date.today()
        else:
            race_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        target_date = race_date.isoformat()

        if args.cities:
            # user-supplied cities → convert to fold keys
            cities = [(fold(clean_track(c)), c) for c in args.cities]
        else:
            # auto-detect from program entries
            cities = domestic_cities_for_date(db_path, target_date)
            if not cities:
                print(
                    f"No domestic tracks found in program for {target_date}.",
                    file=sys.stderr,
                )
                return 1

        print(f"Fetching TJK CDN results for {target_date} — {[c for _, c in cities]}")
        for city_key, city_label in cities:
            print(f"  [{city_label}] ", end="", flush=True)
            csv_text = fetch_csv_from_cdn(race_date, city_key)
            if csv_text is None:
                print("NOT FOUND (CDN 404 — results not published yet?)")
                continue
            stats = import_csv_text(
                csv_text, city_label, db_path, target_date, dry_run=args.dry_run
            )
            print(
                f"inserted={stats['inserted']}  skipped={stats['skipped_exists']}  "
                f"matched={stats['matched']}  no_match={stats['no_match']}"
            )
            _accumulate(total, stats)

    # ── Mode B: local CSV files ──────────────────────────────────────────────
    elif args.csvfiles:
        target_date = args.date or date.today().isoformat()
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
            _accumulate(total, stats)

    else:
        parser.print_help()
        return 1

    inserted = total.get("inserted", 0)
    matched = total.get("matched", 0)
    no_match = total.get("no_match", 0)
    print(f"\nTOPLAM: inserted={inserted}  matched={matched}  no_match={no_match}")
    if args.dry_run:
        print("(dry-run — hi\u00e7bir \u015fey yaz\u0131lmad\u0131)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
