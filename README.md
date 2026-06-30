# Pedigreeall Türkiye At Veri Gölü

Python 3.11+ ile, dış CSV gerektirmeden Pedigreeall API'de erişilebilen Türkiye atlarını keşfeden, ham JSON'u koruyan, ilişkisel tablolara normalize eden ve CSV/Parquet analitik çıktıları üreten pipeline.

API sözleşmesi 20 Haziran 2026 tarihinde [resmî ASP.NET Help kataloğu](https://api.pedigreeall.com/Help) üzerinden doğrulandı. Endpoint kataloğu her çalışmada yeniden keşfedilebilir; uydurma rota yoktur.

## Dizin yapısı

```text
discover_endpoints.py       # Help indeksindeki bütün endpoint'leri kataloglar
probe_public_endpoints.py   # anonim erişimi güvenli biçimde sınıflandırır
discover_horses.py          # Türkiye TJK listesi + ülke filtreli HORSE_ID taraması
scrape_pedigreeall.py       # keşfedilmiş tüm atları toplar
normalize_data.py           # raw JSON -> ilişkisel model
analyze_dataset.py          # kalite raporu ve CSV/Parquet veri gölü
pedigreeall_core.py         # HTTP, retry, rate limit, SQLite ve şema
pedigreeall_progress.db     # checkpoint + warehouse
DATA_DICTIONARY.md
requirements.txt
tests/
lake/analytics/             # üretilecek analitik çıktılar
```

## Kurulum

```bash
cd /opt/at_yaris_tahmini
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Bu sürümde `PUBLIC_ONLY_MODE = True` olduğu için Authorization başlığı gönderilmez. Gelecekte yetkili moda geçilecekse bu sabit bilinçli olarak kapatılmalıdır.

## API anahtarsız public-only çalışma

```powershell
# 1. Help indeksindeki bütün endpoint imzalarını hızlıca katalogla
python discover_endpoints.py --index-only

# İstenirse 320 Help detay sayfasından request/response örneklerini de çıkar
python discover_endpoints.py --rps 1

# 2. Güvenli endpoint'leri anonim probela ve erişim raporlarını üret
python probe_public_endpoints.py --rps 0.5

# 3. Yarış programı + TJK ID aralığı + public graph stratejileriyle keşfet
python discover_horses.py --tjk-start 1 --tjk-end 100000 --race-days 365 --rps 0.75

# 4. Keşfedilen bütün atların yalnız public ayrıntılarını topla
python scrape_pedigreeall.py --rps 0.75 --concurrency 3 --batch-size 100

# 5. İstenirse raw katmandan normalizasyonu baştan çalıştır
python normalize_data.py

# 6. CSV/Parquet ve public-mode kalite raporlarını üret
python analyze_dataset.py --output lake/analytics

# Test
python -m unittest discover -s tests -v
```

Uzun ID taramalarını dilimleyerek çalıştırabilirsiniz (`1–100000`, `100001–200000` gibi); cursor SQLite'ta tutulur. İlk smoke test için `--tjk-start 1 --tjk-end 20 --no-race-program --no-graph` kullanın.

Tam TJK liste endpoint'i servis/bant genişliği nedeniyle zaman aşımına uğrarsa hata kaydedilir ve ülke filtreli keşif devam eder. Sonraki çalışmalarda yalnız sayfalı keşfi çalıştırmak için `discover_horses.py --skip-tjk-list` kullanın.

20 Haziran 2026 anonim smoke testinde `Country/Get` erişilebilirken `Horse/GetFilter` HTTP 401 döndürdü; tam sayfalı HORSE_ID keşfi için yetkili API anahtarı gerekir. Sistem bu durumu `progress` ve `access_restrictions` tablolarında açıkça raporlar. Anahtarsız modda erişilemeyen kayıtlar “eksiksiz çekildi” olarak işaretlenmez.

`PUBLIC_ONLY_MODE = True` hem keşif hem çekim kodunda aktiftir. 401/403 normal hata sayılmaz; `access_restrictions` ve `requires_api_key_endpoints` raporuna yazılır. Daha önce kısıtlı olduğu belirlenen endpoint her at için tekrar tekrar çağrılmaz.

### Public fallback sırası

1. Kısa timeout ile `Tjk/getHorseListFromTjk` denenir. Endpoint pagination/filtre parametresi sunmadığından doğrudan bölünemez.
2. `Tjk/GetRaceProgram` tarih dilimleri denenir; programdan TJK_ID/HORSE_ID ve AGF dâhil yarış programı alanları çıkarılır.
3. `Tjk/Get?p_iTjkId=` yapılandırılmış ID aralığında taranır. Bu yöntem anonim smoke testinde gerçek kayıt döndürmüştür.
4. `HorseInfo/GetById` aralık taraması yalnız endpoint public ise çalışır; 401 işaretinden sonra otomatik atlanır.
5. Public bulunan HORSE_ID'lerden pedigree, ebeveyn, kardeş ve tay grafiği BFS ile `--graph-depth`/`--graph-max-nodes` sınırlarında genişletilir. Mevcut anonim erişimde bu aile endpoint'leri 401 olduğu için kapsam 0'dır.

Belgelenmiş public harf-bazlı at arama endpoint'i doğrulanmadığından isim harfi taraması uydurulmamıştır.

Uzun tam public taramayı tek komutla resumable çalıştırmak için:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_full_public_pipeline.ps1
```

Seyrek anonim problar 127.000'de dolu, 128.000 ve üzerinde boş örnekler gösterdiği için runner `1–128000` aralığını tarar. Bu gözlemsel üst sınır kesin API sözleşmesi değildir; gelecekte yeni kayıtlarla artırılmalıdır.

### Anonim smoke test sonucu

- Help indeksinde kataloglanan endpoint: 320
- Kontrollü probelenen çekirdek endpoint: 19
- `public_available`: 5
- `requires_api_key`: 12
- `timeout`: 2
- TJK ID 1–20 aralığından gerçek dolu at: 19
- Normalize yarış satırı: 339

Bu sayılar tam evren iddiası değildir; `lake/analytics/data_quality_report.json` kapsamı açıkça gösterir.

Erişim raporları `reports/public_mode/` altındadır: `public_endpoints`, `requires_api_key_endpoints`, timeout/not-found/server-error, `unprobed_safe_endpoints` ve `not_probed_unsafe_endpoints` CSV/JSON dosyaları.

## Otomatik at keşfi

Keşif iki doğrulanmış kaynağı birleştirir:

1. `GET Tjk/getHorseListFromTjk`: parametresiz TJK listesi. `TJK_AT_ID`, `TJK_ID`, ad, ırk, cinsiyet, ebeveynler, yaş, sahip, yetiştirici, antrenör, doğum, kazanç ve kariyer derecelerini döndürür. Liste endpoint'i sayfalama sunmadığından yanıt tek parçada alınır.
2. `GET Country/Get` ile Türkiye'nin gerçek `COUNTRY_ID` değeri bulunur. Ardından `POST Horse/GetFilter` gövdesindeki `COUNTRY_ID`, `PAGE_NO`, `PAGE_COUNT` kullanılarak bütün Pedigreeall `HORSE_ID` kayıtları sayfalanır.

`TJK_AT_ID`, Pedigreeall `HORSE_ID` kabul edilmez. İki evren `ad+baba+anne` kesin eşleşmesiyle; gerekirse RapidFuzz ağırlıklı skoru ile bağlanır. Fuzzy bağ ancak eşik ≥97 ve ikinci adaya en az 3 puan fark olduğunda doğrulanır. Kanıt ve güven `horse_links` tablosunda saklanır.

## Doğrulanmış toplama endpoint'leri

| Endpoint | Parametre | Kullanım / temel alanlar |
|---|---|---|
| `GET Tjk/Get` | `p_iTjkId` | Tüm yarışlar; tarih, şehir, mesafe, pist, sonuç, derece, kilo, takı, jokey, ganyan, grup, antrenör, sahip, HP, ikramiye, video/foto; kariyer başlıkları |
| `GET Tjk/GetHorseFromTjk` | `p_iTjkId` | Doğum, start/dereceler, kazanç, handikap, G1/G2/G3, genel/çim/kum/sentetik alanları |
| `GET HorseInfo/GetById` | `p_iId` | HORSE_ID, profil, ebeveyn ID'leri, cinsiyet, renk, aile, sahip, yetiştirici, antrenör, görsel, kariyer |
| `GET Pedigree/GetPedigree` | `p_iGenerationCount=5`, `p_iFirstId`, `p_iSecondId=0` | Beş nesil pedigree hücreleri ve her hücrenin mevcut tüm bilgisi |
| `GET Sibling/GetSiblingFromMother` | `p_iHorseId` | Maternal kardeşler |
| `GET Sibling/GetSiblingFromFather` | `p_iHorseId` | Paternal kardeşler |
| `GET Sibling/GetSiblingFromBroodmareSire` | `p_iHorseId` | Kısrak babası kardeşleri |
| `GET Progeny/GetProgeny` | `p_iHorseId` | Tay profilleri, kazanç ve performans alanları |
| `GET ImageInfo/GetById` | `p_iHorseId` | `INFO`, `IMAGE`, `IMAGE_LIST` |
| `GET FamilySuccess/Get` | `p_iHorseId` | Belgelenmiş aile başarı yanıtı; raw katmanda eksiksiz korunur |

`POST` ekleme/güncelleme/silme, giriş, sipariş ve rapor üretme endpoint'leri kataloglanır fakat `state_change_or_auth` olarak devre dışı bırakılır. Yalnızca belgelenmiş filtre POST'ları `read_filter` kabul edilir.

## Veri yaşam döngüsü ve güvenilirlik

- Tek `aiohttp.ClientSession`, TCP havuzu ve DNS cache kullanılır.
- Global token aralığıyla rate limit; semaphore ile concurrency sınırı vardır.
- 429, 5xx, ağ ve timeout hataları Tenacity exponential backoff+jitter ile yeniden denenir. Diğer 4xx tekrar edilmez.
- Her istek parametre+gövde imzasıyla tekilleştirilir; raw JSON ve SHA-256 SQLite'a yazılır.
- WAL, kısa transaction ve endpoint/entity checkpoint'leri sayesinde kesinti sonrası devam edilir.
- `completed` atlar tekrar çekilmez; `partial` yeniden çalıştırılabilir. `--force` tamamlanmışları da yeniler.
- Normalize tablolar idempotent `INSERT OR REPLACE` anahtarları kullanır.
- CSV ve Parquet dışa aktarımı 100.000 satırlık chunk'larla yapılır.

## Doğrudan, türetilmiş ve desteklenmeyen veri

Doğrudan API: profil, ebeveynler, yarış satırları, jokey/antrenör/sahip, kazanç, derece, grup, kardeş, tay, soy, görsel ve API'nin raw yanıtındaki diğer alanlar.

Türetilmiş: doğum yılından yaş; yarışlardan yüzey, mesafe, mevsim, jokey ve antrenör kırılımları. Bunlar `horse_statistics` içinde açıkça türetilmiş JSON'dur.

Dokümante edilmeyen AGF `null` kalır. Sağlık, veteriner, aşı, beslenme, uyku, mental analiz, stres, piyasa değeri ve gizli yetiştiricilik kayıtları `not_supported_by_api` olarak tutulur. API'deki `PRICE` alanı semantiği/güncelliği kanıtlanmadığı için piyasa değeri sayılmaz.

## Sınırlamalar ve kapsam tanımı

- “Tümü”, API'nin mevcut kimlik doğrulama seviyesiyle listelediği ve Türkiye filtresinden döndürdüğü kayıtlardır; gizli/silinmiş/yetkisiz kayıtların varlığı kanıtlanamaz.
- `Tjk/getHorseListFromTjk` pagination sunmaz; en büyük tek-yanıt bellek riski budur.
- Servis yayımlanmış kota belirtmez. 429 oranı izlenmeli, gerektiğinde RPS düşürülmelidir.
- Bazı atların yalnızca TJK veya yalnızca HORSE_ID kaydı olabilir. Bunlar kaybedilmez; ayrı entity olarak işlenir.
- Pedigree hücrelerinin gerçek doluluğu ata göre değişebilir; istek her zaman 5 nesildir.

## Test ve kabul planı

1. Şema ve zorunlu 12 tablonun varlığı.
2. Endpoint Help parser'ında GET/POST, query ve JSON şema ayrımı.
3. Türkiye ülke ID'sinin ad üzerinden bulunması; sabit ID kullanılmaması.
4. Pagination'ın kısa sayfada bitmesi ve checkpoint'ten devamı.
5. TJK/HORSE_ID'nin karıştırılmaması; kesin/fuzzy/ambiguous eşleşmeler.
6. 200, 404, 429→200, 500→200, timeout ve JSON olmayan yanıtlar.
7. Raw SHA-256, request deduplication ve normalize idempotency.
8. 5 nesil pedigree, kardeş türleri, tay ve medya normalizasyonu.
9. 100 bin+ yarışta bellek ve Parquet/CSV/SQLite satır sayısı eşitliği.
10. Gerçek API'de `--max-pages 1`, `--limit 10` smoke testi; Help şemasıyla alan kontrolü.

## Linux VPS shadow deployment

Dağıtım paketi üretmek için:

```bash
python create_vps_bundle.py
```

Paket VPS üzerinde `/opt/at_yaris_tahmini` altına açıldıktan sonra:

```bash
cd /opt/at_yaris_tahmini
sudo bash deploy/install_vps.sh
systemctl list-timers 'at-yaris-*'
sudo -u at_yaris /opt/at_yaris_tahmini/.venv/bin/python healthcheck.py
```

Kurulum günlük program pipeline'ını, dakikalık AGF kontrolünü, beş dakikalık global sonuç kontrolünü, race-level final prediction freeze scheduler'ını ve yedekleme timer'larını etkinleştirir. Programda bulunan yabancı/Karma pistler görünür kalır; kaynağı desteklenmeyenler `SOURCE_UNSUPPORTED` durumuyla ağır sonuç sorgusundan çıkarılır. Ortam ayarları `.env`, servis tanımları `deploy/systemd/`, log rotasyonu `deploy/logrotate/` altındadır.

Read-only FastAPI dashboard `at-yaris-web.service` ile çalışır. HTML sayfaları ve `/api/*` uçları Basic Auth gerektirir; SQLite bağlantısı `mode=ro` ve `query_only` kullanır. Opsiyonel Nginx reverse proxy yapılandırması `deploy/nginx/at-yaris-dashboard.conf` dosyasındadır.

## Production Deploy ve Backup Sistemi

Mevcut sistem, tamamen Git tabanlı ve sıfır-kesinti odaklı bir deploy ve yedekleme (backup) altyapısına sahiptir.

### Geliştirme ve Deploy Akışı

1. **Geliştirme (Local):**
   Kod değişiklikleri yapıldıktan sonra yerel ortamda test edilir ve GitHub reposuna gönderilir:
   ```bash
   git commit -m "feat: yeni özellik"
   git push origin main
   ```

2. **Dağıtım (VPS - deploy.sh):**
   VPS üzerinde `/opt/at_yaris_tahmini/deploy.sh` scripti çalıştırılarak deploy akışı başlatılır:
   ```bash
   sudo ./deploy.sh
   ```
   - **Deploy Yedekleme:** Canlı kod ve konfigürasyon güncellenmeden önce `.env`, systemd servisleri ve `requirements.txt` gibi kritik dosyaların bir yedeği `/var/backups/at_yaris_tahmini/deploy_backups/` altına alınır. En fazla son 3 deploy yedeği saklanır.
   - **Git Reset:** Sunucu `git fetch origin` ve `git reset --hard origin/main` komutlarıyla GitHub'daki en güncel sürümle senkronize edilir. Canlı SQLite veritabanı ezilmez.
   - **Migration:** Yeni bir veritabanı şema güncellemesi varsa otomatik olarak `migrate_provenance_schema.py` aracılığıyla uygulanır.
   - **Servis Yeniden Başlatma:** Systemd daemon-reload yapılarak `at-yaris-web.service`, `at-yaris-results-update.timer` ve `at-yaris-race-freeze.timer` servisleri yeniden başlatılır.
   - **Sağlık Kontrolü (Health Check):** `/health` endpoint'i üzerinden web sunucusunun durumu, SQLite `query_only` readonly bağlantı güvencesi ve systemd zamanlayıcılarının çalışması doğrulanır.
   - **Raporlama:** Deploy sonucu `reports/deploy_report_YYYYMMDD_HHMMSS.md` dosyasına rapor olarak yazılır.

### Geri Alma (Rollback) Akışı

Bir hata durumunda son 3 başarılı deploy yedeklerinden birine geri dönmek için:
1. İlgili deploy yedeği `/var/backups/at_yaris_tahmini/deploy_backups/` altından çıkarılır.
2. Kod tabanı önceki kararlı git commit hash'ine resetlenir:
   ```bash
   git reset --hard <onceki_commit_hash>
   ```
3. Servisler yeniden başlatılır.

### Veritabanı Yedekleme (Backup) Politikası

Canlı veritabanı `pedigreeall_progress.db` dosyasının yedeklenmesi `backup_db.py` scripti ile SQLite online hot-backup yöntemiyle gerçekleştirilir:
- **Konum:** `/var/backups/at_yaris_tahmini/`
- **Retention (Yedek Saklama Süreleri):**
  - `daily` (Günlük): Son 7 günün yedeği.
  - `weekly` (Haftalık): Son 4 haftanın yedeği.
  - `monthly` (Aylık): Son 6 ayın yedeği.
- Eski yedekler otomatik olarak silinir (Pruning).

### Gece Temizliği ve Log Yönetimi (cleanup.sh)

Her gece 04:00'te çalışan `cleanup.sh` otomasyonu:
- 7 günden eski deploy yedeklerini siler.
- 30 günden eski AGF HTML indirme önbelleğini (`data/agfv2_raw/html/`) temizler.
- 30 günden eski geçici raporları siler.
- Pip, python `__pycache__` ve pytest cache dosyalarını temizleyerek disk kullanımını optimize eder.
- Loglar `logrotate` ile günlük olarak sıkıştırılıp (compress) 14 gün saklanır ve journalctl logları 7 gün ile sınırlandırılır.
