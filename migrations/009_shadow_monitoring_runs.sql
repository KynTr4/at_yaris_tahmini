CREATE TABLE IF NOT EXISTS shadow_monitoring_runs (
    run_id TEXT PRIMARY KEY,
    run_at TEXT NOT NULL,
    shadow_date TEXT NOT NULL,
    leakage_gate_pass INTEGER NOT NULL CHECK(leakage_gate_pass IN (0,1)),
    feature_contract_pass INTEGER NOT NULL CHECK(feature_contract_pass IN (0,1)),
    snapshot_coverage_pass INTEGER NOT NULL CHECK(snapshot_coverage_pass IN (0,1)),
    prediction_drift_status TEXT NOT NULL,
    calibration_status TEXT NOT NULL,
    feature_drift_status TEXT NOT NULL,
    pipeline_status TEXT NOT NULL,
    production_ready INTEGER NOT NULL CHECK(production_ready IN (0,1)),
    details_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_shadow_runs_date
    ON shadow_monitoring_runs(shadow_date,run_at);
CREATE TRIGGER IF NOT EXISTS shadow_monitoring_runs_no_update
BEFORE UPDATE ON shadow_monitoring_runs BEGIN
    SELECT RAISE(ABORT, 'shadow_monitoring_runs is append-only');
END;
CREATE TRIGGER IF NOT EXISTS shadow_monitoring_runs_no_delete
BEFORE DELETE ON shadow_monitoring_runs BEGIN
    SELECT RAISE(ABORT, 'shadow_monitoring_runs is append-only');
END;
