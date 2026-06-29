# Benter Baseline Models - Evaluation Report

## Veri Seti ve Eğitim Süreci (Data & Training Summary)
- **Kullanılan Toplam Satır:** 360797
- **Train Satır Sayısı:** 347578
- **Test Satır Sayısı:** 13219
- **Kullanılan Toplam Yarış Sayısı:** 53871
- **Train Tarih Aralığı:** 1979-03-31 ile 2010-03-17 arası
- **Test Tarih Aralığı:** 2010-03-18 ile 2026-06-07 arası
- **Data Leakage İçin Çıkarılan Kolonlar:** `finish_time_seconds`, `finish_position`, `prize`, `odds`, `agf`, `ganyan` ve zenginleştirme aşamasında üretilen tüm "dummy" kolonlar (toplam 34 kolon).
- **Kullanılan Toplam Feature Sayısı:** 20

## Model Performans Metrikleri (Yarış Bazında Normalize Edilmiş Skorlar)

Aşağıdaki sonuçlar, atların ham kazanma olasılıklarının her yarış için birbirine oranlanıp toplamının 1.0 yapılması (Race Normalization) sonrası elde edilmiştir.

| Model | Log Loss | Brier Score | Top-1 Accuracy (Yarışın 1.sini Bulma Oranı) |
|---|---|---|---|
| Logistic Regression | 5.9327 | 0.271 | 14.42% |\n| XGBoost | 2.8212 | 0.2683 | 15.11% |\n| CatBoost | 5.9312 | 0.2697 | 15.43% |\n
## Modelin Zayıf Noktaları
1. **Dış Veri Eksikliği**: Orijinal veride AGF, idman, hava ve detaylı pist verileri eksik olduğu için model bu önemli faktörlerden faydalanamamaktadır.
2. **Jokey/Antrenör Yetenekleri**: Kategorik id'ler üzerinden veya basit win rate üzerinden ele alınan jokey/antrenör verileri Elo rating benzeri daha gelişmiş Bayesian yöntemlerle güçlendirilmeye muhtaçtır.
3. **Pist Kalibrasyonu**: Eski yıllardaki ölçümlerin günümüz ile tam bağdaşmayabilmesi.
4. **Veri Dağılımı Zaman Etkisi**: Model 1979'dan 2026'ya kadar çok geniş bir tarih aralığında eğitildi. İleriki aşamalarda eski yıllara (ör. 2000 öncesi) daha düşük ağırlık verilerek (sample weight) güncel trendlerin yakalanması sağlanabilir.

## Bir Sonraki İyileştirme Planı (Next Steps)
1. **Ganyan (Odds) Entegrasyonu**: Lojistik Regresyon baz modeline ganyan/AGF verisini (bulunabildiği çağdaş veri setlerinde) ekleyip halkın tahmini ile modelin farkından (Value Betting) çıkarım yapmak.
2. **Zaman Ağırlıklı (Time-decay) Metrikler**: Sadece son yarışlardaki sırasını almak yerine, atın zirve formunda olup olmadığını ölçen eksponansiyel hareketli ortalamalar (EMA) eklemek.
3. **Kelly Kriteri**: Modele bahis yatırımı yapılıyormuşçasına Kelly stratejisi kodlanıp backtest üzerinden ROI (Return on Investment) hesabı yaptırmak.
