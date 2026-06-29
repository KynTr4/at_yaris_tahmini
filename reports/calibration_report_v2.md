# Calibration Report

Generated: 2026-06-27 18:39:26

Probabilities are normalized independently inside every race before calibration measurement. ECE uses 10 fixed-width bins.

| split | model | calibration_error | brier_score | log_loss |
| --- | --- | --- | --- | --- |
| validation | logistic | 0.0187 | 0.1160 | 0.3791 |
| validation | catboost | 0.0540 | 0.0895 | 0.2946 |
| validation | xgboost | 0.0625 | 0.1042 | 0.3360 |
| validation | ensemble | 0.0737 | 0.0999 | 0.3266 |
| test | logistic | 0.0143 | 0.0923 | 0.3137 |
| test | catboost | 0.0492 | 0.0752 | 0.2527 |
| test | xgboost | 0.0534 | 0.0853 | 0.2823 |
| test | ensemble | 0.0549 | 0.0825 | 0.2762 |
| holdout | logistic | 0.0203 | 0.0886 | 0.3033 |
| holdout | catboost | 0.0484 | 0.0708 | 0.2401 |
| holdout | xgboost | 0.0507 | 0.0817 | 0.2734 |
| holdout | ensemble | 0.0573 | 0.0785 | 0.2652 |
| all_evaluation_folds | logistic | 0.0169 | 0.0956 | 0.3227 |
| all_evaluation_folds | catboost | 0.0498 | 0.0765 | 0.2567 |
| all_evaluation_folds | xgboost | 0.0543 | 0.0877 | 0.2896 |
| all_evaluation_folds | ensemble | 0.0591 | 0.0846 | 0.2823 |

Curve: `reports/calibration_curve_v2.png`; reliability data: `output/calibration_table_v2.csv`. Empty high-probability bins are retained with count zero.
