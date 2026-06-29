# Daily Shadow Report

Generated: 2026-06-29 12:51:34

- Mode: `shadow_mode`
- Pipeline status: **FAIL**
- Archived predictions: **734**
- Latest-run races: **67**
- Missed eligible races since shadow inception: **0**
- Newly matched results: **0**
- Completed shadow days: **2 / 90**
- Model retraining: **disabled**

| model | races | top1_accuracy | top3_accuracy | top5_accuracy | log_loss | brier_score | roc_auc | calibration_error |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| logistic | 8 | 0.1250 | 0.5000 | 0.7500 | 0.2394 | 0.0629 | 0.7049 | 0.0120 |
| catboost | 8 | 0.2500 | 0.3750 | 0.7500 | 0.2372 | 0.0624 | 0.7072 | 0.0378 |
| xgboost | 8 | 0.2500 | 0.5000 | 0.5000 | 0.2411 | 0.0629 | 0.6742 | 0.0034 |
| ensemble | 8 | 0.3750 | 0.5000 | 0.7500 | 0.2389 | 0.0626 | 0.6875 | 0.0045 |