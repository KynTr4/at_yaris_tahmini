"""Yerel VPS disk kullanımını özetler.

Kullanım:
    python check_vps_space.py            # disk özeti
    python check_vps_space.py --dirs     # dizin boyutları (storage_manager)
    python check_vps_space.py --report   # son storage raporu (JSON)
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

# storage_manager modülünü çağır (mevcut proje köküne göre)
PROJECT_ROOT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dirs", action="store_true", help="Dizin bazlı boyut raporu")
    parser.add_argument(
        "--report", action="store_true", help="Son storage_manager JSON raporunu göster"
    )
    args = parser.parse_args()

    if args.report:
        report_path = PROJECT_ROOT / "reports" / "storage_report.json"
        if report_path.is_file():
            print(report_path.read_text(encoding="utf-8"))
        else:
            print(
                '{"error": "Henüz storage raporu oluşturulmamış. storage_manager.py çalıştırın."}'
            )
        return

    # Disk kullanımı
    usage = shutil.disk_usage(PROJECT_ROOT)
    total_gb = usage.total / 1024**3
    used_gb = usage.used / 1024**3
    free_gb = usage.free / 1024**3
    pct = used_gb / total_gb * 100

    bar_width = 40
    filled = int(bar_width * pct / 100)
    bar = "█" * filled + "░" * (bar_width - filled)
    status = "⚠ UYARI" if pct >= 80 else ("✓ İYİ" if pct < 60 else "↑ DİKKAT")

    print(f"\n{'=' * 50}")
    print(f"  DISK KULLANIMI  [{status}]")
    print(f"{'=' * 50}")
    print(f"  [{bar}] {pct:.1f}%")
    print(f"  Toplam : {total_gb:.1f} GB")
    print(f"  Kullanılan: {used_gb:.1f} GB")
    print(f"  Boş    : {free_gb:.1f} GB")

    if args.dirs:
        print(f"\n  Dizin Boyutları:")
        try:
            from storage_manager import get_dir_sizes

            sizes = get_dir_sizes(PROJECT_ROOT)
            for name, size_bytes in sorted(
                sizes.items(), key=lambda x: x[1], reverse=True
            ):
                if size_bytes == 0:
                    continue
                size_mb = size_bytes / 1024**2
                size_str = (
                    f"{size_mb / 1024:.2f} GB"
                    if size_mb >= 1024
                    else f"{size_mb:.1f} MB"
                )
                bar_len = (
                    min(30, int(30 * size_bytes / usage.used)) if usage.used else 0
                )
                print(f"  {name:<20} {size_str:>10}  {'█' * bar_len}")
        except ImportError:
            # storage_manager yoksa basit du çıktısı
            for path in sorted(PROJECT_ROOT.iterdir()):
                if path.name.startswith(".") or path.name == ".venv":
                    continue
                if path.is_dir():
                    try:
                        size = sum(
                            f.stat().st_size for f in path.rglob("*") if f.is_file()
                        )
                        size_mb = size / 1024**2
                        if size_mb >= 1:
                            print(f"  {path.name:<20} {size_mb:>8.1f} MB")
                    except PermissionError:
                        pass

    print(f"{'=' * 50}\n")

    if pct >= 80:
        sys.exit(1)


if __name__ == "__main__":
    main()
