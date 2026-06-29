CREATE TABLE IF NOT EXISTS prediction_results (
    prediction_id TEXT PRIMARY KEY,
    finish_position REAL,
    winner INTEGER NOT NULL CHECK(winner IN (0,1)),
    official_odds REAL,
    official_time TEXT,
    payout REAL,
    matched_at TEXT NOT NULL,
    FOREIGN KEY(prediction_id) REFERENCES prediction_snapshots(prediction_id)
);
CREATE INDEX IF NOT EXISTS idx_prediction_results_matched
    ON prediction_results(matched_at,prediction_id);
CREATE TRIGGER IF NOT EXISTS prediction_results_no_update
BEFORE UPDATE ON prediction_results BEGIN
    SELECT RAISE(ABORT, 'prediction_results is append-only');
END;
CREATE TRIGGER IF NOT EXISTS prediction_results_no_delete
BEFORE DELETE ON prediction_results BEGIN
    SELECT RAISE(ABORT, 'prediction_results is append-only');
END;
