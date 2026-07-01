"""Backfill missing horse_links verified records using race_program_entries."""
import argparse
import sys
import sqlite3
import json
from datetime import datetime
from pathlib import Path

from app_config import DB_PATH
from pedigreeall_core import connect, now, canonical


def backfill_links(db_path: str | Path, target_date: str | None = None):
    print(f"Connecting to database: {db_path}")
    conn = connect(db_path)
    try:
        # Check if table horse_mapping exists
        mapping_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='horse_mapping'"
        ).fetchone() is not None

        # Build date condition
        query_params = []
        date_where = ""
        if target_date:
            date_where = "WHERE program_date = ?"
            query_params.append(target_date)

        # 1. Fetch candidates from race_program_entries
        # We need horse_id, horse_name, and tjk_id
        candidates_query = f"""
            SELECT horse_id, horse_name, tjk_id, program_date 
            FROM race_program_entries
            {date_where}
        """
        raw_rows = conn.execute(candidates_query, query_params).fetchall()

        # Statistics
        inserted_count = 0
        skipped_existing_count = 0
        conflict_count = 0
        missing_count = 0

        # Group candidates by horse_id
        horse_groups = {}
        for r in raw_rows:
            h_id = r["horse_id"]
            h_name = r["horse_name"]
            t_id = r["tjk_id"]
            if not t_id or t_id == '0' or t_id == '':
                missing_count += 1
                continue
            if not h_id:
                missing_count += 1
                continue

            horse_groups.setdefault(h_id, []).append((h_name, t_id))

        # Check existing verified links in horse_links
        existing_links = {}  # horse_id -> tjk_id
        existing_tjk_links = {}  # tjk_id -> horse_id
        for row in conn.execute("SELECT tjk_id, horse_id FROM horse_links WHERE verified = 1"):
            existing_links[row["horse_id"]] = str(row["tjk_id"])
            existing_tjk_links[str(row["tjk_id"])] = row["horse_id"]

        # Loop through each horse_id and analyze mappings
        with conn:
            for h_id, mappings in horse_groups.items():
                # Get unique tjk_ids for this horse_id in program entries
                unique_tjk_ids = sorted(list({str(m[1]) for m in mappings}))
                h_name = mappings[0][0]

                if len(unique_tjk_ids) > 1:
                    # Conflict: horse_id mapped to multiple different tjk_ids in program
                    print(f"Conflict: horse_id={h_id} ({h_name}) is mapped to multiple TJK IDs in program: {unique_tjk_ids}")
                    conflict_count += 1
                    continue

                target_tjk_id = unique_tjk_ids[0]

                # Check if this horse_id is already mapped in existing_links
                existing_tjk = existing_links.get(h_id)
                if existing_tjk:
                    if existing_tjk == target_tjk_id:
                        skipped_existing_count += 1
                        continue
                    else:
                        # Conflict: mapped to a different TJK ID in horse_links
                        print(f"Conflict: horse_id={h_id} ({h_name}) already mapped to TJK ID {existing_tjk} in horse_links, program has {target_tjk_id}")
                        conflict_count += 1
                        continue

                # Check if target_tjk_id is already mapped to a different horse_id in existing_tjk_links
                existing_horse = existing_tjk_links.get(target_tjk_id)
                if existing_horse and existing_horse != h_id:
                    # Conflict: TJK ID already mapped to a different horse_id
                    print(f"Conflict: TJK ID {target_tjk_id} already mapped to horse_id {existing_horse} in horse_links, program has {h_id} ({h_name})")
                    conflict_count += 1
                    continue

                # Perform backfill insert/update
                evidence = canonical({"source": "backfill_tjk_links_from_program", "horse_name": h_name})
                stamp = now()

                # Insert/replace into horse_links
                conn.execute(
                    """INSERT OR REPLACE INTO horse_links(
                           tjk_id, horse_id, match_method, confidence, evidence_json, verified, updated_at
                       ) VALUES(?, ?, 'backfill_program', 1.0, ?, 1, ?)""",
                    (target_tjk_id, h_id, evidence, stamp)
                )

                if mapping_exists:
                    # Insert/replace into horse_mapping
                    conn.execute(
                        """INSERT OR REPLACE INTO horse_mapping(
                               tjk_id, horse_id, source_name, api_name, match_method, confidence, verified, updated_at
                           ) VALUES(?, ?, ?, ?, 'backfill_program', 1.0, 1, ?)""",
                        (target_tjk_id, h_id, h_name, h_name, stamp)
                    )

                print(f"Successfully backfilled horse_id={h_id} ({h_name}) -> TJK ID {target_tjk_id}")
                inserted_count += 1

                # Update in-memory dicts to detect conflicts in subsequent iterations
                existing_links[h_id] = target_tjk_id
                existing_tjk_links[target_tjk_id] = h_id

        # Print report
        report = {
            "inserted_count": inserted_count,
            "skipped_existing_count": skipped_existing_count,
            "conflict_count": conflict_count,
            "missing_count": missing_count
        }
        print("\n--- Backfill Statistics Report ---")
        print(json.dumps(report, indent=2))
        return report

    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="Program date in YYYY-MM-DD format")
    args = parser.parse_args()

    backfill_links(DB_PATH, args.date)
