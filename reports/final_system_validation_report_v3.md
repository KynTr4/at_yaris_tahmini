# Final System Validation Report v3

Generated: 2026-06-26 22:49 Europe/Istanbul

Project root: `C:\Users\Agoraa\Documents\at_yaris_tahmini`

## Executive Verdict

XGBoost fallback was removed and real XGBoost production predictions are now generated.

Evidence:

- New model exists: `models/xgboost_production.pkl`
- Model type: `sklearn.pipeline.Pipeline`
- Production model input features: `20`
- Internal transformed feature count: `222`
- Old model marked deprecated: `models/benter_baseline_xgb.deprecated.md`
- Latest `daily_update.ps1` exit code: `0`
- Latest log contains: `XGBoost production model predictions generated without fallback.`
- Latest log has no fallback attempt lines.
- Latest log has no `[ERROR]` lines and no `failed with exit code` lines.
- Active `failed_updates.csv` rows: `0`

## Produced Files

| File | Exists | Modified |
|---|---:|---|
| `models/xgboost_production.pkl` | yes | `2026-06-26 22:45:29` |
| `models/benter_baseline_xgb.deprecated.md` | yes | `2026-06-26 22:45:29` |
| `reports/xgboost_feature_compatibility_report.md` | yes | `2026-06-26 22:45:24` |
| `reports/xgboost_retrain_report.md` | yes | `2026-06-26 22:45:29` |
| `output/model_predictions.csv` | yes | `2026-06-26 22:48:37` |

## Compatibility Finding

The previous model `models/benter_baseline_xgb.pkl` is a bare `XGBClassifier`.

- `n_features_in_`: `222`
- Booster feature count: `222`
- Booster feature names available: `false`
- It does not include the preprocessing pipeline.

The 222 transformed features were reconstructed from the saved Logistic Regression pipeline preprocessor. Those 222 columns are not raw dataset columns; they are generated from the same 20 production features through numeric passthrough/imputation plus one-hot categorical expansion.

Decision: the old XGBoost model is deprecated for production inference. The new `models/xgboost_production.pkl` wraps preprocessing and XGBoost together, so `predict_today.py` can pass the live 20-feature dataframe directly.

## Retraining

Training source:

- Dataset: `output/final_benter_dataset.csv`
- Dataset rows: `363,499`
- Usable completed rows: `363,025`
- Target: `finish_position == 1`
- Split: time-based
- Train rows: `347,325`
- Test rows: `15,700`
- Cutoff date: `2010-04-02`
- Train range: `1979-03-31` to `2010-04-02`
- Test range: `2010-04-03` to `2026-12-06`

No leakage columns were used. Production features remain:

`track`, `distance`, `surface`, `race_class`, `carried_weight`, `draw`, `handicap_rating`, `days_since_last_race`, `last_3_avg_position`, `last_5_avg_position`, `last_10_avg_position`, `surface_win_rate`, `distance_win_rate`, `track_win_rate`, `jockey_horse_win_rate`, `trainer_horse_win_rate`, `weight_change`, `class_change`, `distance_change`, `surface_change`.

Retrain metrics:

- Raw log loss: `0.630830`
- Raw Brier: `0.224857`
- Race-normalized log loss: `5.022049`
- Race-normalized Brier: `0.237774`
- Top-1 accuracy: `16.0307%`
- Probability min/max on test: `0.00349463` / `0.91882968`

## Prediction Validation

`output/model_predictions.csv`:

- Rows: `13,488`
- Duplicate `race_id,horse_id`: `0`
- Columns now include `ensemble_norm_prob`
- XGBoost probability min: `0.00062139047`
- XGBoost probability max: `0.7558185458183289`
- Ensemble probability min: `0.0011065891393042`
- Ensemble probability max: `1.0`

Race-normalized probability checks:

| Column | Min Sum | Max Sum | Max Abs Diff From 1 | Bad Races > 1e-6 |
|---|---:|---:|---:|---:|
| `lr_norm_prob` | `0.9999999999999992` | `1.0000000000000002` | `7.77e-16` | `0` |
| `xgb_norm_prob` | `0.999999999999999` | `1.0000000000000002` | `9.99e-16` | `0` |
| `cb_norm_prob` | `0.9999999999999992` | `1.0000000000000002` | `7.77e-16` | `0` |
| `ensemble_norm_prob` | `0.9999999999999992` | `1.0000000000000002` | `7.77e-16` | `0` |

## Daily Update Validation

Latest `daily_update.ps1` run:

- Exit code: `0`
- Pipeline success marker: yes
- Child exit-code lines: `13`
- `predict_today.py` exit code: `0`
- XGBoost without fallback log line: yes
- Fallback attempt lines: `0`
- Error lines: `0`
- Active `failed_updates.csv` rows: `0`
- SQLite integrity: `ok`

Child scripts:

| Script | Exit Code |
|---|---:|
| `update_race_programs.py` | `0` |
| `update_profiles.py` | `0` |
| `update_races.py` | `0` |
| `update_statistics.py` | `0` |
| `download_agfv2.py --today` | `0` |
| `komiser.py --today` | `0` |
| `process_komiser.py --today` | `0` |
| `update_track_conditions.py` | `0` |
| `update_workouts.py` | `0` |
| `update_results.py` | `0` |
| `incremental_feature_engineering.py` | `0` |
| `build_final_dataset.py` | `0` |
| `predict_today.py` | `0` |

## Current Status

Ready for daily automation with real XGBoost predictions.

The previous XGBoost blocker is resolved:

- no uniform fallback,
- no zero-filled missing feature hack,
- no leakage features,
- production XGBoost accepts the same 20 live features as the prediction path,
- predictions include CatBoost, Logistic, XGBoost, and ensemble normalized probabilities.

## Remaining Notes

- Some foreign race entries still have sparse one-horse race groups because of the upstream program structure. They normalize correctly, but they are less useful analytically.
- The old `models/benter_baseline_xgb.pkl` is kept for audit/backward reference only and should not be used by production prediction.

