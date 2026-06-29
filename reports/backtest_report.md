# DEPRECATED — Production Backtest Report

> Deprecated on 2026-06-27. This report used the incomplete final dataset that
> omitted 2024 and 2025. Use `reports/backtest_report_v2.md` instead.

# Production Backtest Report

Generated: 2026-06-27 17:45:48

## Executive Decision

- Production ready: **No, not yet**. The temporal test ran successfully, but 2024 and 2025 are completely absent and there is a 10-year gap before the 2026 holdout.
- Best holdout model: **catboost**.
- Expected winner accuracy from the 2026 holdout: **33.50%** across `203` races.
- Observed top-1 ROI under stated assumptions: **27.04%**. This is descriptive, not a guaranteed live return.
- Highest SHAP contributors: catboost: handicap_rating, last_3_avg_position, race_class, surface, days_since_last_race; logistic: race_class, track, handicap_rating, last_3_avg_position, last_10_avg_position; xgboost: handicap_rating, last_3_avg_position, race_class, days_since_last_race, surface.

## Temporal Design

| split | evaluation_year | train_rows | train_races | train_max_date | evaluation_rows | evaluation_races | evaluation_min_date | evaluation_max_date |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| validation | 2008 | 237125 | 27353 | 2007-12-31 | 13754 | 1959 | 2008-01-01 | 2008-12-31 |
| test | 2009 | 250879 | 29312 | 2008-12-31 | 7784 | 1298 | 2009-01-01 | 2009-12-31 |
| holdout | 2026 | 263777 | 31778 | 2014-12-11 | 1906 | 203 | 2026-06-13 | 2026-06-26 |

Every fold was retrained from scratch with `train_date < evaluation_date`. Saved production model predictions were not reused. The requested 2024 validation and 2025 test could not be run because both years contain zero rows.

## Data Integrity

- Source rows/columns: `363499` / `62`.
- Backtest as-of date: `2026-06-27`; future-dated rows excluded: `749`.
- Completed valid-race rows evaluated/trained: `265683`.
- Excluded races without exactly one winner or with fewer than two runners: `22122`.
- Duplicate horse/race rows in source: `0`.
- Leakage columns intersecting model features: `[]`.
- AGF coverage: `0`; AGF value-bet test unavailable.

## Error Analysis

| model | lost_races | agf_favorite_analysis | predicted_horse_jockey_change_rate | predicted_horse_surface_change_rate | predicted_horse_distance_change_rate | predicted_horse_steward_incident_rate | actual_winner_jockey_change_rate | actual_winner_surface_change_rate | actual_winner_distance_change_rate | actual_winner_steward_incident_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| logistic | 2074 | unavailable | 0.0029 | 0.4069 | 0.7965 | 0.0000 | 0.0020 | 0.4156 | 0.7847 | 0.0000 |
| catboost | 1752 | unavailable | 0.0017 | 0.4070 | 0.8082 | 0.0000 | 0.0020 | 0.4156 | 0.7847 | 0.0000 |
| xgboost | 1838 | unavailable | 0.0011 | 0.4102 | 0.8188 | 0.0000 | 0.0020 | 0.4156 | 0.7847 | 0.0000 |
| ensemble | 1817 | unavailable | 0.0022 | 0.3913 | 0.8129 | 0.0000 | 0.0020 | 0.4156 | 0.7847 | 0.0000 |

AGF-favorite loss analysis is unavailable. Commissioner, jockey, surface and distance indicators are reported as association rates only; they do not establish causality.

## Weaknesses And Final Work

- Backfill 2017-2025, especially 2024 and 2025, then rerun the intended recent-year validation/test.
- Repair AGF ingestion before enabling value betting; preserve timestamped pre-race AGF snapshots.
- Confirm that historical odds are genuinely available pre-bet and encode dead heats, scratches, deductions, commissions and stake limits.
- Investigate the severe 2016-to-2026 distribution gap and monitor live calibration/drift.
- Use the selected model only after those gates pass; current results justify shadow mode, not unattended wagering.

## Artifacts

- `output/backtest_predictions.csv`
- `output/model_scores.csv`
- `output/roi_simulation.csv`
- `output/calibration_table.csv`
- `reports/model_comparison.md`
- `reports/calibration_report.md`
- `reports/calibration_curve.png`
- `reports/roi_report.md`
- `reports/feature_importance.md`
