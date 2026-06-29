# Calibration Report

Generated: 2026-06-27 17:45:48

Probabilities are normalized independently inside every race before calibration measurement. ECE uses 10 fixed-width bins.

| split | model | calibration_error | brier_score | log_loss |
| --- | --- | --- | --- | --- |
| validation | logistic | 0.0169 | 0.1029 | 0.3411 |
| validation | catboost | 0.0257 | 0.0925 | 0.3092 |
| validation | xgboost | 0.0209 | 0.1030 | 0.3417 |
| validation | ensemble | 0.0278 | 0.0981 | 0.3277 |
| test | logistic | 0.0294 | 0.1144 | 0.3713 |
| test | catboost | 0.0451 | 0.1027 | 0.3363 |
| test | xgboost | 0.0400 | 0.1153 | 0.3741 |
| test | ensemble | 0.0494 | 0.1092 | 0.3571 |
| holdout | logistic | 0.0121 | 0.0873 | 0.3038 |
| holdout | catboost | 0.0211 | 0.0839 | 0.2918 |
| holdout | xgboost | 0.0184 | 0.0885 | 0.3067 |
| holdout | ensemble | 0.0273 | 0.0861 | 0.2981 |
| all_evaluation_folds | logistic | 0.0196 | 0.1055 | 0.3481 |
| all_evaluation_folds | catboost | 0.0315 | 0.0951 | 0.3168 |
| all_evaluation_folds | xgboost | 0.0259 | 0.1059 | 0.3496 |
| all_evaluation_folds | ensemble | 0.0336 | 0.1008 | 0.3351 |

Curve: `reports/calibration_curve.png`; reliability data: `output/calibration_table.csv`. Empty high-probability bins are retained with count zero.
