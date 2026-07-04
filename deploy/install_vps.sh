#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT=/opt/at_yaris_tahmini
LOG_DIR=/var/log/at_yaris_tahmini
BACKUP_DIR=/var/backups/at_yaris_tahmini

id -u at_yaris >/dev/null 2>&1 || useradd --system --home "${PROJECT_ROOT}" --shell /usr/sbin/nologin at_yaris
install -d -o at_yaris -g at_yaris "${PROJECT_ROOT}" "${LOG_DIR}" "${BACKUP_DIR}"

cd "${PROJECT_ROOT}"
if [[ ! -f .env ]]; then
    install -m 600 -o at_yaris -g at_yaris .env.example .env
fi
if grep -q '^WEB_PASSWORD=change_this_password$' .env; then
    generated_password="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
    sed -i "s/^WEB_PASSWORD=change_this_password$/WEB_PASSWORD=${generated_password}/" .env
fi
chmod 600 .env
chown -R at_yaris:at_yaris "${PROJECT_ROOT}" "${LOG_DIR}" "${BACKUP_DIR}"

if [[ ! -x .venv/bin/python ]]; then
    sudo -u at_yaris python3 -m venv .venv
fi
sudo -u at_yaris .venv/bin/python -m pip install --upgrade pip
sudo -u at_yaris .venv/bin/python -m pip install -r requirements.txt
chmod +x backup_daily.sh

install -m 644 deploy/systemd/*.service deploy/systemd/*.timer /etc/systemd/system/
install -m 644 deploy/logrotate/at-yaris-tahmini /etc/logrotate.d/at-yaris-tahmini
systemctl daemon-reload
systemctl enable --now \
    at-yaris-daily.timer \
    at-yaris-agf-update.timer \
    at-yaris-results-update.timer \
    at-yaris-live-results.timer \
    at-yaris-race-freeze.timer \
    at-yaris-backup.timer \
    at-yaris-cleanup.timer \
    at-yaris-storage-manager.timer
systemctl enable --now at-yaris-web.service

sudo -u at_yaris .venv/bin/python web_app.py --check
sudo -u at_yaris .venv/bin/python healthcheck.py || true
sudo -u at_yaris .venv/bin/python generate_vps_deployment_report.py
if [[ -f generate_vps_web_deployment_report.py ]]; then
    sudo -u at_yaris .venv/bin/python generate_vps_web_deployment_report.py
fi

echo "Installed. Dashboard credentials are stored in ${PROJECT_ROOT}/.env (mode 600)."
echo "Run the validation commands documented in reports/vps_web_deployment_report.md."
