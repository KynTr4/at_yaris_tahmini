CREATE TABLE IF NOT EXISTS prediction_feature_snapshots (
    feature_archive_id INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id TEXT NOT NULL UNIQUE,
    race_id TEXT NOT NULL,
    horse_id TEXT NOT NULL,
    prediction_time TEXT NOT NULL,
    race_start_at TEXT NOT NULL,
    feature_values_json TEXT NOT NULL,
    feature_hash TEXT NOT NULL,
    feature_contract_version TEXT NOT NULL,
    archived_at TEXT NOT NULL,
    FOREIGN KEY(prediction_id) REFERENCES prediction_snapshots(prediction_id)
);
CREATE INDEX IF NOT EXISTS idx_prediction_feature_race
    ON prediction_feature_snapshots(race_id,prediction_time,horse_id);
CREATE TRIGGER IF NOT EXISTS prediction_feature_snapshots_no_update
BEFORE UPDATE ON prediction_feature_snapshots BEGIN
    SELECT RAISE(ABORT, 'prediction_feature_snapshots is append-only');
END;
CREATE TRIGGER IF NOT EXISTS prediction_feature_snapshots_no_delete
BEFORE DELETE ON prediction_feature_snapshots BEGIN
    SELECT RAISE(ABORT, 'prediction_feature_snapshots is append-only');
END;
