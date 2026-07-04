#!/usr/bin/env bash
# cleanup.sh — Nightly storage lifecycle for AT Yaris Shadow system.
# Çalışma zamanı: 04:00 Europe/Istanbul (at-yaris-cleanup.timer)
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/opt/at_yaris_tahmini}"
PYTHON="${PROJECT_ROOT}/.venv/bin/python"
LOG_PREFIX="[AT-YARIS CLEANUP]"

echo "=== ${LOG_PREFIX} Başladı: $(date) ==="

# 1. Python storage manager — retention, VACUUM, cache, rapor
#    --threshold 80: disk %80 geçince alert (exit 2)
if "${PYTHON}" "${PROJECT_ROOT}/storage_manager.py" --threshold 80; then
    echo "${LOG_PREFIX} Storage manager tamamlandı."
else
    exit_code=$?
    if [ "${exit_code}" -eq 2 ]; then
        echo "${LOG_PREFIX} UYARI: Disk kullanımı eşiği aşıldı! Rapor: ${PROJECT_ROOT}/reports/storage_report.json"
    else
        echo "${LOG_PREFIX} Storage manager HATAYLA sonlandı (exit=${exit_code})" >&2
    fi
fi

# 2. Deploy yedeklerini temizle (7 günden eski)
DEPLOY_BACKUPS_DIR="/var/backups/at_yaris_tahmini/deploy_backups"
if [ -d "${DEPLOY_BACKUPS_DIR}" ]; then
    echo "${LOG_PREFIX} Deploy yedeklerini temizliyor (>7 gün)..."
    find "${DEPLOY_BACKUPS_DIR}" -type f -name "deploy_backup_*.tar.gz" -mtime +7 -delete || true
fi

# 3. AGF HTML önbelleği (30 günden eski)
HTML_CACHE_DIR="${PROJECT_ROOT}/data/agfv2_raw/html"
if [ -d "${HTML_CACHE_DIR}" ]; then
    echo "${LOG_PREFIX} AGF HTML önbelleğini temizliyor (>30 gün)..."
    find "${HTML_CACHE_DIR}" -type f -name "*.html" -mtime +30 -delete || true
fi

# 4. __pycache__, .pytest_cache, build/dist artıkları
#    (storage_manager.py da yapar ama burada da tutuyoruz güvence için)
echo "${LOG_PREFIX} Python önbelleklerini temizliyor..."
find "${PROJECT_ROOT}" -type d -name "__pycache__" \
    -not -path "${PROJECT_ROOT}/.venv/*" \
    -exec rm -rf {} + 2>/dev/null || true
rm -rf "${PROJECT_ROOT}/.pytest_cache" \
       "${PROJECT_ROOT}/build" \
       "${PROJECT_ROOT}/dist" \
       "${PROJECT_ROOT}/.cache" 2>/dev/null || true

# 5. pip önbelleği
echo "${LOG_PREFIX} pip önbelleğini temizliyor..."
"${PYTHON}" -m pip cache purge 2>/dev/null || true

echo "=== ${LOG_PREFIX} Tamamlandı: $(date) ==="
