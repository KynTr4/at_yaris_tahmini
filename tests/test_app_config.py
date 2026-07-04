from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(os.name != "nt", reason="Windows-specific POSIX path fallback")
def test_linux_env_paths_fall_back_to_repo_on_windows(tmp_path):
    repo = Path(__file__).resolve().parent.parent
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "PROJECT_ROOT=/opt/at_yaris_tahmini",
                "DB_PATH=/opt/at_yaris_tahmini/pedigreeall_progress.db",
                "LOG_DIR=/var/log/at_yaris_tahmini",
                "BACKUP_DIR=/var/backups/at_yaris_tahmini",
            ]
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    for key in ("PROJECT_ROOT", "DB_PATH", "LOG_DIR", "BACKUP_DIR"):
        env.pop(key, None)
    env["ENV_FILE"] = str(env_file)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import app_config; "
                "print(app_config.PROJECT_ROOT); "
                "print(app_config.DB_PATH); "
                "print(app_config.LOG_DIR); "
                "print(app_config.BACKUP_DIR)"
            ),
        ],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    paths = [Path(line).resolve() for line in result.stdout.splitlines()]

    assert paths == [
        repo,
        repo / "pedigreeall_progress.db",
        repo / "logs",
        repo / "backups",
    ]
