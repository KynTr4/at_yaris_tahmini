# VPS Web Deployment Report

Generated: 2026-06-28 21:21:38

## Readiness State

- Generated on: `Windows 10`
- Local web self-check: `PASS` — `{'database_readable': True, 'database_query_only': True, 'templates_present': True, 'static_present': True, 'basic_auth_configured': True}`
- Basic Auth: `ENFORCED` for HTML, JSON API and static routes
- SQLite mode: `read-only / query_only`
- VPS web service state: `unavailable_on_this_host`
- Latest healthcheck: `CRITICAL/NOT VERIFIED`
- PostgreSQL: `NOT INSTALLED`

The package is transfer-ready. Production acceptance is pending until the
service, authenticated endpoint and full healthcheck pass on the Linux VPS.

## Dashboard Files

- `web_app.py`
- `web/templates/base.html`
- `web/templates/dashboard.html`
- `web/templates/races.html`
- `web/templates/predictions.html`
- `web/templates/performance.html`
- `web/templates/reports.html`
- `web/templates/logs.html`
- `web/static/style.css`
- `deploy/systemd/at-yaris-web.service`
- `deploy/nginx/at-yaris-dashboard.conf`

## Web Endpoints

- HTML: `/`, `/races`, `/predictions`, `/performance`, `/reports`, `/logs`
- JSON: `/api/health`, `/api/today-races`, `/api/predictions`, `/api/shadow-status`, `/api/systemd-status`
- Performance JSON: `/api/performance/summary`, `/api/performance/models`,
  `/api/performance/history`, `/api/performance/chart`, `/api/performance/races`
- Race-day JSON: `/api/race-day/summary`, `/api/race-day/tracks`,
  `/api/race-day/races`, `/api/race-day/performance`
- Allowed reports: `model_health_dashboard.md, daily_shadow_report.md, live_accuracy_report.md, model_drift_report.md, feature_drift_report.md, calibration_monitor.md, live_roi_report.md, leakage_gate_v2.md, vps_healthcheck.md, results_coverage_latest.md, izmir_results_debug.md, race_day_dashboard_validation.md`
- Allowed logs: `daily.log, daily.err.log, agf.log, agf.err.log, results.log, results.err.log, web.log, web.err.log`; last 200 lines only

## Security Controls

- Every request requires constant-time checked Basic Auth.
- `.env` is neither served nor included in the archive.
- Database connections use SQLite URI `mode=ro` and `PRAGMA query_only=ON`.
- Report/log names are strict allowlists; arbitrary paths are rejected.
- The installer replaces the placeholder password with a random 48-character hex secret.
- The dashboard does not import model runners or invoke pipeline scripts.

## Transfer Package

- Package: `at_yaris_tahmini_vps_with_web_20260628T181919Z.tar.gz`
- SHA-256: `CF3C776A77CD23078E7AF027754D4CDAE38614E826977DFA8E56EE485F0DF5D7`
- Includes: Python scripts, requirements, SQLite backup, models, output, reports,
  migrations, tests, docs, deploy, web and `.env.example`.
- Excludes: `.env`, `.venv`, `__pycache__`, logs, temp files, scratch and old backups.

## VPS Commands

```bash
cd /opt/at_yaris_tahmini
sudo bash deploy/install_vps.sh

systemctl status at-yaris-web.service
systemctl status at-yaris-daily.timer
systemctl status at-yaris-agf-update.timer
systemctl status at-yaris-results-update.timer
systemctl status at-yaris-backup.timer

sudo grep '^WEB_' /opt/at_yaris_tahmini/.env
curl -u admin:<password-from-env> http://127.0.0.1:8000/api/health
sudo journalctl -u at-yaris-web.service -n 100 --no-pager
sudo -u at_yaris /opt/at_yaris_tahmini/.venv/bin/python healthcheck.py
```

## Optional Nginx and HTTPS

```bash
sudo apt-get install -y nginx
sudo install -m 644 deploy/nginx/at-yaris-dashboard.conf /etc/nginx/sites-available/at-yaris-dashboard
sudo ln -sfn /etc/nginx/sites-available/at-yaris-dashboard /etc/nginx/sites-enabled/at-yaris-dashboard
sudo nginx -t && sudo systemctl reload nginx
```

For public access, replace the wildcard server name with a DNS hostname, restrict
the firewall to SSH/HTTP/HTTPS, then obtain a certificate with Certbot. Do not
send Basic Auth credentials over plain Internet-facing HTTP.

## Remaining Risks

- systemd state, firewall, DNS, TLS, network access and filesystem permissions
  can only be accepted on the target VPS.
- Bootstrap is loaded from a public CDN; a locked-down/offline host should vendor it.
- Basic Auth is suitable only behind HTTPS and should be combined with IP filtering
  or VPN access for a private operations dashboard.
- Local healthcheck remains critical until scheduled runs, a backup and the web
  service exist on the VPS.
