# Veri Kalitesi ve Tahmin İyileştirme Raporu

Oluşturulma: 2026-07-04

## Yönetici Özeti

- SQLite `PRAGMA quick_check` sonucu `ok`; veritabanı fiziksel olarak sağlam.
- Ana SQLite dosyası 2.79 GB ve `horse_races` tablosunda 963.342 satır / 145.108 yarış var.
- Yerel canlı tahmin zinciri henüz veri üretmemiş: `prediction_snapshots=0`, `prediction_results=0`, `prediction_feature_snapshots=0`.
- Yeni `tjk_*` ve `model_prediction_runs` tabloları yerel DB'ye henüz uygulanmamış. Bu nedenle canlı Top1, Top3 ve ROI hesaplanamaz.
- Leakage-safe 2026 historical holdout: 15.322 at, 1.642 yarış. Ensemble Top1 `%27,59`, Top3 `%60,84`.
- Model final odds favorisini yalnızca yarışların `%43,54`'ünde seçiyor. Aynı atı seçtiğinde Top1 `%42,24`, farklılaştığında `%16,29`.
- Final odds ile tanısal Top1 ROI `-%28,94`; odds zaman damgalı olmadığı için bu sonuç sertifikalı değildir.
- Canlı `asof_features.parquet` dosyasındaki 13 geçmiş performans özelliği `%100` eksik. Model imputasyonla çalışsa da esas sinyalini kaybediyor.
- Kesin güvenli cache temizliği 797,41 MB alan açtı. Büyük CSV/Parquet dosyaları silinmedi.

## 1. Mevcut Veri Durumu

### SQLite

| Varlık | Kayıt |
|---|---:|
| `horse_races` | 963.342 satır / 145.108 yarış |
| `horse_profiles` | 82.939 |
| `horse_statistics` | 49.280 |
| `race_program_entries` | 1.273 |
| `program_snapshots` | 2.546 satır / 127 yarış |
| `agf_snapshots` | 2.486 satır / 126 yarış |
| `odds_snapshots` | 2.274 satır / 121 yarış |
| `race_results` | 106 satır / 11 yarış |
| `prediction_snapshots` | 0 |
| `prediction_results` | 0 |
| `prediction_feature_snapshots` | 0 |

Canlı performans oranı üretmek için sonuç kapsamı ve tahmin kapsamı yeterli değil. Öncelik, migration 018/019'u VPS ve yerel analiz kopyasında uygulamak, ardından tahmin ve sonuç yaşam döngüsünü gerçekten doldurmaktır.

### Historical eğitim/holdout verisi

- Kaynak: `output/final_benter_dataset.parquet`
- Ham boyut: 961.695 satır x 68 kolon.
- Geçerli ve tamamlanmış yarışlardan eğitim/değerlendirmeye kabul edilen: 229.511 satır.
- Eksik saha nedeniyle dışlanan yarış: 116.715.
- 2026 holdout: 15.322 satır / 1.642 yarış, 2026-01-01 - 2026-06-26.
- Model sözleşmesi: 20 özellik; AGF ve odds tahmin girdisi değil.

## 2. Diskte Gereksiz Dosyalar

İlk envanterde şu yeniden üretilebilir öğeler bulundu:

| Karar | Öğe | Gerekçe |
|---|---|---|
| SİL | `.cache/` | Pip indirme cache'i; ürün verisi değil |
| SİL | `.pytest_cache/` | Test çalıştırma cache'i |
| SİL | tüm `__pycache__/` dizinleri | Derlenmiş Python bytecode; yeniden oluşur |
| SAKLA | `.venv/` | Yerel çalışma ortamı; Git tarafından zaten ignore ediliyor |
| SAKLA | diagnostics kaynakları/testleri | Ürün dashboard ve regresyon testlerinin parçası |
| SAKLA | `results_coverage_latest.*` + tarihli kopya | İçerik duplicate olsa da biri sabit bağlantı, biri tarihsel kayıt |

İç içe `at_yaris_tahmini/` ve `nul` bu çalışma başlangıcında mevcut değildi.

## 3. Silinen Dosyalar

- 1.132 cache dizini kaldırıldı.
- Toplam 797,41 MB alan açıldı.
- Silinenler yalnızca `.cache`, `.pytest_cache` ve `__pycache__` kapsamındaydı.
- CSV, Parquet, SQLite, model, migration, rapor veya kaynak kod silinmedi.

## 4. Silinmeyen ve Dikkat Gerektiren Dosyalar

### Lake Parquet exportları

SQLite satır sayısı her karşılık gelen Parquet exportundan eşit veya daha yüksek:

| Export | Parquet | SQLite | Karar |
|---|---:|---:|---|
| `discovered_horses.parquet` | 114.993 | 115.020 | ARŞİVLE; SQLite daha güncel |
| `horse_profiles.parquet` | 82.878 | 82.939 | ARŞİVLE; SQLite daha güncel |
| `horse_races.parquet` | 960.792 | 963.342 | ARŞİVLE; SQLite daha güncel |
| `horse_statistics.parquet` | 49.259 | 49.280 | ARŞİVLE; SQLite daha güncel |
| `race_program_entries.parquet` | 0 | 1.273 | SİL adayı; export boş ve stale |

Bu dosyalar otomatik silinmedi. Önce DB yedeği ve geri yükleme testi yapılmalı; ardından storage manager retention politikasıyla arşivlenebilir.

### Eski prediction/result çıktıları

- `output/model_predictions.csv`: 13.488 satır / 5.434 yarış; yarış başına ortalama satır sayısı düşük ve Top1 `%14,94`. SQLite tahmin tabloları boş olduğu için şu an tek eski kanıt; **hemen silinmemeli**, arşivlenmeli.
- `output/prediction_history.csv`, `shadow_predictions.csv`, `live_metrics.csv`, `feature_drift.csv`, `model_drift.csv`: sıfır byte; yeni SQLite akışı doğrulandıktan sonra silinebilir.
- `output/komiser_events.csv` ve rapor CSV'leri: modelde kullanılmayan ama veri kalite kanıtı sağlayan çıktılar; rapor arşivine taşınmalı.

## 5. `.gitignore` Değişiklikleri

Eklenen kurallar:

- `*.db-wal`, `*.db-shm`
- `*.csv`
- `**/__pycache__/`
- `reports/debug*`
- `cache/`, `downloads/`, `nul`

Mevcut `*.db`, `*.parquet`, `logs/`, `backups/`, `.pytest_cache/`, `.cache/`, `tmp/` ve `output/` kuralları korundu. Daha önce izlenen CSV dosyaları ignore kuralına rağmen Git'te izlenmeye devam eder; bunlar ayrı bir onayla `git rm --cached` değerlendirmesine alınmalıdır.

## 6. Veri Kalitesi Sorunları

### Canlı özellik matrisi

84 satırlık canlı `asof_features.parquet` içinde şu özellikler `%100` eksik:

- `days_since_last_race`
- `last_3_avg_position`, `last_5_avg_position`, `last_10_avg_position`
- `surface_win_rate`, `distance_win_rate`, `track_win_rate`
- `jockey_horse_win_rate`, `trainer_horse_win_rate`
- `weight_change`, `class_change`, `distance_change`, `surface_change`

Bu durum, canlı programdaki `tjk:*`/at kimliklerinin tarihsel `horse_races` kimlikleriyle yeterince eşleşmediğini düşündürüyor. DB'de yalnızca 18 `horse_links` kaydı bulunması bu teşhisi destekliyor. Modelin en önemli historical özellikleri canlıda median imputasyona düşüyor.

### Historical holdout eksikleri

| Kolon | Eksik oranı |
|---|---:|
| `race_no` | %100,00 |
| `margin_lengths_numeric` | %100,00 |
| `agf` | %100,00 |
| `jockey_horse_win_rate` | %53,79 |
| `prize` | %47,28 |
| `distance_win_rate` | %46,21 |
| `trainer_horse_win_rate` | %23,53 |
| `pre_race_handicap_rating` | %22,65 |
| `track_win_rate` | %22,41 |
| `surface_win_rate` | %17,86 |
| son yarış/değişim özellikleri | %9,57 |

### Diğer kalite riskleri

1. Hipodrom ve sınıf metinlerinde `Ýzmir`, `Ýstanbul`, `ŢARTLI` gibi mojibake değerleri var. Bunlar kategorileri parçalayabilir.
2. Historical direct program özelliklerinde row-level `captured_at`/provenance kanıtı yok. Leakage audit sonucu production-blocking `NOT PROVEN`.
3. Odds historical sonuç tablosundan geliyor; immutable pre-race fiyat olduğu kanıtlanamıyor.
4. AGF historical holdoutta kullanılamıyor; canlı AGF var ama model sözleşmesi bilinçli olarak dışlıyor.
5. `horse_media`, pedigree, progeny ve sibling tabloları boş. Pedigree sinyali yok.
6. Canlı sonuç kapsamı 11 yarışla sınırlı; dashboard kalite oranları temsili değil.

## 7. Model Bazlı Historical Holdout Başarısı

| Model | Top1 | Top3 |
|---|---:|---:|
| Logistic | %26,67 | %58,53 |
| CatBoost | %27,53 | **%61,63** |
| XGBoost | %26,74 | %59,50 |
| Ensemble | **%27,59** | %60,84 |

Equal-weight ensemble CatBoost'a göre Top1'de yalnızca `0,06` puan iyi, Top3 ve log loss'ta daha kötü. Ensemble ağırlıkları validation/holdout içinde optimize edilmeli veya koşula göre model seçimi yapılmalı.

## 8. Modelin İyi Çalıştığı Koşullar

Ensemble, 2026 holdout:

- Antalya: Top1 `%36,25`, Top3 `%69,37` (160 yarış).
- İzmir: Top1 `%35,46`, Top3 `%66,31` (282 yarış).
- 2-6 atlı yarışlar: Top1 `%39,35`, Top3 `%82,54` (338 yarış).
- 2000+ metre: Top1 `%34,56`, Top3 `%68,20` (217 yarış).
- Kum: Top1 `%29,96`, Top3 `%63,21` (1.098 yarış).
- KV-8: Top1 `%52,78`, Top3 `%80,56`; örnek yalnızca 36 yarış.

Küçük segment sonuçları güven aralığı olmadan production kararı için kullanılmamalı.

## 9. Modelin Kötü Çalıştığı Koşullar

- Elazığ: Top1 `%18,57` (70 yarış).
- İstanbul: Top1 `%21,69` (272 yarış).
- Ankara: Top1 `%21,60` (162 yarış).
- Çim: Top1 `%18,91`, Top3 `%49,45` (275 yarış).
- 1200 metreden kısa yarışlar: Top1 `%17,31` (156 yarış).
- 13+ atlı yarışlar: Top1 `%17,65`, Top3 `%43,53` (255 yarış).
- ŞARTLI 1: Top1 `%3,08`, Top3 `%32,31` (65 yarış).
- Aylık Top1 Ocak `%31,33` iken Haziran `%21,40`; belirgin zaman drift'i var.

En çok hata; kalabalık saha, kısa mesafe, çim, ŞARTLI 1 ve son aylarda yoğunlaşıyor.

## 10. Favori ve ROI Analizi

- Final odds favorisinin Top1 oranı: `%36,36`.
- Ensemble ile odds favorisindeki seçim örtüşmesi: `%43,54`.
- Örtüşen seçimlerde Ensemble Top1: `%42,24`.
- Ayrışan seçimlerde Ensemble Top1: `%16,29`.
- Ensemble tanısal Top1 ROI: `-%28,94`.

Model şu anda piyasa favorisinden daha iyi bir winner picker değil ve farklı düşündüğü yarışlarda belirgin biçimde zayıf. Bununla birlikte odds final/result verisi olduğu için bu karşılaştırma canlı value-bet kanıtı değildir. Timestamped pre-race odds olmadan ROI optimizasyonu yapılmamalı.

## 11. Özellik Kontrolü

| İstenen özellik | Durum | Karar |
|---|---|---|
| Son 3 / son 5 yarış | Var; canlıda %100 eksik | Kimlik eşlemesini düzelt |
| Jokey-at uyumu | Var; holdoutta %53,79 eksik, canlıda %100 eksik | Kapsamı artır |
| Antrenör-at uyumu | Var; canlıda %100 eksik | Kapsamı artır |
| Pist geçmişi | `track_win_rate` var; canlıda eksik | Düzelt |
| Pist-mesafe birlikte | Yok | **Eklenmeli** |
| Şehir/hipodrom geçmişi | `track_win_rate` ile kısmi | Recency ve sınıf kontrollü sürüm eklenmeli |
| Kilo değişimi | Var; canlıda eksik | Düzelt, saha ortalamasına göre normalize et |
| Sınıf değişimi | Var, yalnızca binary | Yukarı/aşağı yönü ve büyüklüğü eklenmeli |
| Mesafe değişimi | Var | Non-lineer ve at-bazlı tolerans eklenmeli |
| Ara sonrası performans | `days_since_last_race` var | Layoff bucket ve atın layoff başarısı eklenmeli |
| Start numarası etkisi | `draw` var | Pist/yüzey/mesafe etkileşimi eklenmeli |
| AGF sırası | Canlı snapshotta var, historical sertifikalı değil | Timestamp/provenance sonrası ayrı market modeli |
| Ganyan oranı | Var ama final odds | Pre-race immutable snapshot şart |
| Favori sapması | Yok | Model-piyasa residual/value özelliği olarak eklenmeli |
| Aynı pistte dereceler | Win rate var, zaman/speed figure yok | **Eklenmeli** |
| Jokeyin o pistte başarısı | Yok | **Eklenmeli** |
| Antrenörün o pistte başarısı | Yok | **Eklenmeli** |

## 12. İşe Yarayan / Yaramayan Özellikler

2026 holdout permutation importance ve SHAP sonuçları:

### Güçlü ve tutarlı

- `race_class`
- `pre_race_handicap_rating`
- `last_3_avg_position`
- `carried_weight`
- kısmen `last_5_avg_position`, `last_10_avg_position`

### Modele göre kararsız veya zayıf

- `distance_win_rate`
- `jockey_horse_win_rate`
- `weight_change`
- `distance_change`
- `class_change`
- XGBoost'ta `surface_win_rate`, `track_win_rate`, `trainer_horse_win_rate` negatif permutation importance gösteriyor.

Bu özellikler hemen silinmemeli. Önce missing indicator, shrinkage, minimum örnek sayısı ve recency weighting ile yeniden tasarlanıp ablation testine alınmalı.

## 13. Tahmini İyileştirecek Yeni Özellikler

1. Pist x mesafe x yüzey bazlı at speed figure ve sınıf-par düzeltmeli süre.
2. Jokey-pist, antrenör-pist ve jokey-antrenör başarı oranları; Bayesian smoothing ile.
3. Son yarış temposu, erken/son sectional ve pace-shape uyumu.
4. Sınıf değişiminin yönü/büyüklüğü ve rakip kalitesi (strength of field).
5. Kilo değişiminin mutlak değil saha ortalaması ve atın tarihsel toleransına göre normalize edilmiş hali.
6. Layoff bucket, ikinci yarış sonrası toparlanma ve atın ara sonrası kişisel başarısı.
7. Draw x pist x mesafe x saha büyüklüğü etkileşimi.
8. Son 3/5 yarış trend eğimi, oynaklık ve kötü yarışa dayanıklı median form.
9. Timestamped AGF/odds ile piyasa residual modeli; ana performans modelinden ayrı.
10. Scratch sonrası saha değişimi, jokey değişimi, workout recency ve komiser olaylarının güvenilir as-of sürümleri.

## 14. Öncelikli Yapılacaklar

1. `horse_links` kapsamını 18 kayıttan canlı programın tamamına çıkar; canlı derived feature doluluğunu kalite kapısı yap.
2. Migration 018/019'u uygula ve `prediction_snapshots`, `prediction_results`, TJK sonuç tablolarının günlük dolduğunu doğrula.
3. Encoding normalizasyonu yap; şehir/sınıf kategorilerini tek canonical değere migrate et.
4. Her canlı tahmin için feature coverage kaydet; kritik özelliklerde yüksek eksiklikte tahmini yayınlama veya güven puanını düşür.
5. Haziran drift'ini veri kapsamı, pist dağılımı ve feature missingness ile kök neden analizine al.
6. Equal-weight ensemble yerine cross-fitted blending/stacking dene; CatBoost tek başına güçlü benchmark olarak kalsın.
7. Odds favorisi benchmarkını resmi model metriği yap; model benchmarkı yenemiyorsa value iddiası üretme.
8. Timestamped pre-race AGF/odds ingestion tamamlanmadan ROI veya bahis optimizasyonu yapma.
9. Kalabalık saha, kısa mesafe, çim ve ŞARTLI 1 için ayrı kalibrasyon ya da segment modeli dene.
10. Yeni özellikleri tek tek ablation + rolling temporal CV ile ölç; SHAP tek başına özellik kabul kriteri olmasın.

## 15. Temizlik Karar Özeti

| Kategori | Karar |
|---|---|
| Cache / pycache / pytest cache | SİLİNDİ |
| SQLite ve modeller | SAKLA |
| Final dataset ve canlı as-of parquet | SAKLA |
| Lake parquet exportları | ARŞİVLE adayı; DB daha güncel |
| Eski prediction CSV | ARŞİVLE; SQLite canlı tahminleri boş |
| Sıfır byte eski CSV'ler | SİL adayı; yeni akış doğrulandıktan sonra |
| Diagnostics kaynak/testleri | SAKLA |
| Duplicate coverage latest/tarihli | SAKLA; farklı erişim amacı |

## 16. Sonuç

Model historical sıralama sinyali üretiyor ancak production tahmin kalitesindeki en büyük engel yeni algoritma eksikliğinden önce canlı veri bağlantısıdır. Historical modelin önemli özellikleri canlıda tamamen boş, canlı tahmin/sonuç tabloları yerel kopyada dolmuyor ve ROI için güvenilir pre-race piyasa verisi yok. Önce kimlik eşleme, immutable snapshot ve canlı değerlendirme döngüsü tamamlanmalı; ardından segment bazlı özellik mühendisliği ve ensemble optimizasyonu anlamlı olacaktır.

## 17. Taşınabilirlik, Freeze Uyumluluğu ve Doğrulama

### Uygulanan düzeltmeler

- `app_config.py`: Windows'ta `.env` içindeki Linux `/opt` ve `/var` yollarının
  `C:\opt`/`C:\var` olarak yorumlanması engellendi. Yerel fallback repo kökü,
  yerel DB, `logs/` ve `backups/`; Linux production davranışı değişmedi.
- `run_race_freeze.py`: çok pencereli state-machine için public, yan etkisiz
  `classify_race()` API'si eklendi.
- `tests/test_race_freeze.py`: eski tek pencere beklentileri
  `PRE_WINDOW`, `CAPTURING`, `FINAL_CAPTURING`, `POST_START_RETRY` ve `FAILED`
  sözleşmesine uyarlandı.
- `performance_queries.py`: materialized tablo mevcut fakat boşsa canlı
  leakage-safe CTE'ye fallback eklendi.
- Results runner ve systemd testleri yeni CDN import/storage manager adımlarına
  uyarlandı.

### Test sonucu

```text
123 passed, 2 warnings in 13.87s
```

Uyarılar:

1. Starlette `TestClient` için gelecekteki `httpx2` geçiş uyarısı.
2. `build_asof_features.py` içinde all-NA DataFrame concat davranışı için
   pandas `FutureWarning`.

### Kalan riskler

- Canlı as-of dosyası stale ve tüm atlar `name:*`; history coverage sıfır.
- `horse_links` canonical historical anahtarlarla eşleşmiyor.
- `prediction_snapshots`, `prediction_feature_snapshots` ve
  `prediction_results` henüz canlı veri üretmiyor.
- Resolver çağrısı program lookup tablosu doldurulmadan önce çalışıyor.
- VPS timer/healthcheck durumu deploy sonrası ayrıca doğrulanmalı.
- Timestamped pre-race odds/AGF olmadan ROI sertifikalı değildir.

Ayrıntılı kök neden ve çözüm sırası:
`reports/live_data_pipeline_blockers.md`.
