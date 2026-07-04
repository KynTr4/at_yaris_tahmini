-- Migration 018: TJK günlük yarış sonuçları ve tahmin karşılaştırma tabloları
-- Tek kayıt kaynağı: HTML'den RAM'de parse edilip SQLite'a yazılır.
-- Dosyaya (CSV, parquet) hiçbir şey yazılmaz.

-- Ham TJK sonuçları: şehir × tarih × koşu × at bazında tekil
CREATE TABLE IF NOT EXISTS tjk_race_results (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    race_date   TEXT NOT NULL,      -- YYYY-MM-DD (Europe/Istanbul)
    city        TEXT NOT NULL,      -- Normalize: 'İstanbul', 'İzmir', ...
    race_no     INTEGER NOT NULL,
    race_time   TEXT,               -- '17.15'
    horse_name  TEXT NOT NULL,      -- Normalize: BÜYÜK HARF, parantez yok, boşluk temizli
    horse_no    INTEGER,            -- TJK start numarası
    actual_rank INTEGER,            -- 1, 2, 3... (NULL = koşmaz/DNS/DNF)
    finish_time TEXT,               -- '1.34.04'
    ganyan      TEXT,               -- '10.50'
    agf         TEXT,               -- '%8(3)'
    scraped_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE(race_date, city, race_no, horse_name)
);

CREATE INDEX IF NOT EXISTS idx_tjk_results_date_city
    ON tjk_race_results(race_date, city, race_no);

-- Tahmin–gerçek karşılaştırması: at bazında birleştirilmiş veri
CREATE TABLE IF NOT EXISTS tjk_prediction_comparisons (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    race_date        TEXT NOT NULL,
    city             TEXT NOT NULL,
    race_no          INTEGER NOT NULL,
    race_time        TEXT,
    horse_name       TEXT NOT NULL,   -- normalize edilmiş at adı
    horse_no         INTEGER,
    actual_rank      INTEGER,         -- TJK gerçek sıra
    predicted_rank   INTEGER,         -- Model tahmin sırası (NULL = eşleşme yok)
    ensemble_prob    REAL,
    catboost_prob    REAL,
    xgboost_prob     REAL,
    logistic_prob    REAL,
    is_top1          INTEGER NOT NULL DEFAULT 0,   -- actual_rank=1 AND predicted_rank=1
    is_top3          INTEGER NOT NULL DEFAULT 0,   -- actual_rank=1 AND predicted_rank<=3
    actual_winner    TEXT,            -- O koşunun birincisinin adı
    match_score      REAL,            -- 0–1 fuzzy match skoru (1.0 = exact)
    pred_source      TEXT,            -- 'prediction_snapshots' veya 'model_prediction_runs'
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE(race_date, city, race_no, horse_name)
);

CREATE INDEX IF NOT EXISTS idx_tjk_comparisons_date_city
    ON tjk_prediction_comparisons(race_date, city);

-- Koşu bazında özet (denormalized, hızlı dashboard sorgusu için)
CREATE TABLE IF NOT EXISTS tjk_race_summary (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    race_date       TEXT NOT NULL,
    city            TEXT NOT NULL,
    race_no         INTEGER NOT NULL,
    race_time       TEXT,
    total_horses    INTEGER NOT NULL DEFAULT 0,
    result_count    INTEGER NOT NULL DEFAULT 0,   -- sonucu olan at sayısı
    matched_preds   INTEGER NOT NULL DEFAULT 0,   -- tahminle eşleşen at sayısı
    top1_correct    INTEGER NOT NULL DEFAULT 0,   -- 1=birinci doğru tahmin
    top3_correct    INTEGER NOT NULL DEFAULT 0,   -- 1=birinci top-3 tahminde
    winner_name     TEXT,
    winner_prob     REAL,
    winner_pred_rank INTEGER,
    last_updated    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE(race_date, city, race_no)
);

CREATE INDEX IF NOT EXISTS idx_tjk_summary_date
    ON tjk_race_summary(race_date, city);
