# Model Diagnostics Validation

Generated: 2026-06-28

## Result: PASS

`/diagnostics` was added without changing prediction generation, schedulers, model artifacts, or database schema. All data access uses the dashboard's SQLite URI `mode=ro` connection with `PRAGMA query_only=ON`.

## Evaluation Contract

- One row represents one evaluated race.
- Only the latest archived prediction run satisfying `prediction_time < race_start_at` is used.
- Logistic, CatBoost, XGBoost, and Ensemble ranks are derived from their stored probabilities; models are never loaded or rerun.
- Official winners come from the latest `race_results` row with `result_status='finished'` and `finish_position=1`.
- AGF uses the latest snapshot satisfying `captured_at < race_start_at`.
- ROI/net profit uses the selected horse's latest certified pre-race `odds_snapshots` row. If it does not exist, ROI is displayed as `NOT CERTIFIED`.
- SHAP is displayed as `Not available` because no immutable SHAP contribution archive exists. The dashboard does not fabricate or recompute contributions.

## Delivered Analysis

- Race table: Top-1 horse/probability, winner rank/probability, probability gap, winner AGF, AGF favorite, correct/wrong.
- Top-1, Top-2, Top-3, and Top-5 accuracy.
- Winner-rank histogram.
- Model/AGF comparison counts.
- Surface, breed, race class, distance, and field-size group performance.
- Top 50 high-confidence errors and low-confidence successes.
- Date, track, model, race type, distance, surface, and field-size filters.
- 100-row server-side pagination and streaming UTF-8 CSV export.

## Security and Regression Validation

- Basic Auth applies to the page, APIs, CSV, and static assets.
- Filter values are bound SQLite parameters; model names are allowlisted.
- Existing dashboard routes and test suite remain operational.
- Browser smoke test: `GÜNCEL`, zero severe JavaScript console errors (favicon 404 excluded).
- Responsive desktop mock: `reports/model_diagnostics_mock.png`.

## Test Evidence

```text
python -m pytest tests/test_diagnostics_dashboard.py -q
3 passed

python -m pytest -q
58 passed, 1 warning
```

The warning is Starlette's existing TestClient/httpx deprecation warning and is unrelated to diagnostics behavior.

## Local Data Note

The local database checked on 2026-06-28 contains zero `prediction_snapshots` and zero `race_results`, so the real local page correctly renders an empty evaluated state. Functional metrics were validated against isolated migrated SQLite fixtures containing known Winner Rank 1 and Winner Rank 3 outcomes. Live metrics will appear after the VPS archive contains matched predictions and results.
