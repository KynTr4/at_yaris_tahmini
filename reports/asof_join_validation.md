# As-Of Join Validation

Generated: 2026-06-27 20:02:57

Certified feature rows/races: **84 / 8**.

| check | status |
| --- | --- |
| feature_prefix_invariance | PASS |
| future_row_invariance | PASS |
| target_mutation_invariance | PASS |
| same_day_race_start_ordering | PASS |
| feature_dataset_nonempty | PASS |
| captured_at_before_race_start | PASS |
| duplicate_feature_rows | PASS |
| duplicate_snapshots | PASS |
| append_only_triggers | PASS |
| outcome_feature_detection | PASS |
| agf_asof | PASS |
| odds_asof | PASS |
| no_legacy_result_query | PASS |

Join contract: latest snapshot by `captured_at` where `captured_at < race_start_at`. Late snapshots never enter the feature frame.
