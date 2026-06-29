# Final System Validation Report

Generated: 2026-06-26 22:19 Europe/Istanbul

Project root: `C:\Users\Agoraa\Documents\at_yaris_tahmini`

## Executive Verdict

The latest `daily_update.ps1` run reached the final completion marker, but the system should not be treated as fully successful or ready for unattended daily automation yet.

Evidence:

- Latest log file exists: `logs/update_2026_06_26.log`, size `22,958` bytes, modified `2026-06-26 22:08:33`.
- Latest run block contains `=== COMPLETED AUTOMATED DAILY UPDATE PIPELINE ===`.
- However, latest run also contains a child-script failure: `update_race_programs.py failed with exit code 1`.
- `failed_updates.csv` is not empty: `8` failure rows.
- Requested `output/final_benter_dataset.csv` and `output/final_benter_dataset.parquet` do not exist.
- Actual final dataset files are in the project root, not `output/`.
- `final_benter_dataset.csv` and `final_benter_dataset.parquet` are out of sync.
- `output/model_predictions.csv` was not updated by the latest run.

## Required Checks

| # | Check | Result | Evidence |
|---:|---|---|---|
| 1 | `daily_update.ps1` really successful? | Partially / operationally unsafe | The PowerShell process can report exit code `0`, but the latest log shows `update_race_programs.py failed with exit code 1`; the script does not propagate child failures as a final non-zero exit. |
| 2 | Errors in `logs/update_2026_06_26.log`? | Yes | Full-day log includes warnings and one error: PyArrow `race_no` conversion error at `2026-06-26 22:07:40`; latest run has warnings. |
| 3 | `failed_updates.csv` empty? | No | `8` rows; latest row: `2026-06-26 22:08:17`, `daily_update.ps1`, `update_race_programs.py`, `ExitCodeError`. |
| 4 | `output/final_benter_dataset.csv` exists? | No | Missing. Actual file exists at root: `final_benter_dataset.csv`, `236,843,540` bytes, modified `2026-06-26 22:07:40`. |
| 5 | `output/final_benter_dataset.parquet` exists? | No | Missing. Actual file exists at root: `final_benter_dataset.parquet`, `8,559,395` bytes, modified `2026-06-26 22:01:09`. |
| 6 | `output/model_predictions.csv` updated? | No | Exists but modified `2026-06-23 13:06:05`; latest `predict_today.py` found no races for `2026-06-26`, so it did not regenerate predictions. |
| 7 | Per `race_id` probability sums equal 1? | Yes, for existing prediction file | `5,366` races checked. `lr_norm_prob` max diff `8.88e-16`; `xgb_norm_prob` max diff `1.41e-7`; `cb_norm_prob` max diff `7.77e-16`. No race exceeded `1e-6` tolerance. |
| 8 | Leakage columns in model feature list? | No direct leakage found | `predict_today.py` uses `20` features. No `finish_position`, `finish_time_seconds`, `is_win`, `odds`, `agf`, `agf_percent`, `agf_rank`, `prize`, or margin/result columns in `FEATURE_COLS`. CatBoost and Logistic model feature names match the same safe list. |
| 9 | Duplicate records created? | Mixed | `final_benter_dataset.csv`: `0` duplicates by `horse_id,race_id`. `output/benter_features_base.csv`: `394` duplicates by `horse_id,race_id`. `output/model_predictions.csv`: `1` duplicate by `race_id,horse_id`. |
| 10 | SQLite row counts preserved? | Integrity OK, but no baseline file found | `pedigreeall_progress.db` integrity check: `ok`. Current key counts: `horse_races=960,792`, `horse_profiles=82,878`, `horse_statistics=49,259`, `raw_api_responses=128,055`, `race_program_entries=0`. Because no previous baseline snapshot was present, preservation can only be judged against current integrity and pipeline evidence. |

## Successful Steps

- `download_agfv2.py --today` completed in the latest run.
- `komiser.py --today` completed in the latest run.
- `process_komiser.py --today` completed in the latest run.
- `update_profiles.py`, `update_races.py`, `update_statistics.py`, `update_track_conditions.py`, `update_workouts.py`, and `update_results.py` completed without non-zero exit in the latest run.
- `incremental_feature_engineering.py` completed in the latest run and reported all completed race features up to date.
- `build_final_dataset.py` completed in the latest run and reported no new rows to add.
- `predict_today.py` completed as a process, but did not generate new predictions because no races were found for `2026-06-26` in the Parquet dataset.
- SQLite locking is not currently visible: `pedigreeall_progress.db` passed `PRAGMA integrity_check`.
- Existing prediction probabilities are normalized correctly by race.
- Final CSV has no duplicate `horse_id,race_id` keys.

## Fixed Errors Confirmed

- SQLite locking: no active lock failure appeared in the latest run; database integrity check returned `ok`.
- `incremental_feature_engineering.py`: latest run completed successfully after earlier failure at `22:01:02`.
- `build_final_dataset.py`: latest run completed successfully after earlier PyArrow save failure.
- Data leakage in prediction feature list: no direct result/outcome columns were found in the active feature list.

## Errors Still Present Or Historically Recorded

- `update_race_programs.py` still failed in the latest run:
  - `2026-06-26 22:08:17 [WARNING] Script update_race_programs.py failed with exit code 1.`
- `race_program_entries` table currently has `0` rows.
- Latest run warning:
  - `No race program entries found for today in database.`
- Latest run warning:
  - `No races found in final dataset for today (2026-06-26). Predictions cannot be generated.`
- `failed_updates.csv` still contains historical and latest failures.
- Earlier same-day error remains recorded:
  - `ArrowTypeError`, `Conversion failed for column race_no with type object`.

## Dataset Evidence

| Artifact | Exists | Rows | Modified | Notes |
|---|---:|---:|---|---|
| `final_benter_dataset.csv` | Yes | `363,250` | `2026-06-26 22:07:40` | Root-level file, not under `output/`. |
| `final_benter_dataset.parquet` | Yes | `360,797` | `2026-06-26 22:01:09` | Stale compared with CSV; row count differs by `2,453`. |
| `output/benter_features_base.csv` | Yes | `363,644` | `2026-06-26 22:05:26` | Has `394` duplicate `horse_id,race_id` rows. |
| `output/model_predictions.csv` | Yes | `13,219` | `2026-06-23 13:06:05` | Not updated by latest daily run. |

Final CSV date range:

- Minimum `race_date`: `1979-03-31`
- Maximum `race_date`: `2026-12-06`
- Rows with `race_date == 2026-06-26`: `21`
- Unique `race_id`: `54,196`

Parquet mismatch:

- CSV rows: `363,250`
- Parquet rows: `360,797`
- Difference: `2,453`

This mismatch is operationally important because `predict_today.py` reads `final_benter_dataset.parquet`, not the CSV.

## Prediction Validation

Existing `output/model_predictions.csv`:

- Rows: `13,219`
- Unique races: `5,366`
- Duplicate `race_id,horse_id` rows: `1`

Probability normalization:

| Column | Race Count | Min Sum | Max Sum | Max Abs Diff From 1 | Bad Races > 1e-6 |
|---|---:|---:|---:|---:|---:|
| `lr_norm_prob` | `5,366` | `0.9999999999999991` | `1.0000000000000002` | `8.88e-16` | `0` |
| `xgb_norm_prob` | `5,366` | `0.999999863` | `1.000000141` | `1.41e-7` | `0` |
| `cb_norm_prob` | `5,366` | `0.9999999999999992` | `1.0000000000000002` | `7.77e-16` | `0` |

Result: probability normalization is valid for the existing prediction file, but that file is stale.

## Feature Leakage Check

Active prediction features from `predict_today.py`:

`track`, `distance`, `surface`, `race_class`, `carried_weight`, `draw`, `handicap_rating`, `days_since_last_race`, `last_3_avg_position`, `last_5_avg_position`, `last_10_avg_position`, `surface_win_rate`, `distance_win_rate`, `track_win_rate`, `jockey_horse_win_rate`, `trainer_horse_win_rate`, `weight_change`, `class_change`, `distance_change`, `surface_change`.

Checked leakage candidates:

`finish_position`, `finish_time_seconds`, `race_time`, `finish`, `is_win`, `winner`, `result`, `odds`, `agf`, `agf_percent`, `agf_rank`, `prize`, `margin_text`, `margin_lengths_numeric`.

Result: none of these were found in the active model feature list.

Model introspection:

- CatBoost feature names available and match the 20-feature list.
- Logistic pipeline feature names available and match the 20-feature list.
- XGBoost pickle did not expose feature names through the checked attributes, so validation relies on `predict_today.py` input list for that model.

## SQLite Evidence

`pedigreeall_progress.db`:

- `PRAGMA integrity_check`: `ok`
- `horse_races`: `960,792`
- `horse_profiles`: `82,878`
- `horse_statistics`: `49,259`
- `discovered_horses`: `114,994`
- `raw_api_responses`: `128,055`
- `race_program_entries`: `0`
- `errors`: `12`
- `access_restrictions`: `12`

`pedigreeall_2026_test.db`:

- `PRAGMA integrity_check`: `ok`
- `discovered_horses`: `45`
- `raw_api_responses`: `47`
- `race_program_entries`: `0`

The database itself is readable and structurally valid. The missing active race program rows are the main data-readiness problem.

## Missing Data Sources

- Today's race program did not load into `race_program_entries`.
- Because `race_program_entries=0`, downstream profile/race/stat/workout/result updates had no target horses for today.
- `predict_today.py` could not generate predictions for `2026-06-26` from Parquet.
- `technical_report.md` and `walkthrough.md` were not found in the project tree during validation.

## Risky Points

- `daily_update.ps1` can return process success even when child scripts fail, because failures are logged but not accumulated into a final non-zero exit.
- Final dataset paths are inconsistent with the requested contract: files are root-level, not `output/`.
- CSV and Parquet final datasets are out of sync.
- `predict_today.py` reads the stale Parquet file, so even a newer CSV does not guarantee fresh predictions.
- `output/model_predictions.csv` is stale and has one duplicate prediction key.
- `output/benter_features_base.csv` contains duplicate keys.
- `failed_updates.csv` is not automatically cleared or scoped per run, so historical failures can obscure the latest state unless run IDs or timestamps are used.

## Daily Run Readiness

Not ready for fully unattended daily execution.

The pipeline can run end-to-end as a process, but it currently does not meet operational success criteria because:

- a required upstream script still fails,
- today's race program table is empty,
- predictions are not refreshed,
- final CSV and Parquet are inconsistent,
- failure tracking is non-empty,
- PowerShell exit code can be misleading.

## Windows Task Scheduler Readiness

It can be attached to Windows Task Scheduler technically, but it should not be trusted yet as a production automation.

Before scheduler binding:

- Make `daily_update.ps1` exit non-zero if any required child script fails.
- Define which warnings are acceptable and which should fail the run.
- Fix `update_race_programs.py` so today's race program creates `race_program_entries`.
- Write final dataset consistently to the expected paths.
- Ensure CSV and Parquet are regenerated together.
- Add a post-run validation step that checks dataset freshness, prediction freshness, duplicate keys, and probability sums.

## Next Work

1. Fix `update_race_programs.py` failure and verify `race_program_entries > 0` for an active race day.
2. Change `daily_update.ps1` to track child failures and exit `1` if any required stage fails.
3. Standardize final dataset location: either move contract to project root or write both CSV and Parquet under `output/`.
4. Regenerate `final_benter_dataset.parquet` after CSV updates and confirm matching row counts.
5. Regenerate `output/model_predictions.csv` from the fresh Parquet and remove duplicate `race_id,horse_id` rows.
6. Add a validation script that writes a small JSON or Markdown summary after each daily run.
7. Only after the above, register the PowerShell command in Windows Task Scheduler.
