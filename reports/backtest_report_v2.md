# Production Backtest Report v2

Generated: 2026-06-27 18:39:26

## Executive Decision

- Production ready: **No, not yet**. The intended recent-year temporal test now runs successfully; betting-data quality and live validation gates remain.
- Best holdout model: **catboost**.
- Expected winner accuracy from the 2026 holdout: **57.95%** across `2452` races.
- Observed top-1 ROI under stated assumptions: **125.33%**. This is descriptive, not a guaranteed live return.
- Highest SHAP contributors: catboost: handicap_rating, last_3_avg_position, race_class, draw, track; logistic: race_class, surface, handicap_rating, track, last_3_avg_position; xgboost: handicap_rating, race_class, last_3_avg_position, draw, track.

## Temporal Design

| split | evaluation_year | train_rows | train_races | train_max_date | evaluation_rows | evaluation_races | evaluation_min_date | evaluation_max_date |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| validation | 2024 | 633110 | 83260 | 2023-12-31 | 13268 | 2228 | 2024-01-02 | 2024-12-31 |
| test | 2025 | 646378 | 85488 | 2024-12-31 | 36640 | 4415 | 2025-01-01 | 2025-12-31 |
| holdout | 2026 | 683018 | 89903 | 2025-12-31 | 21496 | 2452 | 2026-01-01 | 2026-06-26 |

Every fold was retrained from scratch with `train_date < evaluation_date`. Saved production model predictions were not reused. Validation, test and holdout evaluate 2024, 2025 and 2026 respectively.

## Data Integrity

- Source rows/columns: `961695` / `62`.
- Backtest as-of date: `2026-06-27`; future-dated rows excluded: `0`.
- Completed valid-race rows evaluated/trained: `704514`.
- Excluded races without exactly one winner or with fewer than two runners: `52460`.
- Duplicate horse/race rows in source: `0`.
- Leakage columns intersecting model features: `[]`.
- AGF value-bet test remains unavailable because a reliable timestamped pre-race AGF snapshot is not present.

## Error Analysis

| model | lost_races | agf_favorite_analysis | predicted_horse_jockey_change_rate | predicted_horse_surface_change_rate | predicted_horse_distance_change_rate | predicted_horse_steward_incident_rate | actual_winner_jockey_change_rate | actual_winner_surface_change_rate | actual_winner_distance_change_rate | actual_winner_steward_incident_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| logistic | 5813 | unavailable | 0.0000 | 0.3253 | 0.6260 | 0.0000 | 0.0000 | 0.2908 | 0.6966 | 0.0000 |
| catboost | 3700 | unavailable | 0.0000 | 0.2465 | 0.7327 | 0.0000 | 0.0000 | 0.2908 | 0.6966 | 0.0000 |
| xgboost | 3920 | unavailable | 0.0000 | 0.3013 | 0.7005 | 0.0000 | 0.0000 | 0.2908 | 0.6966 | 0.0000 |
| ensemble | 3804 | unavailable | 0.0000 | 0.2466 | 0.7369 | 0.0000 | 0.0000 | 0.2908 | 0.6966 | 0.0000 |

AGF-favorite loss analysis is unavailable. Commissioner, jockey, surface and distance indicators are reported as association rates only; they do not establish causality.

## Weaknesses And Final Work

- Preserve the DB-backed rebuild and rerun these recent-year splits after each material data refresh.
- Repair AGF ingestion before enabling value betting; preserve timestamped pre-race AGF snapshots.
- Confirm that historical odds are genuinely available pre-bet and encode dead heats, scratches, deductions, commissions and stake limits.
- Monitor live calibration and feature drift across the 2024/2025/2026 evaluation sequence.
- Use the selected model only after those gates pass; current results justify shadow mode, not unattended wagering.

## Artifacts

- `output/backtest_predictions_v2.csv`
- `output/model_scores_v2.csv`
- `output/roi_simulation_v2.csv`
- `output/calibration_table_v2.csv`
- `reports/model_comparison_v2.md`
- `reports/calibration_report_v2.md`
- `reports/calibration_curve_v2.png`
- `reports/roi_report_v2.md`
- `reports/feature_importance_v2.md`
