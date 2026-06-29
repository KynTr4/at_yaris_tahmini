# ROI Simulation Report

Generated: 2026-06-27 17:45:48

Each selected horse receives 1 unit. Decimal `odds` is treated as total return including stake. No commission, limit, slippage, dead heat, or late odds movement is modeled.

| split | model | strategy | total_bets | winning_bets | profit | roi | average_odds | max_drawdown |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| holdout | catboost | top_1 | 203.0 | 68 | 54.9000 | 0.2704 | 4.5047 | 21.7000 |
| holdout | catboost | top_2 | 406.0 | 106 | 13.0500 | 0.0321 | 5.4323 | 29.3500 |
| holdout | catboost | top_3 | 606.0 | 134 | -34.8000 | -0.0574 | 6.4557 | 60.1500 |
| holdout | ensemble | top_1 | 203.0 | 68 | 52.1500 | 0.2569 | 4.2478 | 18.7500 |
| holdout | ensemble | top_2 | 406.0 | 107 | 14.7500 | 0.0363 | 5.3026 | 28.6500 |
| holdout | ensemble | top_3 | 606.0 | 135 | -25.2000 | -0.0416 | 6.5505 | 65.8000 |
| holdout | logistic | top_1 | 203.0 | 51 | -58.9500 | -0.2904 | 5.1067 | 60.0000 |
| holdout | logistic | top_2 | 406.0 | 85 | -122.4000 | -0.3015 | 6.2661 | 122.4000 |
| holdout | logistic | top_3 | 606.0 | 122 | -109.8500 | -0.1813 | 7.3100 | 128.3000 |
| holdout | xgboost | top_1 | 203.0 | 61 | -7.0500 | -0.0347 | 4.8315 | 33.5000 |
| holdout | xgboost | top_2 | 406.0 | 96 | -43.0000 | -0.1059 | 6.2110 | 62.2000 |
| holdout | xgboost | top_3 | 606.0 | 125 | -92.3000 | -0.1523 | 7.2214 | 93.3500 |
| test | catboost | top_1 | 1298.0 | 712 | 930.5000 | 0.7169 | 3.5332 | 11.1000 |
| test | catboost | top_2 | 2596.0 | 981 | 824.2000 | 0.3175 | 4.5886 | 19.2000 |
| test | catboost | top_3 | 3800.0 | 1118 | 404.3500 | 0.1064 | 5.6143 | 42.7000 |
| test | ensemble | top_1 | 1298.0 | 685 | 754.8000 | 0.5815 | 3.3945 | 11.0000 |
| test | ensemble | top_2 | 2596.0 | 958 | 727.5000 | 0.2802 | 4.5475 | 28.7000 |
| test | ensemble | top_3 | 3800.0 | 1099 | 226.5000 | 0.0596 | 5.5463 | 78.5500 |
| test | logistic | top_1 | 1298.0 | 588 | 381.5000 | 0.2939 | 3.5495 | 20.8500 |
| test | logistic | top_2 | 2596.0 | 880 | 284.1500 | 0.1095 | 4.5500 | 70.0500 |
| test | logistic | top_3 | 3800.0 | 1049 | -53.6500 | -0.0141 | 5.5737 | 149.5500 |
| test | xgboost | top_1 | 1298.0 | 671 | 827.1500 | 0.6372 | 3.5598 | 10.9000 |
| test | xgboost | top_2 | 2596.0 | 949 | 730.6500 | 0.2815 | 4.6737 | 34.8000 |
| test | xgboost | top_3 | 3800.0 | 1101 | 282.3000 | 0.0743 | 5.7108 | 76.3000 |
| validation | catboost | top_1 | 1959.0 | 928 | 1814.5500 | 0.9263 | 4.3688 | 19.1500 |
| validation | catboost | top_2 | 3918.0 | 1322 | 1742.7500 | 0.4448 | 5.5108 | 32.7000 |
| validation | catboost | top_3 | 5740.0 | 1588 | 1448.2500 | 0.2523 | 6.6464 | 112.5000 |
| validation | ensemble | top_1 | 1959.0 | 890 | 1537.6500 | 0.7849 | 4.2633 | 27.8500 |
| validation | ensemble | top_2 | 3918.0 | 1298 | 1572.9500 | 0.4015 | 5.5083 | 69.7500 |
| validation | ensemble | top_3 | 5740.0 | 1568 | 1297.0500 | 0.2260 | 6.6595 | 162.9500 |
| validation | logistic | top_1 | 1959.0 | 747 | 349.7500 | 0.1785 | 4.2823 | 84.4000 |
| validation | logistic | top_2 | 3918.0 | 1191 | 642.7500 | 0.1641 | 5.5366 | 120.5000 |
| validation | logistic | top_3 | 5740.0 | 1474 | 523.0500 | 0.0911 | 6.7050 | 326.6500 |
| validation | xgboost | top_1 | 1959.0 | 890 | 1538.9000 | 0.7856 | 4.4366 | 23.1000 |
| validation | xgboost | top_2 | 3918.0 | 1284 | 1544.7500 | 0.3943 | 5.6994 | 65.3000 |
| validation | xgboost | top_3 | 5740.0 | 1548 | 1222.9000 | 0.2130 | 6.8793 | 168.2500 |

## AGF Value Bet

Not calculated. `agf` has zero populated rows and `agf_percent`/`agf_rank` contain only `not_found`; fabricating an AGF comparison would invalidate the test. The CSV records this strategy as `unavailable_missing_agf`.
