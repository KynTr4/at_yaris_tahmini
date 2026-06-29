CREATE TABLE IF NOT EXISTS odds_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id TEXT NOT NULL,
    horse_id TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    odds REAL,
    source_request_id TEXT NOT NULL,
    source_endpoint TEXT NOT NULL DEFAULT 'GET:Tjk/GetRaceProgram',
    UNIQUE(source_request_id, race_id, horse_id)
);
CREATE INDEX IF NOT EXISTS idx_odds_asof
    ON odds_snapshots(race_id, horse_id, captured_at);
CREATE TRIGGER IF NOT EXISTS odds_snapshots_no_update
BEFORE UPDATE ON odds_snapshots BEGIN
    SELECT RAISE(ABORT, 'odds_snapshots is append-only');
END;
CREATE TRIGGER IF NOT EXISTS odds_snapshots_no_delete
BEFORE DELETE ON odds_snapshots BEGIN
    SELECT RAISE(ABORT, 'odds_snapshots is append-only');
END;
