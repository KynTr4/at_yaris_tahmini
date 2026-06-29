"""Cross-platform runtime configuration loaded from environment/.env."""
from __future__ import annotations

import os
from pathlib import Path


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


SOURCE_ROOT = Path(__file__).resolve().parent
_load_env_file(Path(os.environ.get("ENV_FILE", SOURCE_ROOT / ".env")))

PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", SOURCE_ROOT)).expanduser().resolve()
DB_PATH = Path(os.environ.get("DB_PATH", PROJECT_ROOT / "pedigreeall_progress.db")).expanduser().resolve()
LOG_DIR = Path(os.environ.get("LOG_DIR", PROJECT_ROOT / "logs")).expanduser().resolve()
BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", PROJECT_ROOT / "backups")).expanduser().resolve()
OUTPUT_DIR = PROJECT_ROOT / "output"
REPORTS_DIR = PROJECT_ROOT / "reports"
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"
MODELS_DIR = PROJECT_ROOT / "models"
TZ_NAME = os.environ.get("TZ", "Europe/Istanbul")
APP_ENV = os.environ.get("APP_ENV", "development")
WEB_USERNAME = os.environ.get("WEB_USERNAME", "admin")
WEB_PASSWORD = os.environ.get("WEB_PASSWORD", "change_this_password")
WEB_HOST = os.environ.get("WEB_HOST", "127.0.0.1")
WEB_PORT = int(os.environ.get("WEB_PORT", "8000"))
SUPPORTED_COUNTRIES = tuple(
    value.strip().upper() for value in os.environ.get("SUPPORTED_COUNTRIES", "TR,ALL").split(",") if value.strip()
)
ENABLE_FOREIGN_RACES = os.environ.get("ENABLE_FOREIGN_RACES", "true").lower() in {"1", "true", "yes", "on"}


def ensure_runtime_dirs() -> None:
    for path in (LOG_DIR, BACKUP_DIR, OUTPUT_DIR, REPORTS_DIR):
        path.mkdir(parents=True, exist_ok=True)
