CREATE TABLE IF NOT EXISTS race_prediction_lifecycle (
    race_id TEXT PRIMARY KEY,
    race_start_at TEXT NOT NULL,
    track TEXT,
    final_refresh_due_at TEXT NOT NULL,
    final_prediction_due_at TEXT NOT NULL,
    final_prediction_done_at TEXT,
    final_prediction_status TEXT NOT NULL,
    agf_snapshot_done_at TEXT,
    odds_snapshot_done_at TEXT,
    prediction_run_id TEXT,
    status TEXT NOT NULL,
    warning TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_race_lifecycle_start_status
    ON race_prediction_lifecycle(race_start_at,status);
