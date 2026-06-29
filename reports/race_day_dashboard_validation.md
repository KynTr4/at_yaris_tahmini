# Race-Day Dashboard Validation

Tarih: 2026-06-28

## Durum

**PASS**

- Yarış evreni `program_snapshots` içindeki seçili günün bütün `race_id` kayıtlarıdır.
- Prediction veya result bulunmaması yarış satırını listeden düşürmez.
- Top-1, yarışın en son pre-race prediction run'ındaki en yüksek `ensemble_probability` değeridir.
- Resmi kazanan, `race_results` içindeki son `finished / finish_position=1` kaydıdır.
- Performance yalnız prediction + resmi kazanan + program horse mapping bulunan ve unsupported olmayan yarışları kullanır.
- Bütün sorgular web uygulamasının SQLite `mode=ro / query_only` bağlantısını kullanır.

## Endpointler

- `/api/race-day/summary?date=YYYY-MM-DD`
- `/api/race-day/tracks?date=YYYY-MM-DD`
- `/api/race-day/races?date=YYYY-MM-DD&track=...`
- `/api/race-day/performance?date=YYYY-MM-DD&track=...`

## Track Özeti

Her track için:

- `program_races`
- `prediction_races`
- `result_races`
- `evaluated_races`
- `missing_result_races`
- `missing_reason`
- `tjk_id_missing_count`
- `unsupported_source_count`

## Yarış Durumları

- `Sonuç çekildi`
- `Sonuç bekleniyor`
- `TJK ID eksik`
- `Kaynak desteklenmiyor`
- `Tahmin yok`
- `Eşleşme hatası`

## Test Kanıtı

Sentetik 2026-06-28 fixture'ı İstanbul, İzmir, Karma, Belmont, Woodbine, Hawthorne ve Selangor olmak üzere yedi track içerir.

- API yedi track'in tamamını döndürdü.
- İstanbul prediction+result ile evaluate edildi.
- İzmir prediction var/result yok durumunda `Sonuç bekleniyor` ve mandatory warning üretti.
- Belmont/Karma listede kaldı ve `Kaynak desteklenmiyor` gösterdi.
- Unsupported yarışlar race-day performance metriğine alınmadı.
- Track filtresi ve SQLite query-only yazma reddi doğrulandı.

Gerçek yerel 2026-06-26 smoke testinde API 8 track ve 64 yarış döndürdü; foreign/Karma track'ler gizlenmedi.
