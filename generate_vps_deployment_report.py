"""Generate an honest deployment readiness report before/after VPS installation."""
from __future__ import annotations

import platform
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from app_config import BACKUP_DIR, DB_PATH, PROJECT_ROOT, REPORTS_DIR

SYSTEMD = PROJECT_ROOT / "deploy" / "systemd"
EXPECTED = [
    "at-yaris-daily.service", "at-yaris-daily.timer",
    "at-yaris-agf-update.service", "at-yaris-agf-update.timer",
    "at-yaris-results-update.service", "at-yaris-results-update.timer",
    "at-yaris-live-results.service", "at-yaris-live-results.timer",
    "at-yaris-race-freeze.service", "at-yaris-race-freeze.timer",
    "at-yaris-backup.service", "at-yaris-backup.timer",
    "at-yaris-web.service",
]


def main() -> int:
    installed = Path("/etc/systemd/system/at-yaris-daily.service").exists()
    templates = {name: (SYSTEMD / name).exists() for name in EXPECTED}
    try:
        connection = sqlite3.connect(str(DB_PATH), timeout=10)
        quick = connection.execute("PRAGMA quick_check").fetchone()[0]
        snapshots = connection.execute("SELECT COUNT(*) FROM program_snapshots").fetchone()[0]
        agf = connection.execute("SELECT COUNT(*) FROM agf_snapshots").fetchone()[0]
        connection.close()
    except Exception as exc:
        quick, snapshots, agf = f"ERROR: {exc}", 0, 0
    status = "INSTALLED_ON_THIS_HOST" if installed else "PACKAGE_READY_NOT_INSTALLED_ON_THIS_HOST"
    backup_files = sorted(BACKUP_DIR.glob("*.tar.gz"), key=lambda item: item.stat().st_mtime)
    backup_status = backup_files[-1].name if backup_files else "NOT VERIFIED"
    health_path = REPORTS_DIR / "vps_healthcheck.md"
    health_status = "NOT RUN"
    if health_path.exists():
        health_text = health_path.read_text(encoding="utf-8")
        health_status = "PASS" if "## Result: **HEALTHY**" in health_text else "CRITICAL"
    report = f"""# VPS Deployment Report

Generated: {datetime.now():%Y-%m-%d %H:%M:%S}

## Status

**{status}**

This report was generated on `{platform.system()} {platform.release()}`. VPS
service/timer status cannot be claimed until the package is copied to the Linux
host and `deploy/install_vps.sh` is run there.

## Prepared Files

- Linux runners: `run_daily_pipeline.py`, `run_agf_update.py`, `run_results_update.py`
- Backup: `backup_daily.py`, `backup_daily.sh`
- Healthcheck: `healthcheck.py`
- Read-only web dashboard: `web_app.py`, `web/`
- Installer: `deploy/install_vps.sh`
- systemd templates present: `{templates}`
- logrotate: `deploy/logrotate/at-yaris-tahmini`
- environment template: `.env.example`

## Local Source State

- Python: `{sys.version.split()[0]}`
- DB file: `{DB_PATH.name}`
- SQLite quick check: `{quick}`
- Program snapshots: `{snapshots}`
- AGF snapshots: `{agf}`
- PostgreSQL installed by this package: **No**

## Deployment Acceptance State

| Item | State |
| --- | --- |
| systemd units installed on this host | {"YES" if installed else "NO"} |
| Daily service exit code | NOT VERIFIED ON VPS |
| AGF service exit code | NOT VERIFIED ON VPS |
| Results service exit code | NOT VERIFIED ON VPS |
| Timer runtime state | NOT VERIFIED ON VPS |
| Latest backup | {backup_status} |
| Latest healthcheck report | {health_status} |
| Leakage/contract/coverage gates | checked by daily runner before prediction |
| PostgreSQL | NOT INSTALLED |

Package readiness is not production acceptance. Production acceptance requires
the three services and `healthcheck.py` to return exit code 0 on the VPS.

## AGF 10-Minute Rule

`run_agf_update.py` filters `now < race_start_at` and uses the last AGF capture
per race: over 60 minutes every 15 minutes, 60–30 every 5, 30–10 every 2,
and the final 10 minutes every 1 minute. In the final window only the nearest
race start group is eligible. The downloader rechecks
`captured_at < race_start_at` before inserting a snapshot.

## Timers After Installation

- Daily pipeline: 10:00 Europe/Istanbul
- AGF scheduler: every minute, 09:00–23:00; fetch cadence 15/5/2/1 minutes
- Results/matching/monitoring: every 15 minutes, 12:00–23:00
- Backup: 03:30 daily

## Validation Commands

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now at-yaris-daily.timer
sudo systemctl enable --now at-yaris-agf-update.timer
sudo systemctl enable --now at-yaris-results-update.timer
sudo systemctl enable --now at-yaris-backup.timer
sudo systemctl start at-yaris-daily.service
sudo systemctl start at-yaris-agf-update.service
sudo systemctl start at-yaris-results-update.service
systemctl status at-yaris-daily.timer at-yaris-agf-update.timer at-yaris-results-update.timer at-yaris-backup.timer
journalctl -u at-yaris-daily.service -n 200 --no-pager
journalctl -u at-yaris-agf-update.service -n 200 --no-pager
journalctl -u at-yaris-results-update.service -n 200 --no-pager
/opt/at_yaris_tahmini/.venv/bin/python healthcheck.py
```

## Troubleshooting

- `database is locked`: inspect overlapping services and JSON durations; do not delete WAL files while services run.
- Missing snapshots: inspect `agf.err.log`, network access, and future-race selection in `agf_update_latest.json`.
- Leakage/coverage failure: stop prediction; inspect `reports/leakage_gate_v2.md` and `reports/asof_join_validation.md`.
- Model load failure: verify model files and hashes under `models/`.
- Healthcheck backup failure: run `backup_daily.sh` manually and inspect permissions on the backup directory.

## Remaining Risks

- Actual systemd status, network reachability, filesystem permissions, timer
  execution and first successful backup remain VPS-side acceptance checks.
- Existing immutable late snapshots remain retained but are excluded from as-of joins.
- SQLite remains single-host; PostgreSQL thresholds are documented separately.
"""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "vps_deployment_report.md").write_text(report, encoding="utf-8")
    print(status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
