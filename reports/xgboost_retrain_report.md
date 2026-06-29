# XGBoost Retrain Report

Generated: 2026-06-26 22:45:29

## Output

- Production model: `models/xgboost_production.pkl`
- Deprecated marker: `models/benter_baseline_xgb.deprecated.md`

## Features

- Production input features: `20`
- Transformed feature count inside pipeline: `222`
- Categorical: `['track', 'surface', 'race_class']`
- Numeric: `['distance', 'carried_weight', 'draw', 'handicap_rating', 'days_since_last_race', 'last_3_avg_position', 'last_5_avg_position', 'last_10_avg_position', 'surface_win_rate', 'distance_win_rate', 'track_win_rate', 'jockey_horse_win_rate', 'trainer_horse_win_rate', 'weight_change', 'class_change', 'distance_change', 'surface_change']`
- Leakage columns used: `[]`

## Time Split

- Train rows: `347325`
- Test rows: `15700`
- Cutoff date: `2010-04-02`
- Train date range: `1979-03-31` to `2010-04-02`
- Test date range: `2010-04-03` to `2026-12-06`

## Metrics

- Raw log loss: `0.630830`
- Raw Brier: `0.224857`
- Race-normalized log loss: `5.022049`
- Race-normalized Brier: `0.237774`
- Top-1 accuracy: `16.0307%`
- Probability min/max: `0.00349463` / `0.91882968`
