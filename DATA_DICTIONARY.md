# Veri sözlüğü

| Tablo | Anahtar | İçerik |
|---|---|---|
| `endpoint_catalog` | `endpoint_key` | Help'ten bulunan method/path, URI ve body parametreleri, örnek request/response şemaları, Help URL, güvenlik sınıfı, doğrulama zamanı |
| `discovered_horses` | `source, source_record_id` | TJK listesi veya Türkiye filtre sayfasındaki keşif kaydı; TJK_ID ve HORSE_ID ayrı kolonlardır; özgün kayıt JSON'u korunur |
| `horse_links` | `tjk_id` | TJK_ID→HORSE_ID bağlama yöntemi, güven, kanıt ve doğrulama bayrağı |
| `horse_profiles` | `horse_key` | Birleşik profil; `horse_key` doğrulanmış iç ID varsa `horse:{id}`, yoksa `tjk:{id}` |
| `horse_pedigrees` | `horse_key,generation,position` | En az 5 nesil istenen pedigree hücresi, ata/ebeveyn ID'leri ve hücrenin tüm JSON bilgisi |
| `horse_races` | `horse_key,race_id` | Tarih, hipodrom, mesafe, pist, sınıf/grup, sonuç, derece, AGF, ganyan, jokey, antrenör, ikramiye ve medya |
| `race_program_entries` | tarih/şehir/koşu/TJK | Public yarış programından TJK_ID, HORSE_ID, AGF, ganyan, jokey, antrenör, kilo ve program verisi |
| `horse_statistics` | `horse_key` | Kariyer toplamları ve yarıştan türetilen yüzey/mesafe/mevsim/jokey/antrenör JSON kırılımları |
| `horse_siblings` | `horse_key,relation_type,sibling` | `maternal`, `paternal`, `broodmare_sire` kardeşler ve profil JSON'u |
| `horse_progeny` | `horse_key,progeny` | Tay adı/ID, kazanç, start, galibiyet, istatistik ve profil JSON'u |
| `horse_media` | `horse_key,media_type,url` | Profil, ebeveyn, ana görsel ve galeri medyası |
| `raw_api_responses` | `request_key` | İstek URL/params/body, HTTP durum, ham JSON, SHA-256 ve UTC çekim zamanı |
| `progress` | `work_type,entity_key,endpoint_key` | Durum, deneme, pagination cursor, mesaj ve zamanlar |
| `errors` | `id` | İş/entity/endpoint, hata tipi, HTTP durum, mesaj, deneme ve zaman |
| `endpoint_probe_results` | `endpoint_key` | `public_available`, `requires_api_key`, `timeout`, `not_found`, `server_error` sınıfı, HTTP durum, gecikme ve örnek parametre |
| `access_restrictions` | `endpoint_key` | 401/403 kısıtları; normal hata tablosundan ayrıdır |

## Temel alan semantiği

- `tjk_id`: TJK'nin at kimliği; string saklanır, leading-zero kaybı olmaz.
- `horse_id`: Pedigreeall iç at kimliği; integer.
- `source_record_id`: TJK kaynağında `TJK_AT_ID` olabilir; `horse_id` değildir.
- `birth_year`, `age`: doğum tarihinden türetilir.
- `agf`: belgelenmiş TJK yarış şemasında yoktur; `NULL`.
- `extra_fields_json`: normalize kolonlara sığmayan fakat API'nin döndürdüğü profil alanlarını kayıpsız tutar.
- `raw_fields_json`: yarış satırının özgün alanlarıdır.
- `unsupported_fields_json`: desteklenmeyen alanların her birini `not_supported_by_api` olarak işaretler.

## Eksik değer standardı

- `NULL`: API alanı destekliyor fakat kayıt için değer dönmedi.
- `not_available`: kaynakta alan varlığı/erişimi belirsiz.
- `not_supported_by_api`: Help şemasında güvenilir kaynak bulunmayan kavram.

Desteklenmeyenler: sağlık, veteriner, aşı, beslenme, uyku, mental analiz, stres skoru, piyasa değeri ve gizli yetiştiricilik kayıtları.

## Immutable provenance tabloları (schema v3)

- `program_snapshots`: Append-only yarış programı gözlemleri. Sertifikalı builder
  yalnızca `captured_at < race_start_at` satırlarını kabul eder.
- `agf_snapshots`: Kaynak capture kimliğine bağlı append-only AGF gözlemleri.
- `odds_snapshots`: Append-only canlı program oranları; sonuç tablosundaki nihai
  `GNY` bu tabloya kopyalanmaz.
- `race_results`: İzole append-only post-race sonuçları. Yalnızca önceki yarış
  geçmişinde kullanılır; hedef yarış girdisi sağlamaz.
- `schema_migrations`: Uygulanan migration adları ve UTC zamanları.

`horse_races` ve `race_program_entries` geriye uyumluluk tablolarıdır.
`build_asof_features.py` bunları sorgulamaz ve v2 leakage PASS kapsamına almaz.

## Shadow monitoring tabloları

- `prediction_snapshots`: Model/pipeline sürümü, tahmin zamanı, yarış başlangıcı,
  dört model olasılığı, feature hash ve tam feature JSON'u içeren immutable gölge
  tahmin arşivi.
- `prediction_results`: Resmi sonuçların tahminlerden ayrı immutable eşlemesi.
- `shadow_monitoring_runs`: Günlük leakage, contract, coverage, drift,
  calibration ve readiness durumlarının append-only sağlık arşivi.
