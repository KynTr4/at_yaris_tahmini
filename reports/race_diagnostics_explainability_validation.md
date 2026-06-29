# Race Diagnostics Explainability Validation

Generated: 2026-06-28

## Result: PASS

The race-level “Neden Bu Tahmin Yapıldı?” workflow is implemented without retraining, model inference, SHAP recomputation, or dashboard writes.

## Evidence Contract

- Probabilities and ranks come from the latest immutable pre-race `prediction_snapshots` run.
- Model inputs come from `prediction_feature_snapshots`; historical rows fall back to the already immutable `prediction_snapshots.feature_values_json` field.
- Program fields come from the exact `program_snapshots.snapshot_id` referenced by `feature_snapshot_id`, not a later program snapshot.
- AGF and odds are selected only where `captured_at <= prediction_time`.
- Finish position comes from the latest official `race_results` row.
- Missing age, sex, pedigree, career, or feature values are displayed as `Not available`; current mutable profiles are not substituted for prediction-time evidence.
- SHAP remains `Not available` because no immutable SHAP archive exists. No SHAP value is computed on demand.

## Confidence Rule v1

- High: Top-1 probability ≥ 0.25 or Top-1/Top-2 margin ≥ 0.10.
- Low: Top-1 probability < 0.15 and margin < 0.03.
- Otherwise: Medium.
- High/Low labels include Correct/Wrong; the requested middle class is `Medium Confidence`.

These labels describe archived probability concentration only. They are not new predictions.

## Immutable Feature Archive

Migration `011_prediction_feature_snapshots.sql` creates an append-only table with update/delete guards. `shadow_mode.archive_predictions()` writes prediction and feature rows in the same SQLite transaction. A feature-archive failure therefore rolls back the prediction write as well.

Local migration result:

```text
applied: 011_prediction_feature_snapshots.sql
table present: true
append-only triggers: 2
current rows: 0
```

The local database currently has no archived predictions; future production predictions will populate both tables.

## Delivered UI/API

- Diagnostics table `İncele` action.
- HTML: `/diagnostics/race/{race_id}`.
- JSON: `/api/diagnostics/race/{race_id}?model=Ensemble`.
- Side-by-side model selection and winner cards.
- Complete archived feature comparison.
- Full race ranking plus Top-10 payload.
- Winner highlighting, confidence classification, and evidence-based miss explanation.
- Explicit missing-snapshot and missing-SHAP states.

## Validation

```text
python -m pytest -q
66 passed, 1 existing Starlette TestClient deprecation warning
```

Browser smoke test:

- Detail status: `GÜNCEL`
- Winner-highlighted rows: `1`
- Feature comparison rows: `4`
- Severe browser console errors: `0`
- Mock: `reports/race_diagnostics_mock.png`

SQLite dashboard connections remain URI `mode=ro` with `PRAGMA query_only=ON`.

## Database-Free Deployment Artifact

- Archive: `dist/at_yaris_tahmini_vps_with_web_20260628T193549Z.tar.gz`
- SHA-256: `CF06D8348036BBF3DA63571CC9518EDF9DB38110252DEF482DF8AA3A4C83FE34`
- Database files: `0`

After deploying code, apply the migration before the next prediction run:

```bash
sudo -u at_yaris /opt/at_yaris_tahmini/.venv/bin/python \
  /opt/at_yaris_tahmini/migrate_provenance_schema.py
sudo systemctl restart at-yaris-web.service
```
