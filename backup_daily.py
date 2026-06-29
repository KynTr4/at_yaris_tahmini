"""SQLite-consistent tar.gz backup with daily/weekly/monthly retention."""
from __future__ import annotations

import shutil
import sqlite3
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

from app_config import BACKUP_DIR, DB_PATH, MODELS_DIR, OUTPUT_DIR, PROJECT_ROOT, REPORTS_DIR, ensure_runtime_dirs


def prune(folder: Path, keep: int) -> None:
    files = sorted(folder.glob("*.tar.gz"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in files[keep:]:
        path.unlink()


def create_backup(now: datetime | None = None) -> Path:
    ensure_runtime_dirs(); now = now or datetime.now()
    daily = BACKUP_DIR / "daily"; weekly = BACKUP_DIR / "weekly"; monthly = BACKUP_DIR / "monthly"
    for folder in (daily, weekly, monthly):
        folder.mkdir(parents=True, exist_ok=True)
    name = f"at_yaris_{now:%Y%m%d_%H%M%S}.tar.gz"
    destination = daily / name
    with tempfile.TemporaryDirectory(dir=BACKUP_DIR) as temporary:
        stage = Path(temporary) / "at_yaris_tahmini"; stage.mkdir()
        source = sqlite3.connect(str(DB_PATH), timeout=60)
        target = sqlite3.connect(str(stage / DB_PATH.name))
        try:
            source.backup(target)
        finally:
            target.close(); source.close()
        for folder in (OUTPUT_DIR, REPORTS_DIR, MODELS_DIR):
            if folder.exists():
                shutil.copytree(folder, stage / folder.name)
        env_example = PROJECT_ROOT / ".env.example"
        if env_example.exists():
            shutil.copy2(env_example, stage / env_example.name)
        with tarfile.open(destination, "w:gz") as archive:
            archive.add(stage, arcname=stage.name)
    if now.weekday() == 6:
        shutil.copy2(destination, weekly / name)
    if now.day == 1:
        shutil.copy2(destination, monthly / name)
    prune(daily, 14); prune(weekly, 8); prune(monthly, 6)
    return destination


if __name__ == "__main__":
    print(create_backup())
