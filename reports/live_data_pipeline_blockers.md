# Canlı Veri Pipeline Blockerları

Oluşturulma: 2026-07-04

## 1. Windows'ta Production Yollarının Yanlış Çözülmesi

**Sorun**

Windows yerel çalışmasında `.env` içindeki `/opt/at_yaris_tahmini` ve `/var/...`
yolları `C:\opt\...` / `C:\var\...` olarak yorumlanıyordu. Migration ve testler
repo içindeki DB yerine var olmayan dizine yöneliyordu.

**Kanıt**

- `MIGRATIONS_DIR` önce `C:\opt\at_yaris_tahmini\migrations` oluyordu.
- `tests/test_race_freeze.py` geçici DB'sinde `program_snapshots` oluşmuyordu.
- Düzeltme sonrasında tam paket `123 passed`.

**Etkilenen dosyalar**

- `app_config.py`
- `migrate_provenance_schema.py`
- DB kullanan tüm runner ve testler

**Çözüm**

Yalnız Windows'ta `/...` biçimli POSIX production yollarını yerel fallback ile
değiştir. Windows biçimli açık override'ları ve Linux production yollarını koru.
Bu davranış `PROJECT_ROOT`, `DB_PATH`, `LOG_DIR` ve `BACKUP_DIR` için aynı olmalı.

**Test komutu**

```bash
python -m pytest tests/test_app_config.py tests/test_race_freeze.py -q
```

## 2. Canlı Program ve As-of Dosyası Güncel Değil

**Sorun**

Yerel analiz kopyasında program snapshotları ile canlı as-of dosyası güncel güne
ulaşmıyor. Freeze runner yalnız yaklaşan yarışları işlediğinden tahmin üretmiyor.

**Kanıt**

- `program_snapshots`: 127 yarış, tarih aralığı
  `2026-06-25T21:05:00Z` - `2026-07-01T20:50:00Z`.
- `output/asof_features.parquet`: 8 yarış / 84 at, maksimum yarış zamanı
  `2026-06-26T20:50:00Z`.
- Analiz tarihi `2026-07-04`; mevcut dosyada yaklaşan yarış yok.

**Etkilenen dosyalar**

- `run_daily_pipeline.py`
- `update_race_programs.py`
- `build_asof_features.py`
- `run_race_freeze.py`
- `deploy/systemd/at-yaris-daily.*`
- `deploy/systemd/at-yaris-race-freeze.*`

**Çözüm**

VPS'de daily ve race-freeze timer durumlarını doğrula. Daily pipeline sonunda
as-of maksimum yarış tarihinin bugünün programıyla eşleşmesini kalite kapısı yap.
Stale as-of dosyasında freeze çalışmasını başarısız say ve açık hata kodu üret.

**Test komutu**

```bash
python update_race_programs.py
python build_asof_features.py
python -c "import pandas as pd; f=pd.read_parquet('output/asof_features.parquet'); print(f.race_start_at.max(), f.race_id.nunique())"
python run_race_freeze.py --date YYYY-MM-DD --now YYYY-MM-DDTHH:MM:SS+00:00
```

## 3. `prediction_snapshots` Sıfır

**Sorun**

Tahmin üretimi günlük pipeline'ın içinde değil. `prediction_snapshots` yalnız
`shadow_mode.py` çalışınca yazılıyor; bunu zaman penceresinde çağıran yol ayrı
race-freeze timer'ı.

**Kanıt**

- Yerel DB: `prediction_snapshots=0`.
- `run_daily_pipeline.py` içinde `shadow_mode.py` veya `run_race_freeze.py` yok.
- `run_daily_pipeline.py` yalnız `shadow_monitor.py` çağırıyor.
- `run_race_freeze.py`, sadece T-15/T+120 saniye pencerelerinde
  `shadow_mode.py` çağırıyor.
- Yerel program/as-of verisi stale olduğu için uygun yarış bulunmuyor.

**Etkilenen dosyalar**

- `run_daily_pipeline.py`
- `run_race_freeze.py`
- `shadow_mode.py`
- `deploy/systemd/at-yaris-race-freeze.service`
- `deploy/systemd/at-yaris-race-freeze.timer`

**Çözüm**

Race-freeze timer'ını production zorunluluğu olarak healthcheck'e ekle.
Her yarış günü için `program race -> freeze lifecycle -> prediction snapshot`
sayımını izleyen invariant oluştur. Uygun yarış varken sıfır tahmin üretimini
servis hatası say.

**Test komutu**

```bash
python -m pytest tests/test_race_freeze.py tests/test_shadow_monitoring.py -q
systemctl status at-yaris-race-freeze.timer --no-pager
systemctl list-timers 'at-yaris-*' --no-pager
```

## 4. `prediction_feature_snapshots` Sıfır

**Sorun**

Feature snapshot yazımı bağımsız bir süreç değil; `shadow_mode.archive_predictions`
içinde prediction satırlarıyla aynı akışta gerçekleşiyor. Upstream tahmin yoksa
feature snapshot da yok.

**Kanıt**

- Yerel DB: `prediction_feature_snapshots=0`.
- `shadow_mode.py`, önce `prediction_snapshots`, sonra
  `prediction_feature_snapshots` insert ediyor.
- `prediction_snapshots=0`.

**Etkilenen dosyalar**

- `shadow_mode.py`
- `migrations/007_prediction_snapshots.sql`
- `migrations/011_prediction_feature_snapshots.sql`

**Çözüm**

Tahmin transaction'ında prediction ve feature row sayılarının birebir eşleşmesini
assert et. Transaction sonrası `prediction_count == feature_count` metriğini
healthcheck ve dashboard'a ekle.

**Test komutu**

```bash
python -m pytest tests/test_shadow_monitoring.py tests/test_feature_leakage_gate.py -q
```

## 5. `prediction_results` Sıfır

**Sorun**

`prediction_results` yalnız mevcut tahminler resmi sonuçlarla eşleştirildiğinde
`shadow_monitor.match_prediction_results()` tarafından yazılıyor. Upstream
prediction olmadığı için downstream eşleştirme yapılamıyor.

**Kanıt**

- Yerel DB: `prediction_results=0`.
- `shadow_monitor.py`, eşleşmeyi `prediction_snapshots` üzerinden başlatıyor.
- `race_results` yalnız 106 satır / 11 yarış; sonuç kapsamı da sınırlı.

**Etkilenen dosyalar**

- `shadow_monitor.py`
- `run_results_update.py`
- `update_results.py`
- `import_race_results_csv.py`
- `migrations/008_prediction_results.sql`

**Çözüm**

Önce prediction üretimini düzelt. Sonra her tamamlanmış yarış için
`predictions -> official results -> prediction_results` sayımını kontrol eden
günlük reconciliation ekle. Sonuç var ama eşleşme yoksa horse/race identity
hatasını ayrı raporla.

**Test komutu**

```bash
python run_results_update.py --date YYYY-MM-DD --country TR
python shadow_monitor.py
python -m pytest tests/test_results_runner.py tests/test_shadow_monitoring.py -q
```

## 6. `horse_links` Yalnız 18 ve Canonical Anahtarla Uyuşmuyor

**Sorun**

Backfill otomatik pipeline adımı değil ve yazdığı `horse_id` değerleri sayısal.
Historical `horse_races.horse_key` ise `tjk:*` veya `horse:*` canonical string.
Mevcut 18 link historical tabloyla hiçbir satır eşleştirmiyor.

**Kanıt**

- `horse_links`: 18 satır / 18 verified.
- Linklerin `horse_id` örnekleri `1748904`, `1851181` gibi sayısal değerler.
- Historical distinct anahtarlar: 49.294 `tjk:*`, 26 `horse:*`.
- Verified link -> historical key eşleşmesi: `0`.
- Program -> link -> historical key eşleşmesi: `0`.
- `backfill_tjk_links_from_program.py` günlük pipeline'da çağrılmıyor.

**Etkilenen dosyalar**

- `backfill_tjk_links_from_program.py`
- `pedigreeall_core.py`
- `update_race_programs.py`
- `build_asof_features.py`
- `run_daily_pipeline.py`

**Çözüm**

Tek canonical horse key sözleşmesi tanımla: TJK ID varsa `tjk:<id>`, yalnız
internal ID varsa `horse:<id>`. `horse_links` için canonical key kolonu/migration
ekle veya mevcut `horse_id` değerlerini canonical stringe migrate et. Backfill'i
program güncellemesinden sonra idempotent daily step olarak çalıştır.

**Test komutu**

```bash
python backfill_tjk_links_from_program.py --date YYYY-MM-DD
python -m pytest tests/test_tjk_resolver.py -q
```

## 7. `name:*` Snapshot Çözümü Yanlış Sırada Çalışıyor

**Sorun**

`update_race_programs.py`, `resolve_name_ids_in_snapshots()` fonksiyonunu aynı
günün `race_program_entries` satırlarını yazmadan önce çağırıyor. Resolver boş/eski
lookup üzerinde çalışıyor; program satırları yazıldıktan sonra tekrar çağrılmıyor.

**Kanıt**

- `program_snapshots` distinct atları: 796 `name:*`, 324 `tjk:*`, 26 `horse:*`.
- Son `asof_features.parquet`: 84/84 at `name:*`.
- Bu 84 atın historical `horse_races.horse_key` ile doğrudan eşleşmesi: `0`.
- Kod sırası: snapshot insert -> resolver -> `race_program_entries` delete/insert.

**Etkilenen dosyalar**

- `update_race_programs.py`
- `snapshot_store.py`
- `build_asof_features.py`

**Çözüm**

Resolver çağrısını `race_program_entries` transaction'ı tamamlandıktan sonraya
taşı. İsim eşleşmesini normalize edilmiş ad + tarih + şehir/race bağlamıyla yap;
ambiguous eşleşmeyi otomatik doğrulama. Immutable snapshot gereği doğrudan update
yerine canonical identity mapping tablosu üzerinden çözüm tercih et.

**Test komutu**

```bash
python -m pytest tests/test_tjk_resolver.py tests/test_pipeline.py -q
python update_race_programs.py
```

## 8. Canlı Historical Özellikler Yüzde 100 Eksik

**Sorun**

`build_asof_features.py`, `program.horse_id` değerlerini
`horse_races.horse_key IN (...)` ile doğrudan arıyor; `horse_links` tablosunu
kullanmıyor. Son canlı frame tamamen `name:*` olduğu için history bulunamıyor.

**Kanıt**

- Son as-of: 84 satır / 8 yarış.
- `days_since_last_race`, son 3/5/10, surface/distance/track win rate,
  jockey/trainer uyumu ve değişim kolonları: 84 satırın 84'ünde NULL.
- As-of atlarının historical direct match sayısı: `0`.
- Modelin güçlü özelliklerinden `last_3_avg_position` canlıda tamamen yok.

**Etkilenen dosyalar**

- `build_asof_features.py`
- `update_race_programs.py`
- `backfill_tjk_links_from_program.py`
- `pedigreeall_core.py`
- `shadow_mode.py`

**Çözüm**

Önce canonical identity resolver ile program atlarını historical key'e çevir,
sonra history sorgusunu resolved key üzerinden yap. Build sonunda kritik derived
özellikler için coverage eşiği uygula. Örneğin yarış bazında history coverage
`< %80` ise prediction freeze'i fail-closed durdursun ve `NO_HISTORY_LINK` kodu
üretsin.

**Test komutu**

```bash
python build_asof_features.py
python -c "import pandas as pd; f=pd.read_parquet('output/asof_features.parquet'); print(f[['days_since_last_race','last_3_avg_position','track_win_rate']].notna().mean())"
python -m pytest tests/test_feature_leakage_gate.py tests/test_training_safety.py -q
```

## Çözüm Uygulama Sırası

1. Windows path fallback'i deploy et ve migration/test yolunu doğrula.
2. `update_race_programs.py` resolver sırasını düzelt.
3. Canonical horse identity migration ve idempotent backfill uygula.
4. `build_asof_features.py` history lookup'ını resolver üzerinden geçir.
5. Derived feature coverage kalite kapısını ekle.
6. Daily ve race-freeze timer healthcheck'lerini zorunlu yap.
7. Bir yarış günü boyunca prediction ve feature snapshot üretimini doğrula.
8. Resmi sonuçlardan `prediction_results` reconciliation çalıştır.
9. Ancak canlı Top1/Top3 kapsamı oluşunca model kalite/ROI değerlendirmesine geç.
