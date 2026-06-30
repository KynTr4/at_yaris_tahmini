#!/usr/bin/env bash
# deploy.sh - Production Git-based deployment automation script.
set -euo pipefail

PROJECT_ROOT="/opt/at_yaris_tahmini"
REPORTS_DIR="${PROJECT_ROOT}/reports"
mkdir -p "$REPORTS_DIR"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
REPORT_PATH="${REPORTS_DIR}/deploy_report_${TIMESTAMP}.md"

PREV_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
MIGRATIONS_OUT=""
BUILD_OUT="No build required (Python-only environment)"
BACKUP_PATH=""
PYTHON_CHECK=""
QUERY_ONLY_CHECK=""

echo "=== Starting Deploy Process: ${TIMESTAMP} ==="

# Function to write deploy report
write_report() {
    local status=$1
    local msg=$2
    local new_commit=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
    local disk_info=$(df -h "${PROJECT_ROOT}" | tail -n 1)
    
    cat <<EOF > "$REPORT_PATH"
# Deploy Report - ${TIMESTAMP}

- **Deploy Status:** ${status}
- **Deploy Time:** $(date +"%Y-%m-%d %H:%M:%S")
- **Git Commit Before:** ${PREV_COMMIT}
- **Git Commit After:** ${new_commit}
- **Migration Status:** ${MIGRATIONS_OUT:-"N/A"}
- **Build Status:** ${BUILD_OUT:-"N/A"}
- **Services Restarted:**
  - at-yaris-web.service
  - at-yaris-results-update.timer
  - at-yaris-race-freeze.timer
- **Health Checks:**
  - Web Server (/health): $([ "${PYTHON_CHECK}" = "HEALTHY" ] && echo "PASS" || echo "FAIL (${PYTHON_CHECK})")
  - SQLite query_only: $([ "${QUERY_ONLY_CHECK}" = "QUERY_ONLY_VERIFIED" ] && echo "PASS" || echo "FAIL (${QUERY_ONLY_CHECK})")
  - results-update timer: $(systemctl is-active at-yaris-results-update.timer || echo "inactive")
  - race-freeze timer: $(systemctl is-active at-yaris-race-freeze.timer || echo "inactive")
- **Backup Created:** ${BACKUP_PATH:-"None"}
- **Deploy Backup Retention:** Kept last 3 backups, pruned older backups.
- **Disk Usage:** ${disk_info}
- **Message:** ${msg}
EOF
    echo "Deploy report written to: ${REPORT_PATH}"
}

run_deploy() {
    # 1. Take a deploy backup of critical files before fetching/resetting
    echo "Taking deploy configuration backup..."
    DEPLOY_BACKUPS_DIR="/var/backups/at_yaris_tahmini/deploy_backups"
    mkdir -p "$DEPLOY_BACKUPS_DIR"

    BACKUP_NAME="deploy_backup_${TIMESTAMP}.tar.gz"
    BACKUP_PATH="${DEPLOY_BACKUPS_DIR}/${BACKUP_NAME}"

    TEMP_META_DIR=$(mktemp -d)
    META_FILE="${TEMP_META_DIR}/deploy_metadata.json"

    cat <<EOF > "$META_FILE"
{
  "timestamp": "${TIMESTAMP}",
  "prev_commit": "${PREV_COMMIT}",
  "env_exists": $([ -f "${PROJECT_ROOT}/.env" ] && echo "true" || echo "false")
}
EOF

    # Create archive of critical configs only
    tar -czf "$BACKUP_PATH" \
        -C "${PROJECT_ROOT}" .env deploy/systemd requirements.txt migrations \
        -C "${TEMP_META_DIR}" deploy_metadata.json 2>/dev/null || true

    rm -rf "$TEMP_META_DIR"
    echo "Deploy configuration backup created at: ${BACKUP_PATH}"

    # Enforce deploy backup retention (keep most recent 3 backups)
    echo "Enforcing deploy backup retention..."
    local backup_files=($(ls -t "${DEPLOY_BACKUPS_DIR}/deploy_backup_"*.tar.gz 2>/dev/null || true))
    if [ ${#backup_files[@]} -gt 3 ]; then
        for ((i=3; i<${#backup_files[@]}; i++)); do
            echo "Pruning old deploy backup: ${backup_files[$i]}"
            rm -f "${backup_files[$i]}"
        done
    fi

    # 2. Git Fetch & Reset
    echo "Fetching from Git remote origin..."
    git fetch origin

    echo "Resetting repository to origin/main..."
    git reset --hard origin/main

    # 3. Migration Check & Execution
    if [ -f "${PROJECT_ROOT}/migrate_provenance_schema.py" ]; then
        echo "Running migrations..."
        MIGRATIONS_OUT=$("${PROJECT_ROOT}/.venv/bin/python" "${PROJECT_ROOT}/migrate_provenance_schema.py" 2>&1)
    else
        MIGRATIONS_OUT="No migrate_provenance_schema.py script found"
    fi
    echo "Migration output: ${MIGRATIONS_OUT}"

    # 4. Systemd reload & restarts
    echo "Reloading systemd daemon..."
    systemctl daemon-reload

    echo "Restarting services..."
    systemctl restart at-yaris-web.service
    systemctl restart at-yaris-results-update.timer
    systemctl restart at-yaris-race-freeze.timer

    # Wait for services to start/settle
    echo "Waiting for services to settle..."
    sleep 5

    # 5. Health Checks
    if [ -f "${PROJECT_ROOT}/.env" ]; then
        # Load env port/host securely
        local web_port=$(grep "^WEB_PORT=" "${PROJECT_ROOT}/.env" | cut -d= -f2 | tr -d '"' | tr -d "'")
        local web_host=$(grep "^WEB_HOST=" "${PROJECT_ROOT}/.env" | cut -d= -f2 | tr -d '"' | tr -d "'")
    fi
    local port="${web_port:-8000}"
    local host="${web_host:-127.0.0.1}"

    # Test /health endpoint
    local health_url="http://${host}:${port}/health"
    echo "Testing health check endpoint at ${health_url}..."
    local health_response=$(curl -s -f --max-time 10 "$health_url" || echo "failed")

    if [ "$health_response" = "failed" ]; then
        PYTHON_CHECK="Health check request failed"
        return 1
    fi

    PYTHON_CHECK=$("${PROJECT_ROOT}/.venv/bin/python" -c "
import json, sys
try:
    data = json.loads('''$health_response''')
    if data.get('status') == 'healthy' and data.get('database') == 'ok':
        print('HEALTHY')
        sys.exit(0)
    else:
        print('UNHEALTHY:', data)
        sys.exit(1)
except Exception as e:
    print('PARSE_ERROR:', e)
    sys.exit(1)
" 2>&1)

    if [ "$PYTHON_CHECK" != "HEALTHY" ]; then
        return 1
    fi

    # Verify SQLite query_only readonly connection
    echo "Verifying SQLite read-only connection..."
    QUERY_ONLY_CHECK=$("${PROJECT_ROOT}/.venv/bin/python" -c "
import sqlite3, sys
from app_config import DB_PATH
try:
    conn = sqlite3.connect(f'file:{DB_PATH.as_posix()}?mode=ro', uri=True, timeout=5)
    conn.execute('PRAGMA query_only=ON')
    conn.execute('CREATE TABLE IF NOT EXISTS test_write (id INT)')
    print('WRITE_SUCCEEDED')
    conn.close()
    sys.exit(1)
except sqlite3.OperationalError as e:
    if 'readonly' in str(e).lower() or 'read-only' in str(e).lower():
        print('QUERY_ONLY_VERIFIED')
        sys.exit(0)
    else:
        print('OPERATIONAL_ERROR:', e)
        sys.exit(1)
except Exception as e:
    print('ERROR:', e)
    sys.exit(1)
" 2>&1)

    if [ "$QUERY_ONLY_CHECK" != "QUERY_ONLY_VERIFIED" ]; then
        return 1
    fi

    # Verify systemd timer statuses
    local results_timer_active=$(systemctl is-active at-yaris-results-update.timer || echo "inactive")
    local freeze_timer_active=$(systemctl is-active at-yaris-race-freeze.timer || echo "inactive")

    if [ "$results_timer_active" != "active" ] || [ "$freeze_timer_active" != "active" ]; then
        return 1
    fi

    return 0
}

# Run deploy wrapped to log outcomes
if run_deploy; then
    echo "Deploy Succeeded!"
    write_report "SUCCESS" "Deploy finished successfully without errors."
else
    echo "Deploy Failed!"
    write_report "FAILED" "Deploy failed during step execution. Check systemd logs and output reports."
    exit 1
fi
