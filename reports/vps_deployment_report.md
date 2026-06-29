# VPS Deployment Report

Generated: 2026-06-27 22:22:38

## Status

**PACKAGE_READY_NOT_INSTALLED_ON_THIS_HOST**

This report was generated on `Windows 10`. VPS
service/timer status cannot be claimed until the package is copied to the Linux
host and `deploy/install_vps.sh` is run there.

## Prepared Files

- Linux runners: `run_daily_pipeline.py`, `run_agf_update.py`, `run_results_update.py`
- Backup: `backup_daily.py`, `backup_daily.sh`
- Healthcheck: `healthcheck.py`
- Read-only web dashboard: `web_app.py`, `web/`
- Installer: `deploy/install_vps.sh`
- systemd templates present: `{'at-yaris-daily.service': True, 'at-yaris-daily.timer': True, 'at-yaris-agf-update.service': True, 'at-yaris-agf-update.timer': True, 'at-yaris-results-update.service': True, 'at-yaris-results-update.timer': True, 'at-yaris-backup.service': True, 'at-yaris-backup.timer': True, 'at-yaris-web.service': True}`
- logrotate: `deploy/logrotate/at-yaris-tahmini`
- environment template: `.env.example`

## Local Source State

- Python: `3.10.6`
- DB file: `pedigreeall_progress.db`
- SQLite quick check: `ok`
- Program snapshots: `589`
- AGF snapshots: `585`
- PostgreSQL installed by this package: **No**

## Deployment Acceptance State

| Item | State |
| --- | --- |
| systemd units installed on this host | NO |
| Daily service exit code | NOT VERIFIED ON VPS |
| AGF service exit code | NOT VERIFIED ON VPS |
| Results service exit code | NOT VERIFIED ON VPS |
| Timer runtime state | NOT VERIFIED ON VPS |
| Latest backup | NOT VERIFIED |
| Latest healthcheck report | CRITICAL |
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
