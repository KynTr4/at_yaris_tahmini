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
    from pedigreeall_core import resolve_tjk_id
    res = resolve_tjk_id(connection, horse_id)
    return res["tjk_id"]


def build_results_coverage(connection: sqlite3.Connection, target_date: str, country: str = "ALL") -> dict[str, Any]:
    from pedigreeall_core import resolve_tjk_id
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
    
    # Check if errors table exists
    errors_table_exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='errors'"
    ).fetchone() is not None

    # 1. Resolve TJK IDs for all horses first and map each horse_id to its resolved TJK info
    resolved_tjk_by_horse = {}
    for horse in programs:
        h_id = horse["horse_id"]
        h_name = horse["horse_name"]
        resolved_tjk_by_horse[h_id] = resolve_tjk_id(connection, h_id, h_name, target_date)

    # 2. Bulk load all errors for target_date to avoid querying in a loop
    errors_by_entity = {}
    if errors_table_exists:
        err_rows = connection.execute(
            """SELECT entity_key, error_type, message FROM errors 
               WHERE date(created_at) = ? 
               ORDER BY id ASC""",
            (target_date,)
        ).fetchall()
        for row in err_rows:
            errors_by_entity[row["entity_key"]] = (row["error_type"], row["message"])

    # 3. Precalculate program distinct race counts in Python
    # Map horse key -> set of race_ids
    horse_races_map = {}
    for horse in programs:
        r_id = horse["race_id"]
        curr_h_id = str(horse["horse_id"])
        curr_tjk_id = resolved_tjk_by_horse[horse["horse_id"]]["tjk_id"]
        
        horse_races_map.setdefault(curr_h_id, set()).add(r_id)
        if curr_tjk_id:
            horse_races_map.setdefault(f"tjk:{curr_tjk_id}", set()).add(r_id)

    # 4. Bulk load run counts from horse_races table
    races_by_horse = {}
    race_rows = connection.execute(
        """SELECT horse_key, COUNT(*) as cnt FROM horse_races 
           WHERE race_date = ? 
           GROUP BY horse_key""",
        (target_dot,)
    ).fetchall()
    for row in race_rows:
        races_by_horse[row["horse_key"]] = row["cnt"]

    missing_horses = []
    horse_reasons = {}
    
    for horse in programs:
        r_id = horse["race_id"]
        h_id = horse["horse_id"]
        h_name = horse["horse_name"]
        track_raw = horse["track"]
        track_cleaned = clean_track(track_raw)
        policy = track_policy(track_cleaned)
        
        # Resolve TJK ID from precalculated map
        res = resolved_tjk_by_horse[h_id]
        tjk_id = res["tjk_id"]
        
        captured = r_id in result_races
        
        if captured:
            reason = "RESULT_CAPTURED"
        elif policy == "unsupported":
            reason = "SOURCE_UNSUPPORTED"
        elif not tjk_id:
            reason = "TJK_ID_MISSING"
        else:
            # Check for API/DB errors using precalculated map
            err_row = None
            entity_key_1 = f"horse:{h_id}" if not str(h_id).startswith("horse:") and not str(h_id).startswith("tjk:") else str(h_id)
            entity_key_2 = f"tjk:{tjk_id}"
            
            if entity_key_1 in errors_by_entity:
                err_row = errors_by_entity[entity_key_1]
            elif entity_key_2 in errors_by_entity:
                err_row = errors_by_entity[entity_key_2]
                
            if err_row:
                err_type, err_msg = err_row[0], err_row[1]
                if any(k in err_type.lower() or k in err_msg.lower() for k in ("sqlite", "write", "database", "normalization")):
                    reason = "DB_WRITE_ERROR"
                else:
                    reason = "API_ERROR"
            else:
                entity_key = entity_key_1
                published = (entity_key in published_entities) or (entity_key_2 in published_entities)
                
                if not published:
                    reason = "PROVIDER_RESULT_NOT_PUBLISHED"
                else:
                    # prog_count from in-memory set
                    prog_count_set = set()
                    if entity_key in horse_races_map:
                        prog_count_set.update(horse_races_map[entity_key])
                    if entity_key_2 in horse_races_map:
                        prog_count_set.update(horse_races_map[entity_key_2])
                    prog_count = len(prog_count_set)
                    
                    # res_count from precalculated map
                    res_count = races_by_horse.get(entity_key, 0) + (races_by_horse.get(entity_key_2, 0) if entity_key_2 != entity_key else 0)
                    
                    if prog_count > 1 or res_count > 1:
                        reason = "AMBIGUOUS_PROGRAM_MATCH"
                    else:
                        reason = "DATA_MISSING"
                        
        horse_reasons[(r_id, h_id)] = reason
        
        if not captured:
            missing_horses.append({
                "horse_name": h_name,
                "horse_id": str(h_id),
                "race_id": r_id,
                "track": track_cleaned,
                "race_no": horse["race_no"],
                "missing_reason": reason,
                "resolved_tjk_id": tjk_id,
                "tjk_id_source": res["source_table"],
                "resolver_reason": res["reason"]
            })

    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in programs:
        grouped.setdefault(row["race_id"], []).append(row)
        
    race_rows = []
    for race_id, horses in grouped.items():
        raw_track = horses[0]["track"]
        track = clean_track(raw_track)
        policy = track_policy(track)
        fetched = race_id in result_races
        missing_tjk = 0
        source_not_published = 0
        
        race_horse_reasons = []
        for horse in horses:
            reason = horse_reasons.get((race_id, horse["horse_id"]), "DATA_MISSING")
            race_horse_reasons.append(reason)
            if reason == "TJK_ID_MISSING":
                missing_tjk += 1
            elif reason == "PROVIDER_RESULT_NOT_PUBLISHED":
                source_not_published += 1
                
        if fetched:
            reason, status = "RESULT_CAPTURED", "Sonuç çekildi"
        else:
            non_captured_reasons = sorted({r for r in race_horse_reasons if r != "RESULT_CAPTURED"})
            if not non_captured_reasons:
                reason = "DATA_MISSING"
            else:
                reason = ",".join(non_captured_reasons)
                
            status_map = {
                "TJK_ID_MISSING": "TJK ID eksik",
                "SOURCE_UNSUPPORTED": "Kaynak desteklenmiyor",
                "PROVIDER_RESULT_NOT_PUBLISHED": "Sonuç bekleniyor (Yayınlanmadı)",
                "AMBIGUOUS_PROGRAM_MATCH": "Program eşleşme karmaşası",
                "DATA_MISSING": "Veri eksik",
                "API_ERROR": "API hatası",
                "DB_WRITE_ERROR": "Veritabanı yazma hatası",
            }
            priority_order = [
                "SOURCE_UNSUPPORTED", "TJK_ID_MISSING", "DB_WRITE_ERROR",
                "API_ERROR", "AMBIGUOUS_PROGRAM_MATCH", "PROVIDER_RESULT_NOT_PUBLISHED", "DATA_MISSING"
            ]
            status_reason = "DATA_MISSING"
            for p in priority_order:
                if p in non_captured_reasons:
                    status_reason = p
                    break
            status = status_map.get(status_reason, "Sonuç bekleniyor")

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
        reasons = set()
        for r in race_rows:
            if r["track"] == track and not r["result_fetched"]:
                for sub_reason in r["missing_reason"].split(","):
                    if sub_reason and sub_reason != "RESULT_CAPTURED":
                        reasons.add(sub_reason)
        row["missing_reason"] = ",".join(sorted(reasons)) if reasons else "NONE"
        
    return {
        "date": target_date, "generated_at": datetime.now(timezone.utc).isoformat(),
        "tracks": sorted(tracks.values(), key=lambda row: (row["track_policy"] != "mandatory", row["track"])),
        "races": race_rows,
        "missing_horses": missing_horses,
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
    
    lines += ["", "## Missing horses detail", "",
              "| Horse Name | Horse ID | Race ID | Track | Race No | Missing Reason | Resolved TJK ID | TJK ID Source | Resolver Reason |",
              "| --- | --- | --- | --- | ---: | --- | --- | --- | --- |"]
    for h in coverage.get("missing_horses", []):
        lines.append(
            f"| {h['horse_name']} | {h['horse_id']} | {h['race_id']} | {h['track']} | {h['race_no']} | "
            f"{h['missing_reason']} | {h['resolved_tjk_id'] or ''} | {h['tjk_id_source'] or ''} | {h['resolver_reason'] or ''} |"
        )
        
    report_text = "\n".join(lines)
    (reports / "results_coverage_latest.md").write_text(report_text, encoding="utf-8")
    (reports / f"results_coverage_{target_date}.md").write_text(report_text, encoding="utf-8")
    return coverage


if __name__ == "__main__":
    import argparse
    from app_config import DB_PATH, OUTPUT_DIR, REPORTS_DIR
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="Date in YYYY-MM-DD format", required=True)
    args = parser.parse_args()
    
    write_results_coverage(DB_PATH, args.date, OUTPUT_DIR, REPORTS_DIR)
    print(f"Generated results coverage for {args.date}")

