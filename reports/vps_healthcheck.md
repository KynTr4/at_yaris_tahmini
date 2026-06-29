# VPS Healthcheck

Generated: 2026-06-27 22:29:11

## Result: **CRITICAL**

| Check | Status | Critical | Detail |
| --- | --- | --- | --- |
| database | PASS | True | quick_check=ok |
| agf_pre_race | PASS | True | late_tjk_agf_snapshots=0 |
| prediction_recency | FAIL | True | no predictions; recent_program_rows=84 |
| runner_run | FAIL | True | missing: run_latest.json |
| runner_agf_update | FAIL | True | missing: agf_update_latest.json |
| runner_results_update | FAIL | True | missing: results_update_latest.json |
| leakage_gate | PASS | True | {'feature_prefix_invariance': True, 'future_row_invariance': True, 'target_mutation_invariance': True, 'same_day_race_start_ordering': True, 'feature_dataset_nonempty': True, 'captured_at_before_race_start': True, 'duplicate_feature_rows': True, 'duplicate_snapshots': True, 'append_only_triggers': True, 'outcome_feature_detection': True, 'agf_asof': True, 'odds_asof': True, 'no_legacy_result_query': True} |
| feature_contract | PASS | True | contract valid |
| snapshot_coverage | PASS | True | missed_races=[] |
| shadow_monitor | PASS | True | last_run=2026-06-27T17:04:53.348462+00:00 |
| disk_space | PASS | True | free_gb=101.71, free_pct=20.9 |
| error_logs | PASS | True | none |
| web_service | FAIL | True | systemd unavailable on this host |
| web_basic_auth | PASS | True | unauthenticated_status=401 |
| web_api | PASS | True | status=200, dashboard=healthy |
| backup_recency | FAIL | True | no backup |
