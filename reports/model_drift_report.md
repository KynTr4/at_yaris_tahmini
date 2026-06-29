# Model Drift Report

Generated: 2026-06-29 12:51:34

Overall prediction drift: **CRITICAL**. Reference window is the previous 30 calendar days.

| drift_type | model | current_rows | reference_rows | psi | js_distance | kl_divergence | winner_probability_shift | confidence_shift | winner_rate_shift | class_js_distance | scratch_rate_shift | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| prediction | logistic | 180 | 554 | 0.3189 | 0.0108 | 0.0393 | N/A | 0.0031 | N/A | N/A | N/A | CRITICAL |
| prediction | catboost | 180 | 554 | 0.0502 | 0.0024 | 0.0100 | N/A | 0.0112 | N/A | N/A | N/A | PASS |
| prediction | xgboost | 180 | 554 | 0.2845 | 0.0103 | 0.0378 | N/A | 0.0107 | N/A | N/A | N/A | CRITICAL |
| prediction | ensemble | 180 | 554 | 0.2930 | 0.0120 | 0.0448 | N/A | 0.0004 | N/A | N/A | N/A | CRITICAL |
| target | all | 0 | 131 | N/A | N/A | N/A | N/A | N/A | N/A | 0.6931 | 0.0000 | INSUFFICIENT_DATA |