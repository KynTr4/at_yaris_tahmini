# Storage & TJK Refactor Raporu

Oluşturulma: 2026-07-04
Durum: ✅ 24/24 test geçti

---

## Genel Bakış

Bu refaktör, üç temel sorunu çözer:

1. **VPS disk doluyordu** — CSV/Parquet birikimi (~3.3 GB temizlendi)
2. **TJK sonuçları senkronize değildi** — HTML'den canlı çekip SQLite'a yazılıyor
3. **Veri çoklanması** — Aynı bilgi CSV, parquet, JSON, log ve SQLite'ta ayrı ayrı tutuluyordu

Temel ilke: **SQLite tek kayıt kaynağıdır.**

---

## 1. Değiştirilen Dosyalar

| Dosya | Değişiklik |
|---|---|
| `tjk_scraper.py` | Komple yeniden yazıldı — HTML parse, SQLite persist, karşılaştırma, cache |
| `predict_today.py` | CSV/parquet çıktısı kaldırıldı → `model_prediction_runs` SQLite tablosuna yazıyor |
| `shadow_mode.py` | `SHADOW_CSV` ve `HISTORY_CSV` yazımı kaldırıldı, sadece SQLite kullanıyor |
| `storage_manager.py` | `--delete` bayrağı eklendi; varsayılan çalıştırma = dry-run + VACUUM |
| `web_app.py` | `/api/tjk-results` cache/force_refresh desteği, `/api/storage-status` yeni endpoint, SYSTEMD_UNITS güncellendi |
| `clean_large_csvs.py` | Yeniden yazıldı: parquet var mı + SQLite'ta karşılık var mı kontrolü |
| `cleanup.sh` | `storage_manager.py` çağırıyor, daha güvenli |
| `deploy/logrotate/at-yaris-tahmini` | 7→30 gün saklama, `archive/` dizini |
| `deploy/install_vps.sh` | `at-yaris-cleanup.timer` ve `at-yaris-storage-manager.timer` enable ediliyor |
| `web/templates/base.html` | Navbar'a "🏇 TJK Sonuçlar" eklendi |
| `web/templates/tjk_results.html` | Yeni sayfa — tahmin/gerçek karşılaştırma |
| `web/templates/dashboard.html` | Disk izleme widget'ı eklendi |
| `check_vps_space.py` | Hardcoded SSH şifresi kaldırıldı, yerel disk istatistikleri |

---

## 2. Kaldırılan CSV/Parquet Üretimi

| Script | Eski çıktı | Yeni durum |
|---|---|---|
| `predict_today.py` | `output/model_predictions.parquet` | SQLite `model_prediction_runs` tablosu |
| `shadow_mode.py` | `output/shadow_predictions.csv` | ❌ Artık üretilmiyor |
| `shadow_mode.py` | `output/prediction_history.csv` | ❌ Artık üretilmiyor |
| `tjk_scraper.py` | Sadece in-memory dict döndürüyordu | SQLite `tjk_race_results` + `tjk_prediction_comparisons` |

---

## 3. Yeni SQLite Tabloları

### Migration 018 — `tjk_race_results`
Ham TJK sonuçları. `(race_date, city, race_no, horse_name)` üzerinde UNIQUE.

```sql
INSERT INTO tjk_race_results
    (race_date, city, race_no, race_time, horse_name, horse_no,
     actual_rank, finish_time, ganyan, agf)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(race_date, city, race_no, horse_name) DO UPDATE SET ...
```

### Migration 018 — `tjk_prediction_comparisons`
At başına karşılaştırma kaydı. Tekrar yazma = REPLACE (güncel veri).

### Migration 018 — `tjk_race_summary`
Koşu başına özet (denormalized, dashboard için hızlı sorgu).

### Migration 019 — `model_prediction_runs`
`predict_today.py` çıktısı. `prediction_snapshots`'tan farkı: provenance trigger yok, daha basit.

---

## 4. TJK Akışı

```
GET /api/tjk-results?date=YYYY-MM-DD
         │
         ▼
  tjk_race_summary'de
  taze kayıt var mı?
  (< 15 dk önce)
         │
    Evet ▼           Hayır ─────────────────────────────────────────────────┐
         │                                                                   │
  SQLite'tan oku                                     TJK HTML'i çek (HTTP) ◄┘
  (hızlı, ~5ms)                                              │
         │                                          _parse_races() → RAM'de
         │                                          at adları normalize edilir
         │                                                    │
         │                                     persist_results() → SQLite UPSERT
         │                                     tjk_race_results (kayıtlar korunur)
         │                                                    │
         │                            build_and_persist_comparisons()
         │                            prediction_snapshots veya
         │                            model_prediction_runs'tan tahminler
         │                            Exact match → fuzzy match (score ≥ 85)
         │                            INSERT OR REPLACE → tjk_prediction_comparisons
         │                            INSERT OR REPLACE → tjk_race_summary
         │                                                    │
         └──────────────────────────────────────────────► JSON yanıt
```

---

## 5. Storage Manager Akışı

```bash
# Gece 03:00 otomatik (at-yaris-storage-manager.timer):
python storage_manager.py --delete

# Sonucu gör:
python storage_manager.py --report

# Önce ne silineceğini gör:
python storage_manager.py          # dry-run default

# Sadece SQLite bakımı:
python storage_manager.py --vacuum
```

**Retention politikaları:**

| Kategori | Saklama |
|---|---|
| `output/*.csv` (korunanlar hariç) | 0 gün — anında sil |
| `lake/analytics/*.csv` | 0 gün |
| `output/today_features_base.*` | 1 gün |
| `output/backtest*.parquet` | Son 5 + 90 gün |
| `data/agfv2_raw/html/*.html` | 30 gün |
| Log dosyaları | 30 gün |
| `komiser_raporlari/*.pdf` | 90 gün |

**SQLite bakımı (her çalışmada):**
1. `PRAGMA wal_checkpoint(TRUNCATE)` — WAL flush
2. `VACUUM` — Fragmented space geri al
3. `ANALYZE` — Query planner istatistiklerini güncelle

---

## 6. VPS Deploy Sonrası Çalıştırılacak Komutlar

```bash
# 1. Kodu güncelle
cd /opt/at_yaris_tahmini
git pull

# 2. Migration'ları uygula (otomatik, ilk çalışmada)
.venv/bin/python migrate_provenance_schema.py

# 3. Yeni systemd servislerini kur
sudo install -m644 deploy/systemd/at-yaris-storage-manager.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now at-yaris-storage-manager.timer
sudo systemctl enable --now at-yaris-cleanup.timer

# 4. Mevcut büyük CSV'leri temizle (3.3 GB boşaltır)
.venv/bin/python storage_manager.py --delete

# 5. SQLite VACUUM (önerilen ilk deploy sonrası)
.venv/bin/python storage_manager.py --vacuum

# 6. Web app syntax kontrolü
.venv/bin/python web_app.py --check

# 7. Testleri çalıştır
.venv/bin/python -m pytest tests/test_storage_and_tjk.py -v
```

---

## 7. Riskler ve Önlemler

| Risk | Olasılık | Önlem |
|---|---|---|
| TJK web sitesi erişim engeli | Orta | Requests timeout=20s, per-city hata yakalanır, diğerleri devam eder |
| `prediction_snapshots` boş (shadow_mode çalışmamış) | Düşük | `model_prediction_runs` fallback otomatik devreye girer |
| Migration sırasında DB kilitlenmesi | Düşük | `timeout=60` ayarı var; tek seferlik işlem |
| `predict_today.py` SQLite yazma hatası | Düşük | Hata loglanır ve script başarısız kodla sonlanır; yanlış başarı raporu üretilmez |
| `enforce_retention` yanlış dosya siler | Düşük | `PROTECTED_OUTPUTS` seti + `--delete` flag zorunlu |

---

## 8. Geri Dönüş Planı

**Parquet/CSV'ye geri dönmek gerekirse:**

`predict_today.py`'de SQLite bloğunu şununla değiştir:
```python
# Geçici geri dönüş (migration tamamlanana kadar)
predictions_to_save.to_parquet("output/model_predictions.parquet", index=False)
```

`shadow_mode.py`'de CSV satırlarını uncomment et:
```python
SHADOW_CSV = OUTPUT_DIR / "shadow_predictions.csv"
```

**TJK karşılaştırması için geri dönüş:** `tjk_scraper.py` hâlâ `compare_predictions_with_tjk()` fonksiyonu sunuyor, sadece şimdi SQLite'a da yazıyor. API endpoint değişmedi.

---

## 9. Test Sonuçları

```
24 passed

TestNormalizeHorseName (5/5)   ✅ At adı normalizasyonu
TestMigrations (3/3)           ✅ Migration 018+019 tabloları
TestPersistResults (4/4)       ✅ TJK sonuç kaydetme + duplicate + canlı güncelleme
TestStorageManager (5/5)       ✅ dry-run vs --delete davranışı
TestPredictTodaySQLite (1/1)   ✅ model_prediction_runs yazma
TestStorageStatusAPI (3/3)     ✅ Disk metrikleri + gerçek API endpoint'i
TestTJKHTMLParse (3/3)         ✅ HTML parse (gerçek HTTP yok)
```
