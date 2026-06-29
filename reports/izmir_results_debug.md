# İzmir Results Debug

Tarih: 2026-06-28

## Bulgular

VPS gözlemi: `race_results` içinde yalnız İstanbul'a ait 6 yarış mevcut; İzmir ve yabancı/Karma programları eksik.

Bu çalışma alanındaki yerel DB kopyası 2026-06-28 program snapshot/entry verisini içermediği için VPS'deki İzmir at ve yarış sayıları burada doğrudan yeniden sayılamadı. Ancak kod incelemesinde İzmir'i kalıcı olarak dışarıda bırakabilen deterministik hata bulundu:

```text
Eski kontrol: horse_races içinde sonuç varsa atı tamamlanmış kabul et
Gerçek hedef: race_results içinde immutable sonuç varsa tamamlanmış kabul et
```

İzmir sonucu legacy `horse_races` tablosuna daha önce yazılmış, fakat `race_results` as-of mimarisine aktarılmamışsa eski runner bu atı her çalışmada `continue` ile atlıyordu. İstanbul sonuçları aynı anda ilk kez çekildiyse yalnız İstanbul'un `race_results` içinde görünmesi bu davranışla uyumludur.

## Düzeltme

- Completion source-of-truth `race_results` olarak değiştirildi.
- Legacy sonuç var fakat immutable sonuç yoksa kayıt yeniden fetch/map akışına girer.
- Son iki takvim günü varsayılan olarak yeniden kontrol edilir; gece sonrası eksik mandatory sonuçlar tekrar denenir.
- İstanbul ve İzmir `mandatory` kaynak olarak sınıflandırılır.
- Yabancı/Karma programlar `source_unsupported` warning üretir, servisi failed yapmaz.
- `append_normalized_result=0` artık başarı gibi loglanmaz; `RESULT_NOT_APPENDED` ve coverage reason üretir.

## Yeni Teşhis Nedenleri

- `tjk_id_missing`: program atında çözülebilir TJK ID yok.
- `source_not_published`: TJK ID var, legacy kaynakta tarih sonucu henüz yayımlanmamış.
- `result_mapping_pending`: kaynak sonucu var, immutable yarış eşlemesi henüz oluşmamış veya belirsiz.
- `source_unsupported`: yabancı/Karma pist mevcut sonuç endpoint'i tarafından desteklenmiyor.
- `none`: sonuç `race_results` içinde mevcut.

VPS deploy sonrası kesin İzmir dağılımı `reports/results_coverage_latest.md` ve `output/results_coverage_run.json` içinde track/race bazında görülecektir.
