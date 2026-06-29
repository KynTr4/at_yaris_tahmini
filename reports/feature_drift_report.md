# Feature Drift Report

Generated: 2026-06-29 12:51:34

Overall feature drift: **CRITICAL**.

| feature | feature_type | current_rows | reference_rows | current_mean | reference_mean | current_median | reference_median | current_std | reference_std | current_min | reference_min | current_max | reference_max | current_missing_rate | reference_missing_rate | unseen_category_rate | psi | js_distance | kl_divergence | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| track | categorical | 180 | 554 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | 0.0000 | 0.0000 | 1.0000 | 38.8434 | 0.6931 | 20.0363 | CRITICAL |
| distance | numeric | 180 | 554 | 1595.0000 | 1546.3899 | 1500.0000 | 1500.0000 | 348.8649 | 331.4110 | 1200.0000 | 1000.0000 | 2200.0000 | 2400.0000 | 0.0000 | 0.0000 | N/A | 7.6587 | 0.1404 | 1.7264 | CRITICAL |
| surface | categorical | 180 | 554 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | 0.0000 | 0.0812 | 0.0000 | 2.3267 | 0.0745 | 0.2672 | CRITICAL |
| race_class | categorical | 180 | 554 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | 0.0000 | 0.0000 | 1.0000 | 35.1564 | 0.6931 | 18.1104 | CRITICAL |
| carried_weight | numeric | 180 | 554 | 56.0833 | 56.5171 | 56.5000 | 57.0000 | 3.0382 | 2.1650 | 50.0000 | 50.0000 | 63.0000 | 63.0000 | 0.0000 | 0.0000 | N/A | 0.5477 | 0.0623 | 0.2941 | CRITICAL |
| draw | numeric | 180 | 554 | 6.0000 | 6.0923 | 6.0000 | 6.0000 | 3.8129 | 3.7560 | 1.0000 | 1.0000 | 20.0000 | 19.0000 | 0.0444 | 0.0812 | N/A | 0.0406 | 0.0048 | 0.0221 | PASS |
| handicap_rating | numeric | 180 | 554 | 48.1959 | 67.5064 | 50.0000 | 71.0000 | 19.9044 | 24.1675 | 7.0000 | 0.0000 | 110.0000 | 108.0000 | 0.1778 | 0.0199 | N/A | 1.0328 | 0.1190 | 0.4676 | CRITICAL |
| days_since_last_race | numeric | 180 | 554 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | 1.0000 | 1.0000 | N/A | N/A | N/A | N/A | PASS |
| last_3_avg_position | numeric | 180 | 554 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | 1.0000 | 1.0000 | N/A | N/A | N/A | N/A | PASS |
| last_5_avg_position | numeric | 180 | 554 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | 1.0000 | 1.0000 | N/A | N/A | N/A | N/A | PASS |
| last_10_avg_position | numeric | 180 | 554 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | 1.0000 | 1.0000 | N/A | N/A | N/A | N/A | PASS |
| surface_win_rate | numeric | 180 | 554 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | 1.0000 | 1.0000 | N/A | N/A | N/A | N/A | PASS |
| distance_win_rate | numeric | 180 | 554 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | 1.0000 | 1.0000 | N/A | N/A | N/A | N/A | PASS |
| track_win_rate | numeric | 180 | 554 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | 1.0000 | 1.0000 | N/A | N/A | N/A | N/A | PASS |
| jockey_horse_win_rate | numeric | 180 | 554 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | 1.0000 | 1.0000 | N/A | N/A | N/A | N/A | PASS |
| trainer_horse_win_rate | numeric | 180 | 554 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | 1.0000 | 1.0000 | N/A | N/A | N/A | N/A | PASS |
| weight_change | numeric | 180 | 554 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | 1.0000 | 1.0000 | N/A | N/A | N/A | N/A | PASS |
| class_change | numeric | 180 | 554 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | N/A | 0.0000 | 0.0000 | 0.0000 | PASS |
| distance_change | numeric | 180 | 554 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | 1.0000 | 1.0000 | N/A | N/A | N/A | N/A | PASS |
| surface_change | numeric | 180 | 554 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | N/A | 0.0000 | 0.0000 | 0.0000 | PASS |