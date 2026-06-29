"""Generate the web-enabled VPS deployment and transfer report."""
from __future__ import annotations

import hashlib
import platform
from datetime import datetime

from app_config import PROJECT_ROOT, REPORTS_DIR
from web_app import ALLOWED_LOGS, ALLOWED_REPORTS, self_check, systemd_status


def sha256(path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def main() -> int:
    archives = sorted(
        (PROJECT_ROOT / "dist").glob("at_yaris_tahmini_vps_with_web_*.tar.gz"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    archive = archives[0] if archives else None
    archive_name = archive.name if archive else "NOT GENERATED"
    archive_hash = sha256(archive) if archive else "NOT GENERATED"
    health = REPORTS_DIR / "vps_healthcheck.md"
    health_state = "HEALTHY" if health.is_file() and "## Result: **HEALTHY**" in health.read_text(encoding="utf-8") else "CRITICAL/NOT VERIFIED"
    checks = self_check()
    units = systemd_status()
    report = f"""# VPS Web Deployment Report

Generated: {datetime.now():%Y-%m-%d %H:%M:%S}

## Readiness State

- Generated on: `{platform.system()} {platform.release()}`
- Local web self-check: `{'PASS' if all(checks.values()) else 'FAIL'}` — `{checks}`
- Basic Auth: `ENFORCED` for HTML, JSON API and static routes
- SQLite mode: `read-only / query_only`
- VPS web service state: `{units.get('at-yaris-web.service', 'unknown')}`
- Latest healthcheck: `{health_state}`
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
- `web/templates/diagnostics.html`
- `web/templates/diagnostics_race.html`
- `web/templates/reports.html`
- `web/templates/logs.html`
- `web/static/style.css`
- `deploy/systemd/at-yaris-web.service`
- `deploy/nginx/at-yaris-dashboard.conf`

## Web Endpoints

- HTML: `/`, `/races`, `/predictions`, `/performance`, `/diagnostics`,
  `/diagnostics/race/{race_id}`, `/reports`, `/logs`
- JSON: `/api/health`, `/api/today-races`, `/api/predictions`, `/api/shadow-status`, `/api/systemd-status`
- Performance JSON: `/api/performance/summary`, `/api/performance/models`,
  `/api/performance/history`, `/api/performance/chart`, `/api/performance/races`
- Race-day JSON: `/api/race-day/summary`, `/api/race-day/tracks`,
  `/api/race-day/races`, `/api/race-day/performance`
- Live results JSON: `/api/results-refresh/status` (all program tracks by default)
- Missing data JSON/CSV: `/api/race-day/missing-horses`,
  `/api/race-day/missing-horses/export.csv`
- Bet simulator: `/bet-simulator`, `/api/bet-simulator/summary`,
  `/api/bet-simulator/history`, `/api/bet-simulator/export.csv`
- Diagnostics JSON: `/api/diagnostics/summary`, `/api/diagnostics/races`,
  `/api/diagnostics/winner-ranks`, `/api/diagnostics/groups`,
  `/api/diagnostics/extremes`, `/api/diagnostics/filters`,
  `/api/diagnostics/feature-contribution`, `/api/diagnostics/race/{race_id}`,
  `/api/diagnostics/export.csv`
- Allowed reports: `{', '.join(ALLOWED_REPORTS)}`
- Allowed logs: `{', '.join(ALLOWED_LOGS)}`; last 200 lines only

## Security Controls

- Every request requires constant-time checked Basic Auth.
- `.env` is neither served nor included in the archive.
- Database connections use SQLite URI `mode=ro` and `PRAGMA query_only=ON`.
- Report/log names are strict allowlists; arbitrary paths are rejected.
- The installer replaces the placeholder password with a random 48-character hex secret.
- The dashboard does not import model runners or invoke pipeline scripts.

## Transfer Package

- Package: `{archive_name}`
- SHA-256: `{archive_hash}`
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
systemctl status at-yaris-live-results.timer
systemctl status at-yaris-race-freeze.timer
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
"""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "vps_web_deployment_report.md").write_text(report, encoding="utf-8")
    print(archive_name)
    print(archive_hash)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
