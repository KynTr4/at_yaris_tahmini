"""Read-only track/race result coverage diagnostics."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from race_scope import DOMESTIC_TRACKS, clean_track, fold, track_in_country

MANDATORY_TRACKS = {"ISTANBUL", "IZMIR"}


def track_policy(track: object) -> str:
    normalized = fold(clean_track(track))
    base = normalized.split()[0] if normalized else ""
    if base in MANDATORY_TRACKS:
        return "mandatory"
    if base in DOMESTIC_TRACKS:
        return "supported"
    return "unsupported"


def resolved_tjk_id(connection: sqlite3.Connection, horse_id: str) -> str | None:
    if horse_id.startswith("tjk:"):
        value = horse_id.split(":", 1)[1].strip()
        return value if value and value != "0" else None
    if horse_id.startswith("horse:"):
        value = horse_id.split(":", 1)[1]
        row = connection.execute(
            "SELECT tjk_id FROM horse_links WHERE CAST(horse_id AS TEXT)=? AND verified=1 LIMIT 1",
            (value,),
        ).fetchone()
        if row and row[0] not in (None, "", 0, "0"):
            return str(row[0])
    return None


def build_results_coverage(connection: sqlite3.Connection, target_date: str, country: str = "ALL") -> dict[str, Any]:
    connection.row_factory = sqlite3.Row
    programs = connection.execute(
        """WITH ranked AS (
               SELECT *,ROW_NUMBER() OVER(
                   PARTITION BY race_id,horse_id ORDER BY captured_at DESC,snapshot_id DESC
               ) AS rn
               FROM program_snapshots
               WHERE date(race_start_at,'+3 hours')=?
           )
           SELECT race_id,horse_id,horse_name,race_no,race_start_at,track
           FROM ranked WHERE rn=1 ORDER BY race_start_at,race_no,horse_id""",
        (target_date,),
    ).fetchall()
    result_races = {
        row[0] for row in connection.execute(
            """SELECT DISTINCT race_id FROM race_results
               WHERE date(race_start_at,'+3 hours')=?
                 AND result_status='finished' AND finish_position=1""",
            (target_date,),
        )
    }
    target_dot = datetime.strptime(target_date, "%Y-%m-%d").strftime("%d.%m.%Y")
    published_entities = {
        row[0] for row in connection.execute(
            """SELECT DISTINCT horse_key FROM horse_races
               WHERE race_date=? AND finish IS NOT NULL
                 AND trim(CAST(finish AS TEXT)) NOT IN ('','not_available')""",
            (target_dot,),
        )
    }

    programs = [row for row in programs if track_in_country(row["track"], country)]
    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in programs:
        grouped.setdefault(row["race_id"], []).append(row)
    race_rows = []
    for race_id, horses in grouped.items():
        raw_track = horses[0]["track"]
        track = clean_track(raw_track); policy = track_policy(track)
        fetched = race_id in result_races
        missing_tjk = 0; source_not_published = 0
        for horse in horses:
            tjk_id = resolved_tjk_id(connection, str(horse["horse_id"]))
            if not tjk_id:
                missing_tjk += 1
            elif str(horse["horse_id"]) not in published_entities:
                source_not_published += 1
        if fetched:
            reason, status = "NONE", "Sonuç çekildi"
        elif policy == "unsupported":
            reason, status = "SOURCE_UNSUPPORTED", "Kaynak desteklenmiyor"
        elif missing_tjk:
            reason, status = "TJK_ID_MISSING", "TJK ID eksik"
        elif source_not_published:
            reason, status = "RESULT_NOT_PUBLISHED", "Sonuç bekleniyor"
        else:
            reason, status = "RESULT_MAPPING_PENDING", "Sonuç bekleniyor"
        race_rows.append({
            "race_id": race_id, "track": track, "track_policy": policy,
            "race_no": horses[0]["race_no"], "race_start_at": horses[0]["race_start_at"],
            "horse_count": len(horses), "result_fetched": fetched,
            "missing_reason": reason, "status": status,
            "tjk_id_missing_horse_count": missing_tjk if not fetched else 0,
            "source_not_published_count": source_not_published if not fetched else 0,
        })

    tracks: dict[str, dict[str, Any]] = {}
    for race in race_rows:
        row = tracks.setdefault(race["track"], {
            "track": race["track"], "track_policy": race["track_policy"],
            "program_races": 0, "result_races": 0, "missing_races": 0,
            "missing_reason": "NONE", "tjk_id_missing_horse_count": 0,
            "source_not_published_count": 0,
        })
        row["program_races"] += 1
        row["result_races"] += int(race["result_fetched"])
        row["missing_races"] += int(not race["result_fetched"])
        row["tjk_id_missing_horse_count"] += race["tjk_id_missing_horse_count"]
        row["source_not_published_count"] += race["source_not_published_count"]
    for track, row in tracks.items():
        reasons = sorted({r["missing_reason"] for r in race_rows if r["track"] == track and not r["result_fetched"]})
        row["missing_reason"] = ",".join(reasons) if reasons else "NONE"
    return {
        "date": target_date, "generated_at": datetime.now(timezone.utc).isoformat(),
        "tracks": sorted(tracks.values(), key=lambda row: (row["track_policy"] != "mandatory", row["track"])),
        "races": race_rows,
    }


def coverage_warnings(coverage: dict[str, Any]) -> list[str]:
    warnings = []
    for row in coverage.get("tracks", []):
        if not row.get("missing_races"):
            continue
        prefix = "mandatory_track_missing" if row.get("track_policy") == "mandatory" else "unsupported_track_pending" if row.get("track_policy") == "unsupported" else "track_missing"
        warnings.append(
            f"{prefix}: track={row['track']} missing_races={row['missing_races']} "
            f"reason={row['missing_reason']} tjk_id_missing_horses={row['tjk_id_missing_horse_count']} "
            f"source_not_published={row['source_not_published_count']}"
        )
    return warnings


def write_results_coverage(
    db_path: str | Path,
    target_date: str,
    output_dir: str | Path,
    reports_dir: str | Path,
) -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        connection.execute("PRAGMA query_only=ON")
        coverage = build_results_coverage(connection, target_date)
    finally:
        connection.close()
    output = Path(output_dir); reports = Path(reports_dir)
    output.mkdir(parents=True, exist_ok=True); reports.mkdir(parents=True, exist_ok=True)
    text = json.dumps(coverage, ensure_ascii=False, indent=2)
    (output / "results_coverage_latest.json").write_text(text, encoding="utf-8")
    (output / f"results_coverage_{target_date}.json").write_text(text, encoding="utf-8")
    lines = [
        "# Results Coverage", "", f"Date: {target_date}", "",
        "| Track | Policy | Program races | Result races | Missing races | Missing reason | Missing TJK horses | Source not published |",
        "| --- | --- | ---: | ---: | ---: | --- | ---: | ---: |",
    ]
    for row in coverage["tracks"]:
        lines.append(
            f"| {row['track']} | {row['track_policy']} | {row['program_races']} | {row['result_races']} | "
            f"{row['missing_races']} | {row['missing_reason']} | {row['tjk_id_missing_horse_count']} | "
            f"{row['source_not_published_count']} |"
        )
    lines += ["", "## Missing race detail", "", "```json", json.dumps(
        [row for row in coverage["races"] if not row["result_fetched"]], ensure_ascii=False, indent=2
    ), "```", ""]
    report_text = "\n".join(lines)
    (reports / "results_coverage_latest.md").write_text(report_text, encoding="utf-8")
    (reports / f"results_coverage_{target_date}.md").write_text(report_text, encoding="utf-8")
    return coverage
