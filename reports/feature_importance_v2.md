# Feature Importance

Generated: 2026-06-27 18:39:26

Importance is computed on the 2026 holdout model trained on all valid races before 2026. One-hot contributions are aggregated back to the 20 raw production features.

## Logistic

| feature | shap_mean_abs | gain_importance | permutation_importance |
| --- | --- | --- | --- |
| race_class | 1.116018 | N/A | 0.038914 |
| surface | 0.627837 | N/A | 0.001084 |
| handicap_rating | 0.481947 | N/A | 0.037461 |
| track | 0.382876 | N/A | 0.000785 |
| last_3_avg_position | 0.314075 | N/A | 0.010892 |
| draw | 0.227272 | N/A | 0.003734 |
| last_10_avg_position | 0.084568 | N/A | 0.000641 |
| days_since_last_race | 0.081637 | N/A | 0.001665 |
| surface_win_rate | 0.071097 | N/A | -0.000320 |
| surface_change | 0.057507 | N/A | 0.000392 |
| track_win_rate | 0.049921 | N/A | 0.000077 |
| class_change | 0.039944 | N/A | 0.000697 |
| jockey_horse_win_rate | 0.038820 | N/A | 0.000065 |
| last_5_avg_position | 0.034094 | N/A | -0.000066 |
| distance | 0.018313 | N/A | -0.000037 |
| trainer_horse_win_rate | 0.014853 | N/A | -0.000266 |
| distance_change | 0.010992 | N/A | 0.000073 |
| weight_change | 0.004382 | N/A | -0.000032 |
| distance_win_rate | 0.004265 | N/A | -0.000037 |
| carried_weight | 0.000322 | N/A | 0.000001 |

## Catboost

| feature | shap_mean_abs | gain_importance | permutation_importance |
| --- | --- | --- | --- |
| handicap_rating | 0.816888 | 37.079613 | 0.405760 |
| last_3_avg_position | 0.224420 | 7.630504 | 0.009249 |
| race_class | 0.216119 | 11.562742 | 0.157284 |
| draw | 0.153118 | 16.079387 | 0.000997 |
| track | 0.132770 | 7.512850 | 0.002393 |
| days_since_last_race | 0.100672 | 1.936273 | 0.002246 |
| last_5_avg_position | 0.084154 | 1.780010 | 0.001244 |
| surface | 0.080765 | 3.851085 | 0.001144 |
| carried_weight | 0.071950 | 1.874620 | 0.002657 |
| surface_win_rate | 0.061560 | 1.848177 | 0.005168 |
| last_10_avg_position | 0.047482 | 1.923362 | 0.003393 |
| track_win_rate | 0.040439 | 1.448368 | 0.003353 |
| jockey_horse_win_rate | 0.039000 | 0.517171 | 0.001099 |
| distance | 0.029549 | 1.110640 | 0.002731 |
| trainer_horse_win_rate | 0.029508 | 1.281213 | 0.002806 |
| distance_change | 0.027158 | 1.291261 | 0.001227 |
| surface_change | 0.024735 | 0.158091 | 0.000375 |
| distance_win_rate | 0.017156 | 0.498635 | 0.001361 |
| weight_change | 0.012333 | 0.481345 | 0.001015 |
| class_change | 0.006075 | 0.134651 | 0.000200 |

## Xgboost

| feature | shap_mean_abs | gain_importance | permutation_importance |
| --- | --- | --- | --- |
| handicap_rating | 1.209120 | 1092.974243 | 0.254934 |
| race_class | 0.426848 | 13134.738626 | 0.114931 |
| last_3_avg_position | 0.322417 | 2700.863037 | -0.004882 |
| draw | 0.180410 | 1668.990356 | 0.001007 |
| track | 0.111551 | 2055.327042 | 0.003702 |
| surface | 0.088282 | 779.284393 | 0.001943 |
| days_since_last_race | 0.087869 | 237.500031 | 0.000693 |
| surface_win_rate | 0.061077 | 302.382904 | 0.002147 |
| carried_weight | 0.055339 | 251.913635 | 0.003336 |
| track_win_rate | 0.050079 | 398.404297 | 0.003258 |
| trainer_horse_win_rate | 0.029496 | 306.773682 | 0.004975 |
| distance | 0.018424 | 103.585091 | 0.002818 |
| last_10_avg_position | 0.018288 | 129.075897 | -0.001721 |
| distance_win_rate | 0.018040 | 77.459618 | 0.001326 |
| class_change | 0.017012 | 204.609146 | 0.001604 |
| jockey_horse_win_rate | 0.016816 | 162.666016 | -0.001961 |
| weight_change | 0.012666 | 95.189209 | 0.002644 |
| last_5_avg_position | 0.012445 | 209.892609 | -0.000816 |
| distance_change | 0.006473 | 48.254639 | 0.000514 |
| surface_change | 0.003729 | 106.216454 | 0.000568 |

Logistic regression has no tree gain; its gain cells are intentionally N/A. CatBoost gain is native PredictionValuesChange; XGBoost gain is booster split gain.
