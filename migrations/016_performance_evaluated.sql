-- Migration 016: pre-materialized evaluation table for fast API reads
-- Populated daily by materialize_performance.py; web_app reads are SELECT-only.
CREATE TABLE IF NOT EXISTS performance_evaluated (
    prediction_id          TEXT NOT NULL,
    race_id                TEXT NOT NULL,
    prediction_time        TEXT NOT NULL,
    race_start_at          TEXT NOT NULL,
    model                  TEXT NOT NULL,
    model_version          TEXT,
    probability            REAL,
    predicted_horse_id     TEXT,
    predicted_horse        TEXT,
    winner_name            TEXT,
    winner_ids             TEXT,
    city                   TEXT,
    race_no                INTEGER,
    race_class             TEXT,
    surface                TEXT,
    distance               INTEGER,
    race_date              TEXT NOT NULL,
    race_time              TEXT,
    correct                INTEGER NOT NULL DEFAULT 0,
    decimal_odds           REAL,
    winner_decimal_odds    REAL,
    net_return             REAL,
    materialized_at        TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (prediction_id, model)
);
CREATE INDEX IF NOT EXISTS idx_pe_date  ON performance_evaluated(race_date);
CREATE INDEX IF NOT EXISTS idx_pe_model ON performance_evaluated(model, race_date);
CREATE INDEX IF NOT EXISTS idx_pe_city  ON performance_evaluated(city, race_date);
