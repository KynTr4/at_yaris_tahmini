# Feature Importance

Generated: 2026-06-27 17:45:48

Importance is computed on the 2026 holdout model trained only through 2016. One-hot contributions are aggregated back to the 20 raw production features.

## Logistic

| feature | shap_mean_abs | gain_importance | permutation_importance |
| --- | --- | --- | --- |
| race_class | 0.854382 | N/A | 0.014824 |
| track | 0.446614 | N/A | 0.000606 |
| handicap_rating | 0.421447 | N/A | 0.026629 |
| last_3_avg_position | 0.330678 | N/A | 0.010347 |
| last_10_avg_position | 0.132605 | N/A | 0.002304 |
| surface | 0.108353 | N/A | -0.000016 |
| days_since_last_race | 0.103200 | N/A | 0.000960 |
| draw | 0.076911 | N/A | 0.000498 |
| surface_win_rate | 0.061159 | N/A | 0.001412 |
| surface_change | 0.048138 | N/A | 0.000893 |
| track_win_rate | 0.045637 | N/A | 0.000579 |
| jockey_horse_win_rate | 0.034444 | N/A | -0.000424 |
| distance | 0.017018 | N/A | -0.000108 |
| carried_weight | 0.016405 | N/A | -0.000038 |
| class_change | 0.015890 | N/A | 0.000287 |
| last_5_avg_position | 0.014477 | N/A | -0.000057 |
| weight_change | 0.013236 | N/A | -0.000063 |
| trainer_horse_win_rate | 0.009220 | N/A | 0.000000 |
| distance_change | 0.008959 | N/A | -0.000098 |
| distance_win_rate | 0.007595 | N/A | 0.000000 |

## Catboost

| feature | shap_mean_abs | gain_importance | permutation_importance |
| --- | --- | --- | --- |
| handicap_rating | 0.490981 | 31.322665 | 0.224757 |
| last_3_avg_position | 0.267092 | 11.320668 | 0.009432 |
| race_class | 0.170078 | 9.606033 | 0.063981 |
| surface | 0.145835 | 18.236958 | -0.000085 |
| days_since_last_race | 0.115193 | 3.902615 | 0.001288 |
| last_5_avg_position | 0.092444 | 5.286259 | 0.002053 |
| last_10_avg_position | 0.088004 | 3.941669 | 0.002935 |
| draw | 0.080578 | 1.670406 | 0.000296 |
| carried_weight | 0.067234 | 2.498715 | 0.000262 |
| surface_win_rate | 0.066336 | 2.183676 | 0.002343 |
| track | 0.041455 | 2.223286 | 0.000113 |
| track_win_rate | 0.041453 | 1.597632 | 0.002050 |
| jockey_horse_win_rate | 0.035653 | 1.095249 | 0.000691 |
| weight_change | 0.035609 | 1.087881 | 0.003807 |
| distance | 0.032213 | 0.967662 | 0.000144 |
| distance_win_rate | 0.029224 | 0.742378 | 0.000000 |
| distance_change | 0.026533 | 0.810925 | 0.003531 |
| trainer_horse_win_rate | 0.022126 | 1.045880 | 0.000908 |
| surface_change | 0.021848 | 0.350645 | 0.000238 |
| class_change | 0.007494 | 0.108796 | 0.000283 |

## Xgboost

| feature | shap_mean_abs | gain_importance | permutation_importance |
| --- | --- | --- | --- |
| handicap_rating | 0.630906 | 232.260605 | 0.085142 |
| last_3_avg_position | 0.356544 | 1070.277222 | -0.007180 |
| race_class | 0.277263 | 3289.110094 | 0.038575 |
| days_since_last_race | 0.103424 | 99.347641 | 0.000742 |
| surface | 0.078781 | 1192.779095 | -0.000170 |
| draw | 0.073155 | 75.576828 | -0.001595 |
| carried_weight | 0.066272 | 74.617050 | 0.001451 |
| last_10_avg_position | 0.061276 | 156.556061 | -0.007481 |
| surface_win_rate | 0.058858 | 99.660088 | -0.001417 |
| last_5_avg_position | 0.055386 | 164.716156 | -0.005898 |
| track_win_rate | 0.042334 | 96.762054 | -0.000109 |
| jockey_horse_win_rate | 0.022449 | 61.209301 | -0.002072 |
| weight_change | 0.022349 | 37.023285 | -0.000889 |
| track | 0.021975 | 303.166891 | -0.000291 |
| distance | 0.019301 | 39.167084 | 0.001465 |
| distance_win_rate | 0.010800 | 40.790813 | 0.000000 |
| trainer_horse_win_rate | 0.009602 | 49.434505 | -0.000141 |
| distance_change | 0.006049 | 26.789679 | 0.000252 |
| surface_change | 0.003913 | 44.623837 | -0.000196 |
| class_change | 0.003494 | 59.277439 | 0.000511 |

Logistic regression has no tree gain; its gain cells are intentionally N/A. CatBoost gain is native PredictionValuesChange; XGBoost gain is booster split gain.
