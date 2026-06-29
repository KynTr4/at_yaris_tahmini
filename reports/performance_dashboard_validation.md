# Tahmin Performansı Dashboard Doğrulaması

Tarih: 2026-06-28

## Durum

**PASS**

- Mevcut FastAPI/Jinja/Bootstrap mimarisi korundu.
- Yeni tahmin sistemi, scheduler, migration veya tablo eklenmedi.
- Kaynaklar yalnızca `prediction_snapshots`, `race_results` ve at/hipodrom adı için `program_snapshots`.
- Bütün bağlantılar SQLite `mode=ro` ve `PRAGMA query_only=ON` üzerinden çalışıyor.
- Mevcut global Basic Auth middleware `/performance` ve bütün yeni API uçlarını kapsıyor.

## Performans Veri Sözleşmesi

Her `race_id + prediction_time + model` grubu için model olasılığı en yüksek at Top-1 seçimdir. Eşitlikte `horse_id` deterministik bağlayıcıdır. Modeller mevcut dört olasılık kolonundan okunur: Logistic, CatBoost, XGBoost ve Ensemble.

En son `finished` sonucu `race_results` içinden `captured_at, result_id` sırasıyla seçilir. Top-1 at kazananlar arasında bulunuyorsa `correct=1`; aksi halde `correct=0`.

- Doğru ve oran mevcut: `net_return = result_odds - 1`
- Yanlış: `net_return = -1`
- Doğru fakat oran eksik: doğruluk metriğine dahil, ROI pay/paydasına dahil değil
- ROI: `100 * SUM(net_return) / COUNT(net_return)`

## SQL Optimizasyonu

`run_maxima` CTE'si her prediction run için dört model maksimumunu tek taramada çıkarır. Yalnızca maksimuma eşit adaylar model satırlarına açılıp window ranking'e gönderilir. Böylece 50.000 prediction satırı doğrudan 200.000 satırlık window-sort işlemine sokulmaz.

Diğer CTE'ler:

- `ranked_results/latest_results`: append-only sonuçların son resmi görünümü
- `ranked_programs/latest_programs`: at adı, hipodrom ve koşu bilgisi
- `winners`: dead-heat dahil kazanan kümesi
- `evaluation_core/evaluated`: correctness, decimal odds ve birim getiri

History sorgusu `COUNT(*) OVER()` ile toplam ve 100 satırlık sayfayı tek sorguda döndürür. Özet/model/chart sonuçları filtre anahtarlı 30 saniyelik, en fazla 256 elemanlı bellek önbelleğine sahiptir.

## 50K Benchmark

Geçici SQLite üzerinde 5.000 yarış × 10 at = 50.000 `prediction_snapshots` satırı:

| Sorgu | Soğuk süre |
| --- | ---: |
| Summary | 351,4 ms |
| History, ilk 100 kayıt | 375,6 ms |

Hedef: **<500 ms — PASS**. `/performance` HTML kabuğu ölçümü 26,8 ms; özet, grafik ve tablo tarayıcıda paralel API çağrılarıyla yüklenir.

## Test Kapsamı

- Basic Auth: HTML/API/static 401 ve yetkili 200
- SQLite read-only/query-only yazma reddi
- Model bazlı Top-1 seçimi
- Kazanan eşleştirme
- Doğruluk, ROI ve net kâr hesabı
- Tarih/hipodrom/model/doğru-yanlış filtreleri
- Geçersiz model filtresinin 400 dönmesi
- 100 kayıt pagination ve ikinci sayfa
- 30 günlük chart ve kümülatif kâr
- Hipodrom/model filtre seçenekleri
- Mevcut probability-sum ve path traversal kontrolleri

## Mock Görseller

- `reports/mock_performance_desktop.png`
- `reports/mock_performance_mobile.png`
