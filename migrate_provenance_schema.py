"""Apply provenance schema migrations exactly once per database."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app_config import DB_PATH, MIGRATIONS_DIR

ROOT = Path(__file__).resolve().parent
MIGRATIONS = MIGRATIONS_DIR


def apply_migrations(db_path: str | Path = DB_PATH) -> list[str]:
    applied_now: list[str] = []
    connection = sqlite3.connect(str(db_path), timeout=60)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations(
                   migration_name TEXT PRIMARY KEY,
                   applied_at TEXT NOT NULL
               )"""
        )
        applied = {row[0] for row in connection.execute("SELECT migration_name FROM schema_migrations")}
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name in applied:
                continue
            connection.executescript(path.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations VALUES(?, ?)",
                (path.name, datetime.now(timezone.utc).isoformat()),
            )
            connection.commit()
            applied_now.append(path.name)
    finally:
        connection.close()
    return applied_now


if __name__ == "__main__":
    print({"applied": apply_migrations()})
