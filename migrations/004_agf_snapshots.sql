CREATE TABLE IF NOT EXISTS agf_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id TEXT NOT NULL,
    horse_id TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    agf_percent REAL,
    agf_rank INTEGER,
    source_request_id TEXT NOT NULL,
    source_endpoint TEXT NOT NULL DEFAULT 'TJK_AGFv2',
    UNIQUE(source_request_id, race_id, horse_id)
);
CREATE INDEX IF NOT EXISTS idx_agf_asof
    ON agf_snapshots(race_id, horse_id, captured_at);
CREATE TRIGGER IF NOT EXISTS agf_snapshots_no_update
BEFORE UPDATE ON agf_snapshots BEGIN
    SELECT RAISE(ABORT, 'agf_snapshots is append-only');
END;
CREATE TRIGGER IF NOT EXISTS agf_snapshots_no_delete
BEFORE DELETE ON agf_snapshots BEGIN
    SELECT RAISE(ABORT, 'agf_snapshots is append-only');
END;
