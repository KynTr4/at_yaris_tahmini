# ROI Simulation Report

Generated: 2026-06-27 18:39:26

Each selected horse receives 1 unit. Decimal `odds` is treated as total return including stake. No commission, limit, slippage, dead heat, or late odds movement is modeled.

| split | model | strategy | total_bets | winning_bets | profit | roi | average_odds | max_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| holdout | catboost | top_1 | 2452.0 | 1421 | 3073.0500 | 1.2533 | 4.3214 | 14.1500 |
| holdout | catboost | top_2 | 4904.0 | 1899 | 3287.9000 | 0.6705 | 5.4722 | 21.7000 |
| holdout | catboost | top_3 | 7324.0 | 2144 | 2486.5500 | 0.3395 | 6.4714 | 33.9000 |
| holdout | ensemble | top_1 | 2452.0 | 1395 | 2879.3000 | 1.1743 | 4.1960 | 17.7000 |
| holdout | ensemble | top_2 | 4904.0 | 1870 | 2992.6500 | 0.6102 | 5.4067 | 26.6000 |
| holdout | ensemble | top_3 | 7324.0 | 2118 | 2291.4000 | 0.3129 | 6.4455 | 41.5500 |
| holdout | logistic | top_1 | 2452.0 | 852 | 97.7000 | 0.0398 | 5.0067 | 111.3000 |
| holdout | logistic | top_2 | 4904.0 | 1342 | -246.5000 | -0.0503 | 5.9880 | 390.5500 |
| holdout | logistic | top_3 | 7324.0 | 1658 | -1075.5000 | -0.1468 | 6.9511 | 1084.5500 |
| holdout | xgboost | top_1 | 2452.0 | 1363 | 2974.2500 | 1.2130 | 4.7238 | 13.8000 |
| holdout | xgboost | top_2 | 4904.0 | 1855 | 3306.2000 | 0.6742 | 6.0793 | 35.2000 |
| holdout | xgboost | top_3 | 7324.0 | 2094 | 2366.3000 | 0.3231 | 7.1096 | 37.6000 |
| test | catboost | top_1 | 4415.0 | 2545 | 6423.2500 | 1.4549 | 4.8499 | 12.1000 |
| test | catboost | top_2 | 8830.0 | 3463 | 7641.6500 | 0.8654 | 6.0895 | 21.9500 |
| test | catboost | top_3 | 13126.0 | 3889 | 7138.8000 | 0.5439 | 7.3167 | 41.1500 |
| test | ensemble | top_1 | 4415.0 | 2483 | 6116.3500 | 1.3854 | 4.7968 | 13.1500 |
| test | ensemble | top_2 | 8830.0 | 3392 | 6919.5000 | 0.7836 | 6.1607 | 21.0500 |
| test | ensemble | top_3 | 13126.0 | 3844 | 6401.9500 | 0.4877 | 7.4610 | 43.5000 |
| test | logistic | top_1 | 4415.0 | 1527 | 656.0500 | 0.1486 | 5.9772 | 51.0000 |
| test | logistic | top_2 | 8830.0 | 2450 | 709.1500 | 0.0803 | 7.2240 | 107.6500 |
| test | logistic | top_3 | 13126.0 | 3046 | 60.2000 | 0.0046 | 8.2898 | 212.7000 |
| test | xgboost | top_1 | 4415.0 | 2474 | 6636.2000 | 1.5031 | 5.4867 | 16.0000 |
| test | xgboost | top_2 | 8830.0 | 3457 | 8206.0500 | 0.9293 | 6.9151 | 19.0500 |
| test | xgboost | top_3 | 13126.0 | 3910 | 7868.1500 | 0.5994 | 8.3096 | 30.4000 |
| validation | catboost | top_1 | 2228.0 | 1429 | 3980.9500 | 1.7868 | 4.9509 | 11.0000 |
| validation | catboost | top_2 | 4456.0 | 1889 | 4744.5000 | 1.0647 | 7.0947 | 10.2500 |
| validation | catboost | top_3 | 6450.0 | 2067 | 4440.7500 | 0.6885 | 8.8471 | 49.4000 |
| validation | ensemble | top_1 | 2228.0 | 1413 | 3831.8000 | 1.7198 | 5.2288 | 11.2000 |
| validation | ensemble | top_2 | 4456.0 | 1881 | 4764.5000 | 1.0692 | 7.4567 | 13.4000 |
| validation | ensemble | top_3 | 6450.0 | 2063 | 4279.1500 | 0.6634 | 9.3509 | 20.4500 |
| validation | logistic | top_1 | 2228.0 | 903 | 1291.9000 | 0.5798 | 6.6111 | 25.9500 |
| validation | logistic | top_2 | 4456.0 | 1440 | 2006.8500 | 0.4504 | 8.1732 | 45.9000 |
| validation | logistic | top_3 | 6450.0 | 1716 | 1906.2500 | 0.2955 | 9.9391 | 89.3000 |
| validation | xgboost | top_1 | 2228.0 | 1338 | 4018.0000 | 1.8034 | 6.7160 | 15.0000 |
| validation | xgboost | top_2 | 4456.0 | 1883 | 5145.6500 | 1.1548 | 8.6207 | 11.3500 |
| validation | xgboost | top_3 | 6450.0 | 2073 | 4631.4500 | 0.7181 | 10.4399 | 30.2000 |

## AGF Value Bet

Not calculated. `agf` has zero populated rows and `agf_percent`/`agf_rank` contain only `not_found`; fabricating an AGF comparison would invalidate the test. The CSV records this strategy as `unavailable_missing_agf`.
