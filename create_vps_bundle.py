"""Create a reproducible Linux VPS deployment bundle.

The live SQLite database is copied through sqlite3.Connection.backup(), never by
copying its file while writers may be active.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sqlite3
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from app_config import DB_PATH, PROJECT_ROOT


ROOT_FILES = (
    "requirements.txt",
    ".env.example",
    ".deploymentignore",
    "README.md",
    "DATA_DICTIONARY.md",
    "backup_daily.sh",
)
CODE_DIRS = ("deploy", "migrations", "tests", "docs", "web")
RUNTIME_DIRS = ("models", "output", "reports")
EXCLUDED_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".env",
}


def copy_tree(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    shutil.copytree(
        source,
        destination,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(*EXCLUDED_NAMES, "*.pyc", "*.tmp"),
    )


def sqlite_backup(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True) as src:
        with sqlite3.connect(destination) as dst:
            src.backup(dst)
            result = dst.execute("PRAGMA quick_check").fetchone()[0]
            if result != "ok":
                raise RuntimeError(f"Bundle database quick_check failed: {result}")


def write_checksum(archive: Path) -> Path:
    digest = hashlib.sha256()
    with archive.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    sidecar = archive.with_name(f"{archive.name}.sha256")
    sidecar.write_text(f"{digest.hexdigest().upper()}  {archive.name}\n", encoding="ascii")
    return sidecar


def build_bundle(
    output_dir: Path,
    include_database: bool = True,
    include_runtime_assets: bool = True,
) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / f"at_yaris_tahmini_vps_with_web_{stamp}.tar.gz"

    with tempfile.TemporaryDirectory(prefix="at_yaris_bundle_") as temporary:
        bundle_root = Path(temporary) / "at_yaris_tahmini"
        bundle_root.mkdir()

        for source in PROJECT_ROOT.glob("*.py"):
            shutil.copy2(source, bundle_root / source.name)
        for name in ROOT_FILES:
            source = PROJECT_ROOT / name
            if source.exists():
                shutil.copy2(source, bundle_root / name)
        for name in CODE_DIRS:
            copy_tree(PROJECT_ROOT / name, bundle_root / name)
        if include_runtime_assets:
            for name in RUNTIME_DIRS:
                copy_tree(PROJECT_ROOT / name, bundle_root / name)
        for name in ("models", "output", "reports", "logs"):
            (bundle_root / name).mkdir(exist_ok=True)

        if include_database:
            if not DB_PATH.exists():
                raise FileNotFoundError(f"SQLite database not found: {DB_PATH}")
            sqlite_backup(DB_PATH, bundle_root / DB_PATH.name)

        with tarfile.open(archive, "w:gz") as tar:
            tar.add(bundle_root, arcname="at_yaris_tahmini")

    write_checksum(archive)
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "dist",
        help="Directory that receives the tar.gz archive.",
    )
    parser.add_argument(
        "--without-database",
        action="store_true",
        help="Create a code-only bundle.",
    )
    parser.add_argument(
        "--without-runtime-assets",
        action="store_true",
        help="Omit models/output/reports for a lightweight packaging smoke test.",
    )
    args = parser.parse_args()
    archive = build_bundle(
        args.output_dir.resolve(),
        include_database=not args.without_database,
        include_runtime_assets=not args.without_runtime_assets,
    )
    print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
