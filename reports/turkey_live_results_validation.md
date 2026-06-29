# Turkey-Only Live Results Validation

Generated: 2026-06-28

## Result: PASS (local) / VPS activation pending

The production race scope now defaults to `SUPPORTED_COUNTRIES=TR` and `ENABLE_FOREIGN_RACES=false`. Historical foreign rows remain immutable in SQLite, but are excluded from race-day UI, performance/diagnostics SQL, new prediction generation, result fetch selection, and coverage denominators.

## Delivered

- Central reversible scope: `race_scope.py`, including TJK track aliases such as Veliefendi → İstanbul.
- `/api/race-day/*` defaults to `country=TR`; disabled `country=ALL` returns HTTP 400.
- `/api/results-refresh/status` reads the runner artifact and verifies track counts against read-only SQLite.
- `run_results_update.py --today-tracks --country TR --skip-monitor --live-status` shares the existing `results_update` lock.
- Completed tracks are filtered before horse-detail requests.
- New systemd units: `at-yaris-live-results.service` and `.timer`, every five minutes.
- `/races` and `/performance` have a 300-second countdown, overlap guard, background-tab slowdown, immediate visible-tab refresh, failure retry, and one-hour completed-day status cadence.
- `shadow_mode.py` and `predict_today.py` reject foreign rows before model execution.

## Validation Evidence

```text
python -m pytest -q
64 passed, 1 existing Starlette TestClient deprecation warning
```

Browser smoke test:

- `/races`: live status rendered and countdown advanced from five minutes
- `/performance`: live status rendered and countdown advanced from five minutes
- Severe JavaScript console errors: `0`

On a host where the live runner has not executed yet, status is deliberately `UNKNOWN`; it becomes `SUCCESS`, `WARNING`, `FAILED`, or `SKIPPED_ALREADY_RUNNING` after the first service run.

SQLite dashboard self-check retains URI `mode=ro` and `PRAGMA query_only=ON`.

## Database-Free Deployment Artifact

- Archive: `dist/at_yaris_tahmini_vps_with_web_20260628T191422Z.tar.gz`
- SHA-256: `2FDF1A926EF5C820E2C405C1AAC1537C44C04855BF55F6285E0FA238D66D8D2D`
- Database files in archive: `0`
- Runtime models/output artifacts in archive: omitted

## VPS Activation

```bash
cd /opt/at_yaris_tahmini
sudo systemctl daemon-reload
sudo systemctl enable --now at-yaris-live-results.timer
sudo systemctl list-timers 'at-yaris-*'
sudo systemctl start at-yaris-live-results.service
sudo journalctl -u at-yaris-live-results.service -n 100 --no-pager
curl -u admin:<password> "http://127.0.0.1:8000/api/results-refresh/status?country=TR"
```

VPS service state is not claimed here because this validation ran on Windows. Before activation, preserve `/opt/at_yaris_tahmini/pedigreeall_progress.db` and `.env`; the supplied archive contains neither database nor `.env`.

## Rollback

```bash
sudo systemctl disable --now at-yaris-live-results.timer
sudo systemctl stop at-yaris-live-results.service
```

The existing 15-minute `at-yaris-results-update.timer` is unchanged and continues operating independently.
