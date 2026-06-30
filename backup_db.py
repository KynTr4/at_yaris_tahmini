"""Consistent SQLite database hot backup with daily/weekly/monthly retention."""
from __future__ import annotations

import gzip
import shutil
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

from app_config import BACKUP_DIR, DB_PATH, ensure_runtime_dirs


def prune(folder: Path, keep: int) -> None:
    files = sorted(folder.glob("*.db.gz"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in files[keep:]:
        try:
            path.unlink()
            print(f"Removed old database backup: {path.name}")
        except OSError as e:
            print(f"Failed to remove {path.name}: {e}")


def create_backup(now: datetime | None = None) -> Path:
    ensure_runtime_dirs()
    now = now or datetime.now()
    daily = BACKUP_DIR / "daily"
    weekly = BACKUP_DIR / "weekly"
    monthly = BACKUP_DIR / "monthly"
    
    for folder in (daily, weekly, monthly):
        folder.mkdir(parents=True, exist_ok=True)
        
    name = f"pedigreeall_progress_{now:%Y%m%d_%H%M%S}.db.gz"
    destination = daily / name
    
    # 1. Hot backup to a temporary .db file
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_db_path = Path(temp_dir) / "temp_backup.db"
        source = sqlite3.connect(str(DB_PATH), timeout=60)
        target = sqlite3.connect(str(temp_db_path))
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
            
        # 2. Compress the backup directly to destination
        with open(temp_db_path, "rb") as f_in:
            with gzip.open(destination, "wb", compresslevel=6) as f_out:
                shutil.copyfileobj(f_in, f_out)
                
    print(f"Database hot backup created successfully: {destination}")
    
    # 3. Handle Weekly and Monthly copies
    # Sunday is index 6 in weekday() (Mon=0, Sun=6)
    if now.weekday() == 6:
        shutil.copy2(destination, weekly / name)
        print(f"Copied backup to weekly folder: {weekly / name}")
    if now.day == 1:
        shutil.copy2(destination, monthly / name)
        print(f"Copied backup to monthly folder: {monthly / name}")
        
    # 4. Enforce retention limits
    prune(daily, 7)
    prune(weekly, 4)
    prune(monthly, 6)
    
    return destination


if __name__ == "__main__":
    create_backup()
