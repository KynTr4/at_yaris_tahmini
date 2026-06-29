# Results Update Production Hardening

Tarih: 2026-06-28

## Durum

**LOCAL VALIDATION: PASS**  
**VPS SYSTEMD ACCEPTANCE: PENDING**

## Lock Sözleşmesi

`results_update.lock` atomik `O_CREAT|O_EXCL` ile oluşturulur ve şu metadata'yı taşır:

```json
{
  "pid": 1234,
  "started_at": "...",
  "hostname": "...",
  "lock_id": "...",
  "runner": "results_update"
}
```

- PID aynı hostta çalışıyorsa yeni çağrı `SKIPPED_ALREADY_RUNNING` ve exit `0` döner.
- PID ölü, metadata bozuk veya host farklıysa lock stale sayılır, silinir ve runner devam eder.
- Normal bitişte yalnızca aynı `lock_id` sahibi lock dosyasını kaldırabilir.
- Linux PID kontrolü `kill(pid, 0)`, Windows kontrolü `OpenProcess` kullanır.

## Exit Politikası

- `SUCCESS/0`: update ve monitor teknik olarak tamamlandı, warning yok.
- `WARNING/0`: snapshot coverage, missed shadow races, insufficient data, drift/calibration/feature warning veya monitoring-only exit 1.
- `SKIPPED_ALREADY_RUNNING/0`: önceki gerçek PID hâlâ çalışıyor.
- `FAILED/1`: DB/schema/integrity problemi, subprocess exception/timeout/traceback, update_results non-zero, sonuç yazma/normalize hatası veya monitoring kaydı oluşmadan shadow monitor hatası.

Monitoring-only exit 1 ancak yeni `shadow_monitoring_runs` kaydı oluşmuş ve stderr'de traceback yoksa warning'e çevrilir.

## Log ve Sayaçlar

`results.log` JSON event satırları ve child stdout içerir. `results.err.log` child stderr ve traceback içerir. Her durumda `results_update_latest.json` atomik olarak yazılır.

Sayaçlar doğrudan SQLite'dan ölçülür:

- `inserted_results_count`: çalışmadan önce/sonra `race_results` satır farkı
- `distinct_result_races_today`: İstanbul zamanı ile bugünkü distinct yarış
- `matched_predictions_count`: shadow monitor öncesi/sonrası `prediction_results` satır farkı

## Systemd

- Timer: 15 dakikada bir, değişmedi.
- Service user: `at_yaris`.
- `TimeoutStartSec=3900`: iki ayrı 1800 saniyelik child adımı ve kapanış kontrolünü kapsar.
- `KillMode=control-group`: timeout/stop sırasında child Python süreçleri de temizlenir.
- `StandardOutput` ve `StandardError` mevcut results loglarına append eder.

## VPS Doğrulama

```bash
sudo rm -f /var/log/at_yaris_tahmini/results_update.lock
sudo systemctl daemon-reload

sudo -u at_yaris /opt/at_yaris_tahmini/.venv/bin/python /opt/at_yaris_tahmini/run_results_update.py
echo $?

sudo systemctl start at-yaris-results-update.service
systemctl status at-yaris-results-update.service --no-pager

cat /var/log/at_yaris_tahmini/results_update_latest.json

sqlite3 /opt/at_yaris_tahmini/pedigreeall_progress.db "
SELECT date(race_start_at), COUNT(DISTINCT race_id), COUNT(*)
FROM race_results
GROUP BY date(race_start_at)
ORDER BY date(race_start_at) DESC;
"
```

Beklenen service sonucu `success`; JSON status değeri `SUCCESS`, `WARNING` veya overlap durumunda `SKIPPED_ALREADY_RUNNING` olmalıdır.
