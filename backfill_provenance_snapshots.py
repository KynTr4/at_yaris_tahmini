"""Backfill snapshots only from raw captures that already contain real fetched_at."""
from snapshot_store import backfill_program_captures_from_raw
from app_config import DB_PATH

if __name__ == "__main__":
    print(backfill_program_captures_from_raw(DB_PATH))
