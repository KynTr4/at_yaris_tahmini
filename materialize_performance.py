"""Materialize the performance_evaluated table for fast API reads.

Run this script after update_results.py finishes so that race outcome data is
present before the snapshot is taken.  It performs a full DELETE + INSERT in a
single IMMEDIATE transaction, ensuring readers always see a consistent view of
the table — never a partial update.

Typical invocation (daily cron / pipeline step):
    python materialize_performance.py

Output: a single JSON object on stdout with status, row counts, and timing.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
import traceback
from datetime import datetime, timezone

from app_config import DB_PATH, LOG_DIR, PROJECT_ROOT  # noqa: F401 — kept for callers
from migrate_provenance_schema import apply_migrations
from performance_queries import PERFORMANCE_CTE
from race_scope import configure_sqlite

# ---------------------------------------------------------------------------
# INSERT statement: a single WITH ... INSERT INTO ... SELECT compound statement
# supported by SQLite ≥ 3.35.  PERFORMANCE_CTE supplies the full CTE preamble
# (ending with the closing parenthesis of the `evaluated` CTE); we append the
# INSERT directly so that the whole string is one valid SQL statement.
# ---------------------------------------------------------------------------
INSERT_SQL = (
    PERFORMANCE_CTE
    + """
INSERT INTO performance_evaluated (
    prediction_id, race_id, prediction_time, race_start_at, model, model_version,
    probability, predicted_horse_id, predicted_horse, winner_name, winner_ids,
    city, race_no, race_class, surface, distance, race_date, race_time,
    correct, decimal_odds, winner_decimal_odds, net_return, materialized_at
)
SELECT prediction_id, race_id, prediction_time, race_start_at, model, model_version,
       probability, predicted_horse_id, predicted_horse, winner_name, winner_ids,
       city, race_no, race_class, surface, distance, race_date, race_time,
       correct, decimal_odds, winner_decimal_odds, net_return, datetime('now')
FROM evaluated
"""
)


def materialize(db_path=DB_PATH) -> dict:
    """Rebuild performance_evaluated from scratch in a single atomic transaction.

    Returns a dict with keys: status, rows_before, rows_after, elapsed_ms,
    materialized_at.  Raises on any database error after attempting a ROLLBACK.
    """
    # Ensure migration 016 (and any earlier pending migrations) are applied
    # before we try to reference the table.
    apply_migrations(db_path)

    conn = sqlite3.connect(str(db_path), timeout=60)
    conn.row_factory = sqlite3.Row
    configure_sqlite(conn)
    try:
        # Switch to WAL mode for better read/write concurrency; no-op if
        # already set — the pragma just returns the current journal mode.
        conn.execute("PRAGMA journal_mode=WAL")

        before_count = conn.execute(
            "SELECT COUNT(*) FROM performance_evaluated"
        ).fetchone()[0]

        t0 = time.perf_counter()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM performance_evaluated")
            conn.execute(INSERT_SQL)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

        after_count = conn.execute(
            "SELECT COUNT(*) FROM performance_evaluated"
        ).fetchone()[0]
        elapsed_ms = (time.perf_counter() - t0) * 1000

        return {
            "status": "ok",
            "rows_before": before_count,
            "rows_after": after_count,
            "elapsed_ms": round(elapsed_ms, 1),
            "materialized_at": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        conn.close()


def main() -> int:
    try:
        result = materialize()
        print(json.dumps(result))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
