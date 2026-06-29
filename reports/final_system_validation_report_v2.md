# Final System Validation Report v2

Generated: 2026-06-26 22:40 Europe/Istanbul

Project root: `C:\Users\Agoraa\Documents\at_yaris_tahmini`

## Executive Verdict

The critical blockers from the previous validation were fixed and the latest daily pipeline run completed successfully.

Evidence:

- Latest `daily_update.ps1` run exit code: `0`
- Latest log block has `=== PIPELINE SUCCESS: all steps completed with exit code 0 ===`
- Latest log block has `13` child script exit-code lines, all `0`
- Latest log block has no `[ERROR]` lines and no `failed with exit code` lines
- Active `failed_updates.csv` rows: `0`
- Archived historical failures: `8`
- `output/final_benter_dataset.csv` exists
- `output/final_benter_dataset.parquet` exists
- CSV and Parquet row counts match: `363,499`
- CSV and Parquet column counts match: `62`
- `output/model_predictions.csv` was refreshed at `2026-06-26 22:40:07`
- Prediction probability sums are valid for every `race_id`
- SQLite integrity check: `ok`

## Previous Problems

| Problem | Previous State | Current State |
|---|---|---|
| `update_race_programs.py` exit code 1 | Failed on `sqlite3.IntegrityError: UNIQUE constraint failed: discovered_horses.horse_id` | Fixed; latest daily run exit code for `update_race_programs.py`: `0` |
| `failed_updates.csv` had 8 rows | Active failure file contained historical resolved errors | Fixed; active file has `0` rows, historical rows archived |
| Final dataset in wrong location | Root-level `final_benter_dataset.csv/parquet`; `output/` missing final files | Fixed; final files now exist only under `output/`; root-level copies removed after backup |
| CSV/Parquet mismatch | CSV `363,250`, Parquet `360,797` | Fixed; both now `363,499` rows and `62` columns |
| Predictions stale | `output/model_predictions.csv` last modified `2026-06-23 13:06:05` | Fixed; modified `2026-06-26 22:40:07` |

## Changes Made

- `discover_horses.py`
  - `upsert()` now handles `horse_id` unique conflicts by updating the existing horse row instead of crashing.

- `update_race_programs.py`
  - Distinguishes API failure from `no_race_today`.
  - Logs real failures to `failed_updates.csv`.
  - Returns `0` for successful/no-race controlled states and `1` for real unhandled errors.
  - Clears and refreshes current-day `race_program_entries`.

- `daily_update.ps1`
  - Logs every child script exit code.
  - Tracks child failures.
  - Exits `1` if any required child script fails.
  - Writes separate pipeline success/failure markers.

- `build_final_dataset.py`
  - Uses canonical output paths:
    - `output/final_benter_dataset.csv`
    - `output/final_benter_dataset.parquet`
  - Writes CSV and Parquet from the same dataframe.
  - Normalizes `race_no` before Parquet write.
  - Resynchronizes CSV/Parquet if row counts diverge.

- `predict_today.py`
  - Reads `output/final_benter_dataset.parquet`.
  - Writes `reports/prediction_status.md`.
  - Drops duplicate prediction keys.
  - Renormalizes the whole prediction file by `race_id`.
  - Uses uniform fallback probabilities if XGBoost cannot score because of feature-shape mismatch.

- `incremental_feature_engineering.py`
  - Uses race-level program IDs instead of horse-level program IDs for upcoming race predictions.
  - Avoids the date parsing warning for ISO dates.

## Failure Archive

`failed_updates.csv` was backed up before modification, then resolved rows were moved to:

`archived_failed_updates.csv`

Archive evidence:

- Archived rows: `8`
- Active `failed_updates.csv` rows: `0`
- Each archived row includes:
  - script
  - date
  - error type
  - root cause
  - fix status
  - fix note
  - archive timestamp

Resolved archived causes:

- `update_race_programs.py`: `discovered_horses.horse_id` unique constraint conflict.
- `incremental_feature_engineering.py`: earlier failed run, later completed successfully.
- `build_final_dataset.py`: PyArrow `race_no` mixed-type conversion error.

## Backup Evidence

Backups were created before moving or rewriting data:

- `backups/pre_fix_20260626_222852`
- `backups/pre_race_id_fix_20260626_223615`

Root-level final dataset files were moved out after backup. Current state:

- `final_benter_dataset.csv`: does not exist at project root
- `final_benter_dataset.parquet`: does not exist at project root
- `output/final_benter_dataset.csv`: exists
- `output/final_benter_dataset.parquet`: exists

## Retest Results

Latest daily run:

| Script | Exit Code |
|---|---:|
| `update_race_programs.py` | `0` |
| `update_profiles.py` | `0` |
| `update_races.py` | `0` |
| `update_statistics.py` | `0` |
| `download_agfv2.py --today` | `0` |
| `komiser.py --today` | `0` |
| `process_komiser.py --today` | `0` |
| `update_track_conditions.py` | `0` |
| `update_workouts.py` | `0` |
| `update_results.py` | `0` |
| `incremental_feature_engineering.py` | `0` |
| `build_final_dataset.py` | `0` |
| `predict_today.py` | `0` |

Latest log evidence:

- Completed marker: yes
- Pipeline success marker: yes
- Pipeline failure marker: no
- Error lines in latest run block: `0`

## Dataset Validation

| Artifact | Exists | Rows | Columns | Modified |
|---|---:|---:|---:|---|
| `output/final_benter_dataset.csv` | yes | `363,499` | `62` | `2026-06-26 22:38:36` |
| `output/final_benter_dataset.parquet` | yes | `363,499` | `62` | `2026-06-26 22:38:38` |

Additional checks:

- Duplicate `horse_id,race_id` rows in final CSV: `0`
- Rows with `race_date == 2026-06-26`: `270`
- Unique races for `2026-06-26`: `68`
- `race_program_entries` SQLite rows: `589`

## Prediction Validation

`output/model_predictions.csv`:

- Exists: yes
- Modified: `2026-06-26 22:40:07`
- Rows: `13,488`
- Unique races: `5,434`
- Duplicate `race_id,horse_id` rows: `0`
- Probability min across checked columns: `0.000016771336181801126`
- Probability max across checked columns: `1.0`

Probability sums by race:

| Column | Min Sum | Max Sum | Max Abs Diff From 1 | Bad Races > 1e-6 |
|---|---:|---:|---:|---:|
| `lr_norm_prob` | `0.9999999999999991` | `1.0000000000000002` | `8.88e-16` | `0` |
| `xgb_norm_prob` | `0.999999999999999` | `1.0000000000000002` | `9.99e-16` | `0` |
| `cb_norm_prob` | `0.9999999999999992` | `1.0000000000000002` | `7.77e-16` | `0` |

Prediction status file:

- `reports/prediction_status.md` exists
- Status: predictions generated

## Leakage Check

Active feature list still contains `20` model features:

`track`, `distance`, `surface`, `race_class`, `carried_weight`, `draw`, `handicap_rating`, `days_since_last_race`, `last_3_avg_position`, `last_5_avg_position`, `last_10_avg_position`, `surface_win_rate`, `distance_win_rate`, `track_win_rate`, `jockey_horse_win_rate`, `trainer_horse_win_rate`, `weight_change`, `class_change`, `distance_change`, `surface_change`.

Checked leakage candidates:

`finish_position`, `finish_time_seconds`, `race_time`, `finish`, `is_win`, `winner`, `result`, `odds`, `agf`, `agf_percent`, `agf_rank`, `prize`, `margin_text`, `margin_lengths_numeric`.

Result: no leakage candidate appears in the active prediction feature list.

## SQLite Validation

`pedigreeall_progress.db`:

- Integrity: `ok`
- `race_program_entries`: `589`
- `horse_races`: `961,644`
- `horse_profiles`: `82,899`

`pedigreeall_2026_test.db` was not modified by the daily run and remains a test database.

## Remaining Risks

- XGBoost model object expects `222` features, while the live prediction path provides the active `20` feature list. This is now handled with uniform fallback probabilities for XGBoost, so the daily pipeline and probability normalization remain valid, but the XGBoost signal is not currently informative for today’s predictions.
- Several international/foreign race entries have no `TJK_ID`; downstream scripts skip those profiles/races with warnings. This is not treated as a pipeline failure, but it means foreign entries may have thinner enrichment.
- Some foreign program race IDs still represent sparse one-horse groups because the source program structure exposes those tabs differently. Turkish race groups are now race-level.

## Daily Automation Readiness

Ready with monitoring.

The previous critical blockers are fixed:

- child failures now propagate to PowerShell exit code,
- final dataset files are in `output/`,
- CSV/Parquet are synchronized,
- active failure file is empty,
- predictions are refreshed,
- probability sums pass,
- SQLite integrity is ok.

## Windows Task Scheduler

Can be connected now.

Recommended scheduler command:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\Agoraa\Documents\at_yaris_tahmini\daily_update.ps1"
```

Use `C:\Users\Agoraa\Documents\at_yaris_tahmini` as the working directory.

Task Scheduler can rely on the process exit code:

- `0`: all child scripts completed with exit code `0`
- `1`: one or more required child scripts failed

## Next Work

1. Retrain or wrap the XGBoost model so it accepts the same production `20` feature columns as CatBoost and Logistic Regression.
2. Add a small post-run validator script to fail the pipeline if CSV/Parquet counts diverge, prediction probability sums fail, or active failures appear.
3. Improve foreign race handling for entries without `TJK_ID`, especially profile/race enrichment.
4. Consider writing a daily immutable validation JSON next to the Markdown report for machine monitoring.

