#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="${PROJECT_ROOT:-/opt/at_yaris_tahmini}"
exec "${PROJECT_ROOT}/.venv/bin/python" "${PROJECT_ROOT}/backup_db.py"
