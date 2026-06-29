CREATE TABLE IF NOT EXISTS program_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id TEXT NOT NULL,
    horse_id TEXT NOT NULL,
    race_start_at TEXT NOT NULL,
    race_no INTEGER,
    captured_at TEXT NOT NULL,
    source_endpoint TEXT NOT NULL,
    source_request_id TEXT NOT NULL,
    draw REAL,
    carried_weight REAL,
    jockey TEXT,
    trainer TEXT,
    handicap_rating REAL,
    race_class TEXT,
    track TEXT,
    surface TEXT,
    distance REAL,
    horse_name TEXT,
    UNIQUE(source_request_id, race_id, horse_id)
);
CREATE INDEX IF NOT EXISTS idx_program_asof
    ON program_snapshots(race_id, horse_id, captured_at, race_start_at);
CREATE INDEX IF NOT EXISTS idx_program_horse_start
    ON program_snapshots(horse_id, race_start_at);
CREATE TRIGGER IF NOT EXISTS program_snapshots_no_update
BEFORE UPDATE ON program_snapshots BEGIN
    SELECT RAISE(ABORT, 'program_snapshots is append-only');
END;
CREATE TRIGGER IF NOT EXISTS program_snapshots_no_delete
BEFORE DELETE ON program_snapshots BEGIN
    SELECT RAISE(ABORT, 'program_snapshots is append-only');
END;
