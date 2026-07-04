"""VPS disk temizleme: Parquet karşılığı olan büyük CSV dosyaları siler.

Çalıştırma:
    python clean_large_csvs.py           # önizleme (silmez)
    python clean_large_csvs.py --delete  # gerçekten siler
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

# Parquet karşılığı olan ve silinmesi güvenli büyük CSV'ler
# (output/ ve lake/analytics/ içinde — .gitignore'da olduklarından git'e dahil değiller)
SAFE_TO_DELETE = [
    # lake/analytics — parquet karşılıkları var
    "lake/analytics/discovered_horses.csv",
    "lake/analytics/horse_races.csv",
    "lake/analytics/horse_profiles.csv",
    "lake/analytics/horse_statistics.csv",
    "lake/analytics/horse_pedigrees.csv",
    "lake/analytics/horse_progeny.csv",
    "lake/analytics/horse_siblings.csv",
    "lake/analytics/horse_media.csv",
    "lake/analytics/race_program_entries.csv",
    "lake/analytics/errors.csv",
    # output/ — ara sonuç / yeniden üretilebilir dosyalar
    "output/final_benter_dataset.csv",  # parquet var: output/final_benter_dataset.parquet
    "output/benter_features_with_komiser.csv",  # ara dosya
    "output/benter_features_enriched.csv",  # ara dosya
    "output/benter_features_base.csv",  # ara dosya
    "output/expanded_horse_races.csv",  # ara dosya
    "output/expanded_horse_profiles.csv",  # ara dosya
    "output/margins_data.csv",  # yeniden üretilebilir
    "output/workouts.csv",  # yeniden üretilebilir
    "output/agf_data.csv",  # yeniden üretilebilir
    "output/backtest_predictions_v2.csv",  # eski backtest
    "output/backtest_predictions.csv",  # eski backtest
    "output/roi_simulation_v2.csv",  # eski simülasyon
    "output/roi_simulation.csv",  # eski simülasyon
    "output/race_starter_coverage.csv",  # yeniden üretilebilir
    "output/track_conditions.csv",  # yeniden üretilebilir
    "output/komiser_raw_text.csv",  # ham veri
    "output/today_features_base.csv",  # günlük üretim dosyası
    "output/asof_features.csv",  # parquet var: output/asof_features.parquet
]

# Kesinlikle SİLME — web app veya pipeline tarafından kullanılıyor
KEEP = {
    "output/model_predictions.csv",  # predict_today.py çıktısı (web app okuyabilir)
    "output/calibration_table.csv",
    "output/calibration_table_v2.csv",
    "output/model_scores.csv",
    "output/model_scores_v2.csv",
    "output/feature_drift.csv",
    "output/live_metrics.csv",
    "output/model_drift.csv",
    "output/shadow_predictions.csv",
    "output/prediction_history.csv",
    "output/raw_field_coverage.csv",
    "failed_updates.csv",
    "archived_failed_updates.csv",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delete", action="store_true", help="Dosyaları gerçekten sil")
    parser.add_argument(
        "--min-mb", type=float, default=0, help="Bu MB'den küçük dosyaları atla"
    )
    args = parser.parse_args()

    total_freed = 0
    deleted = 0
    skipped = 0

    for rel in SAFE_TO_DELETE:
        path = PROJECT_ROOT / rel
        if not path.exists():
            continue
        size_bytes = path.stat().st_size
        size_mb = size_bytes / 1024 / 1024
        if size_mb < args.min_mb:
            continue
        # Güvenlik kontrolü: KEEP listesinde olmamalı
        if rel in KEEP:
            print(f"  KORUNUYOR  {rel} ({size_mb:.1f} MB)")
            skipped += 1
            continue

        total_freed += size_bytes
        if args.delete:
            path.unlink()
            print(f"  SİLİNDİ   {rel} ({size_mb:.1f} MB)")
            deleted += 1
        else:
            print(f"  SİLİNECEK {rel} ({size_mb:.1f} MB)")

    total_mb = total_freed / 1024 / 1024
    total_gb = total_mb / 1024
    print()
    if args.delete:
        print(f"✓ {deleted} dosya silindi, {total_gb:.2f} GB boşaltıldı.")
    else:
        print(
            f"Önizleme: {deleted + (len(SAFE_TO_DELETE) - skipped)} dosya, ~{total_gb:.2f} GB silinebilir."
        )
        print("Gerçekten silmek için: python clean_large_csvs.py --delete")


if __name__ == "__main__":
    main()
