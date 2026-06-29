CREATE TABLE IF NOT EXISTS race_results (
    result_id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id TEXT NOT NULL,
    horse_id TEXT NOT NULL,
    race_start_at TEXT NOT NULL,
    race_no INTEGER,
    captured_at TEXT NOT NULL,
    source_endpoint TEXT NOT NULL,
    source_request_id TEXT NOT NULL,
    finish_position REAL,
    finish_time TEXT,
    prize REAL,
    margin TEXT,
    result_odds REAL,
    result_status TEXT NOT NULL,
    UNIQUE(source_request_id, race_id, horse_id)
);
CREATE INDEX IF NOT EXISTS idx_results_history
    ON race_results(horse_id, race_start_at, race_id);
CREATE TRIGGER IF NOT EXISTS race_results_no_update
BEFORE UPDATE ON race_results BEGIN
    SELECT RAISE(ABORT, 'race_results is append-only');
END;
CREATE TRIGGER IF NOT EXISTS race_results_no_delete
BEFORE DELETE ON race_results BEGIN
    SELECT RAISE(ABORT, 'race_results is append-only');
END;
