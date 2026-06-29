# XGBoost Feature Compatibility Report

Generated: 2026-06-26 22:45:24

## Existing Model

- File: `models/benter_baseline_xgb.pkl`
- Type: `xgboost.sklearn.XGBClassifier`
- `n_features_in_`: `222`
- Booster feature count: `222`
- Booster feature names available: `False`

## 222 Feature Finding

The existing XGBoost pickle is a bare `XGBClassifier`, not a preprocessing pipeline. It expects the post-transform matrix with 222 columns. The model does not retain feature names in its booster, so the named 222-feature list was reconstructed from the saved Logistic Regression pipeline preprocessor, which uses the same 20 production input columns.

- Reconstructed transformed feature count: `222`
- First transformed features:

  - `num__distance`
  - `num__carried_weight`
  - `num__draw`
  - `num__handicap_rating`
  - `num__days_since_last_race`
  - `num__last_3_avg_position`
  - `num__last_5_avg_position`
  - `num__last_10_avg_position`
  - `num__surface_win_rate`
  - `num__distance_win_rate`
  - `num__track_win_rate`
  - `num__jockey_horse_win_rate`
  - `num__trainer_horse_win_rate`
  - `num__weight_change`
  - `num__class_change`
  - `num__distance_change`
  - `num__surface_change`
  - `cat__track_Adana`
  - `cat__track_Ankara`
  - `cat__track_Bursa`
  - `cat__track_Diyarbakır`
  - `cat__track_Elazığ`
  - `cat__track_Meydan Dubai`
  - `cat__track_Rusya`
  - `cat__track_İstanbul`
  - `cat__track_İzmir`
  - `cat__track_Şanlıurfa`
  - `cat__surface_K:`
  - `cat__surface_K:Islak`
  - `cat__surface_K:Nemli`
  - `cat__surface_K:Nemli  10.1`
  - `cat__surface_K:Nemli  10.2`
  - `cat__surface_K:Nemli  10.3`
  - `cat__surface_K:Nemli  9.8`
  - `cat__surface_K:Normal`
  - `cat__surface_K:Normal  10`
  - `cat__surface_K:Normal  10.1`
  - `cat__surface_K:Normal  10.2`
  - `cat__surface_K:Normal  10.3`
  - `cat__surface_K:Normal  9.5`

## Dataset Compatibility

- Final dataset columns: `62`
- Production feature columns requested: `20`
- Missing production features: `[]`
- Leakage intersections in production features: `[]`

## Decision

The old XGBoost model is marked deprecated because it cannot accept the live 20-column prediction dataframe directly. A new production XGBoost pipeline is trained below with its own preprocessor and saved as `models/xgboost_production.pkl`.
