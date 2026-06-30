#!/usr/bin/env bash
# cleanup.sh - Nightly cleanup script for AT Yaris Shadow system.
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/opt/at_yaris_tahmini}"
BACKUP_DIR="/var/backups/at_yaris_tahmini"
DEPLOY_BACKUPS_DIR="${BACKUP_DIR}/deploy_backups"

echo "=== AT Yaris Cleanup Script Started: $(date) ==="

# 1. Clean up deploy backups older than 7 days
if [ -d "$DEPLOY_BACKUPS_DIR" ]; then
    echo "Cleaning up deploy backups older than 7 days in ${DEPLOY_BACKUPS_DIR}..."
    find "$DEPLOY_BACKUPS_DIR" -type f -name "deploy_backup_*.tar.gz" -mtime +7 -delete || true
fi

# 2. Clean up AGF HTML cache older than 30 days
HTML_CACHE_DIR="${PROJECT_ROOT}/data/agfv2_raw/html"
if [ -d "$HTML_CACHE_DIR" ]; then
    echo "Cleaning up AGF HTML cache older than 30 days in ${HTML_CACHE_DIR}..."
    find "$HTML_CACHE_DIR" -type f -name "*.html" -mtime +30 -delete || true
fi

# 3. Clean up temporary reports older than 30 days
REPORTS_DIR="${PROJECT_ROOT}/reports"
if [ -d "$REPORTS_DIR" ]; then
    echo "Cleaning up temporary reports older than 30 days in ${REPORTS_DIR}..."
    find "$REPORTS_DIR" -type f \( -name "results_coverage_*.md" -o -name "deploy_report_*.md" \) -mtime +30 -delete || true
fi

# 4. Clean up pip cache
echo "Cleaning up pip cache..."
rm -rf ~/.cache/pip || true

# 5. Clean up __pycache__, pytest, build and dist caches in project directory
echo "Cleaning up Python, pytest, and build caches..."
find "$PROJECT_ROOT" -type d -name "__pycache__" -exec rm -rf {} + || true
rm -rf "${PROJECT_ROOT}/.pytest_cache" || true
rm -rf "${PROJECT_ROOT}/build" || true
rm -rf "${PROJECT_ROOT}/dist" || true
rm -rf "${PROJECT_ROOT}/*.egg-info" || true
rm -rf "${PROJECT_ROOT}/.cache" || true

echo "=== Cleanup Completed Successfully: $(date) ==="
