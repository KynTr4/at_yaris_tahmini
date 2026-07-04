-- Migration 019: Basit prediction kayıt tablosu (predict_today.py çıktısı)
-- prediction_snapshots'tan farkı: provenance trigger yok, shadow_mode bağımlılığı yok.
-- predict_today.py bu tabloya yazar; CSV/parquet üretmez.

CREATE TABLE IF NOT EXISTS model_prediction_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_date TEXT NOT NULL,    -- YYYY-MM-DD
    race_id         TEXT NOT NULL,
    horse_id        TEXT NOT NULL,
    horse_name      TEXT NOT NULL,
    track           TEXT,
    race_no         INTEGER,
    race_start_at   TEXT,
    lr_prob         REAL,
    xgb_prob        REAL,
    cb_prob         REAL,
    ensemble_prob   REAL NOT NULL,
    predicted_rank  INTEGER NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE(prediction_date, race_id, horse_id)
);

CREATE INDEX IF NOT EXISTS idx_model_pred_runs_date
    ON model_prediction_runs(prediction_date, race_id);
