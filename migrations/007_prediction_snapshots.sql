CREATE TABLE IF NOT EXISTS prediction_snapshots (
    prediction_id TEXT PRIMARY KEY,
    model_version TEXT NOT NULL,
    pipeline_version TEXT NOT NULL,
    race_id TEXT NOT NULL,
    horse_id TEXT NOT NULL,
    prediction_time TEXT NOT NULL,
    race_start_at TEXT NOT NULL,
    logistic_probability REAL NOT NULL CHECK(logistic_probability BETWEEN 0 AND 1),
    catboost_probability REAL NOT NULL CHECK(catboost_probability BETWEEN 0 AND 1),
    xgboost_probability REAL NOT NULL CHECK(xgboost_probability BETWEEN 0 AND 1),
    ensemble_probability REAL NOT NULL CHECK(ensemble_probability BETWEEN 0 AND 1),
    predicted_rank INTEGER NOT NULL CHECK(predicted_rank >= 1),
    feature_hash TEXT NOT NULL,
    feature_values_json TEXT NOT NULL,
    feature_contract_version TEXT NOT NULL,
    feature_snapshot_id INTEGER NOT NULL,
    source_request_id TEXT NOT NULL,
    FOREIGN KEY(feature_snapshot_id) REFERENCES program_snapshots(snapshot_id)
);
CREATE INDEX IF NOT EXISTS idx_prediction_race_time
    ON prediction_snapshots(race_id,prediction_time,horse_id);
CREATE INDEX IF NOT EXISTS idx_prediction_start
    ON prediction_snapshots(race_start_at,prediction_time);
CREATE TRIGGER IF NOT EXISTS prediction_snapshots_no_update
BEFORE UPDATE ON prediction_snapshots BEGIN
    SELECT RAISE(ABORT, 'prediction_snapshots is append-only');
END;
CREATE TRIGGER IF NOT EXISTS prediction_snapshots_no_delete
BEFORE DELETE ON prediction_snapshots BEGIN
    SELECT RAISE(ABORT, 'prediction_snapshots is append-only');
END;
