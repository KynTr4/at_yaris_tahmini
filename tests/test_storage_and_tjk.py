"""Storage + TJK refactoring entegrasyon testleri.

Çalıştırma:
    pytest tests/test_storage_and_tjk.py -v
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import types
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── stdlib mock app_config ────────────────────────────────────────────────────
def _mock_app_config(tmp_db: Path, tmp_dir: Path) -> None:
    mock = types.ModuleType("app_config")
    mock.DB_PATH = tmp_db
    mock.LOG_DIR = tmp_dir / "logs"
    mock.BACKUP_DIR = tmp_dir / "backups"
    mock.OUTPUT_DIR = tmp_dir / "output"
    mock.REPORTS_DIR = tmp_dir / "reports"
    mock.PROJECT_ROOT = tmp_dir
    mock.MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
    mock.TZ_NAME = "Europe/Istanbul"
    mock.ensure_runtime_dirs = lambda: None
    for d in (mock.LOG_DIR, mock.BACKUP_DIR, mock.OUTPUT_DIR, mock.REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)
    sys.modules["app_config"] = mock


# ── fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture()
def tmp_env(tmp_path):
    db = tmp_path / "test.db"
    _mock_app_config(db, tmp_path)
    yield {"db": db, "root": tmp_path}
    # Cleanup: reset module so next test gets a fresh mock
    sys.modules.pop("app_config", None)
    sys.modules.pop("tjk_scraper", None)
    sys.modules.pop("storage_manager", None)
    sys.modules.pop("migrate_provenance_schema", None)


# ── helpers ───────────────────────────────────────────────────────────────────
def _apply_migrations(db_path):
    from migrate_provenance_schema import apply_migrations

    return apply_migrations(str(db_path))


def _get_scraper():
    import importlib

    return importlib.import_module("tjk_scraper")


# =============================================================================
# 1. Horse name normalization
# =============================================================================
class TestNormalizeHorseName:
    def test_strips_start_no(self):
        mod = _get_scraper()
        assert mod.normalize_horse_name("YAĞIZATEŞ(8)") == "YAĞIZATEŞ"

    def test_uppercase(self):
        mod = _get_scraper()
        assert mod.normalize_horse_name("yağızateş(8)") == "YAĞIZATEŞ"

    def test_no_parens(self):
        mod = _get_scraper()
        assert mod.normalize_horse_name("SECRET OF DRAGON") == "SECRET OF DRAGON"

    def test_collapses_spaces(self):
        mod = _get_scraper()
        assert mod.normalize_horse_name("  KRAL   OSIMHEN(13)  ") == "KRAL OSIMHEN"

    def test_turkish_chars_preserved(self):
        mod = _get_scraper()
        assert "İ" in mod.normalize_horse_name("İNZİBAT(6)")


# =============================================================================
# 2. SQLite migration — tabloların oluşturulması
# =============================================================================
class TestMigrations:
    def test_018_tables_created(self, tmp_env):
        _apply_migrations(tmp_env["db"])
        conn = sqlite3.connect(str(tmp_env["db"]))
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        assert "tjk_race_results" in tables
        assert "tjk_prediction_comparisons" in tables
        assert "tjk_race_summary" in tables

    def test_019_table_created(self, tmp_env):
        _apply_migrations(tmp_env["db"])
        conn = sqlite3.connect(str(tmp_env["db"]))
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        assert "model_prediction_runs" in tables

    def test_idempotent(self, tmp_env):
        """İki kez çalıştırmak hata vermemeli."""
        _apply_migrations(tmp_env["db"])
        _apply_migrations(tmp_env["db"])  # second call — must be no-op


# =============================================================================
# 3. TJK sonuç kaydetme — duplicate insert testi
# =============================================================================
class TestPersistResults:
    def _sample_city_data(self):
        return {
            "city": "İstanbul",
            "date": "2026-07-04",
            "races": [
                {
                    "race_no": 1,
                    "race_time": "17.15",
                    "horses": [
                        {
                            "horse_name": "YAĞIZATEŞ",
                            "horse_no": 8,
                            "finish_pos": 1,
                            "finish_time": "1.34.04",
                            "odds": "10.50",
                            "agf": "%8(3)",
                        },
                        {
                            "horse_name": "SAKIZ ADASI",
                            "horse_no": 4,
                            "finish_pos": 2,
                            "finish_time": "1.34.19",
                            "odds": "7.95",
                            "agf": "%7(4)",
                        },
                    ],
                }
            ],
            "error": None,
        }

    def test_first_insert_returns_count(self, tmp_env):
        _apply_migrations(tmp_env["db"])
        mod = _get_scraper()
        rows = mod.persist_results(str(tmp_env["db"]), self._sample_city_data())
        assert rows >= 1

    def test_duplicate_insert_does_not_duplicate_row(self, tmp_env):
        _apply_migrations(tmp_env["db"])
        mod = _get_scraper()
        mod.persist_results(str(tmp_env["db"]), self._sample_city_data())
        mod.persist_results(str(tmp_env["db"]), self._sample_city_data())
        conn = sqlite3.connect(str(tmp_env["db"]))
        count = conn.execute("SELECT COUNT(*) FROM tjk_race_results").fetchone()[0]
        conn.close()
        assert count == 2

    def test_partial_result_is_updated_by_later_scrape(self, tmp_env):
        _apply_migrations(tmp_env["db"])
        mod = _get_scraper()
        partial = self._sample_city_data()
        partial["races"][0]["horses"][0]["finish_pos"] = None
        partial["races"][0]["horses"][0]["finish_time"] = ""
        mod.persist_results(str(tmp_env["db"]), partial)

        complete = self._sample_city_data()
        mod.persist_results(str(tmp_env["db"]), complete)
        conn = sqlite3.connect(str(tmp_env["db"]))
        row = conn.execute(
            "SELECT actual_rank, finish_time FROM tjk_race_results WHERE horse_name=?",
            ("YAĞIZATEŞ",),
        ).fetchone()
        conn.close()
        assert row == (1, "1.34.04")

    def test_data_in_db_after_insert(self, tmp_env):
        _apply_migrations(tmp_env["db"])
        mod = _get_scraper()
        mod.persist_results(str(tmp_env["db"]), self._sample_city_data())
        conn = sqlite3.connect(str(tmp_env["db"]))
        rows = conn.execute(
            "SELECT horse_name, actual_rank FROM tjk_race_results WHERE race_date='2026-07-04'"
        ).fetchall()
        conn.close()
        names = [r[0] for r in rows]
        assert "YAĞIZATEŞ" in names
        ranks = {r[0]: r[1] for r in rows}
        assert ranks["YAĞIZATEŞ"] == 1


# =============================================================================
# 4. Storage manager — dry-run default, --delete required for real deletion
# =============================================================================
class TestStorageManager:
    def test_import_ok(self, tmp_env):
        import importlib

        sm = importlib.import_module("storage_manager")
        assert hasattr(sm, "run_all")
        assert hasattr(sm, "enforce_retention")
        assert hasattr(sm, "vacuum_sqlite")

    def test_get_disk_usage(self, tmp_env):
        import importlib

        sm = importlib.import_module("storage_manager")
        result = sm.get_disk_usage(tmp_env["root"])
        assert "total_gb" in result
        assert "used_percent" in result
        assert 0 <= result["used_percent"] <= 100

    def test_enforce_retention_dry_run_deletes_nothing(self, tmp_env):
        import importlib

        sm = importlib.import_module("storage_manager")
        # Create a fake old CSV
        csv_path = tmp_env["root"] / "output" / "test_old.csv"
        csv_path.write_text("a,b\n1,2\n")
        result = sm.enforce_retention(
            tmp_env["root"], sm.RETENTION_POLICIES, dry_run=True
        )
        # File must still exist (dry_run=True)
        assert csv_path.exists()

    def test_enforce_retention_delete_removes_csv(self, tmp_env):
        import importlib

        sm = importlib.import_module("storage_manager")
        # Create an unprotected CSV in output/
        csv_path = tmp_env["root"] / "output" / "unprotected_test.csv"
        csv_path.write_text("a,b\n1,2\n")
        result = sm.enforce_retention(
            tmp_env["root"], sm.RETENTION_POLICIES, dry_run=False
        )
        # File should be deleted (max_age_days=0 for output/*.csv)
        assert not csv_path.exists()

    def test_delete_mode_flag(self, tmp_env):
        """--delete flag olmadan run_all dry_run=True kullanmalı."""
        import importlib

        sm = importlib.import_module("storage_manager")
        # Create a file that should be deleted
        csv_path = tmp_env["root"] / "output" / "should_not_delete.csv"
        csv_path.write_text("x\n")
        report = sm.run_all(dry_run=True, skip_vacuum=True)  # no delete
        assert report["dry_run"] is True
        # File must still exist
        assert csv_path.exists()


# =============================================================================
# 5. predict_today.py — SQLite yazma testi (mock modeller)
# =============================================================================
class TestPredictTodaySQLite:
    def test_model_prediction_runs_table_writable(self, tmp_env):
        """model_prediction_runs tablosuna yazma testi."""
        _apply_migrations(tmp_env["db"])
        conn = sqlite3.connect(str(tmp_env["db"]))
        conn.execute(
            """INSERT OR REPLACE INTO model_prediction_runs
               (prediction_date, race_id, horse_id, horse_name, track, race_no,
                race_start_at, lr_prob, xgb_prob, cb_prob, ensemble_prob, predicted_rank)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "2026-07-04",
                "race:1",
                "horse:101",
                "YAĞIZATEŞ",
                "İstanbul",
                1,
                "2026-07-04T14:15:00+03:00",
                0.10,
                0.12,
                0.13,
                0.117,
                1,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT horse_name, predicted_rank FROM model_prediction_runs WHERE race_id='race:1'"
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "YAĞIZATEŞ"
        assert row[1] == 1


# =============================================================================
# 6. Dashboard API — /api/storage-status temel doğrulama
# =============================================================================
class TestStorageStatusAPI:
    def test_endpoint_returns_storage_payload(self, tmp_path, monkeypatch):
        from fastapi.testclient import TestClient

        import web_app

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        monkeypatch.setattr(web_app, "PROJECT_ROOT", tmp_path)
        monkeypatch.setattr(web_app, "REPORTS_DIR", reports_dir)

        client = TestClient(web_app.app)
        response = client.get(
            "/api/storage-status",
            auth=(web_app.WEB_USERNAME, web_app.WEB_PASSWORD),
        )

        assert response.status_code == 200
        payload = response.json()
        assert {"disk", "dirs", "last_run_at", "freed_mb"} <= payload.keys()

    def test_get_disk_usage_keys(self, tmp_env):
        import importlib

        sm = importlib.import_module("storage_manager")
        disk = sm.get_disk_usage(tmp_env["root"])
        for key in ("total_gb", "used_gb", "free_gb", "used_percent"):
            assert key in disk, f"Missing key: {key}"

    def test_get_dir_sizes_returns_dict(self, tmp_env):
        import importlib

        sm = importlib.import_module("storage_manager")
        sizes = sm.get_dir_sizes(tmp_env["root"])
        assert isinstance(sizes, dict)


# =============================================================================
# 7. TJK HTML parse testi (gerçek istek yok — sabit HTML'den)
# =============================================================================
SAMPLE_HTML = """
<div class="races-panes races-panes3">
  <div id="225946" sehir="İstanbul" style="display:block">
    <div class="race-details">
      <h3 class="race-no"><a>1. Koşu 17.15</a></h3>
    </div>
    <div id="kosubilgisi-225946">
      <table class="tablesorter"><tbody>
        <tr class="odd">
          <td class="gunluk-GunlukYarisSonuclari-SONUCNO">1</td>
          <td class="gunluk-GunlukYarisSonuclari-AtAdi3">
            <a href="#">YAĞIZATEŞ(8)<span></span></a>
          </td>
          <td class="gunluk-GunlukYarisSonuclari-Derece">1.34.04</td>
          <td class="gunluk-GunlukYarisSonuclari-Gny"><span>10,50</span></td>
          <td class="gunluk-GunlukYarisSonuclari-AGFORAN"><a>%8(3)</a></td>
        </tr>
        <tr class="even">
          <td class="gunluk-GunlukYarisSonuclari-SONUCNO">2</td>
          <td class="gunluk-GunlukYarisSonuclari-AtAdi3">
            <a href="#">SAKIZ ADASI(4)<span></span></a>
          </td>
          <td class="gunluk-GunlukYarisSonuclari-Derece">1.34.19</td>
          <td class="gunluk-GunlukYarisSonuclari-Gny"><span>7,95</span></td>
          <td class="gunluk-GunlukYarisSonuclari-AGFORAN"><a>%7(4)</a></td>
        </tr>
      </tbody></table>
    </div>
  </div>
</div>
"""


class TestTJKHTMLParse:
    def test_parse_races_extracts_horses(self):
        from bs4 import BeautifulSoup

        mod = _get_scraper()
        soup = BeautifulSoup(SAMPLE_HTML, "html.parser")
        races = mod._parse_races(soup, "İstanbul")
        assert len(races) == 1
        race = races[0]
        assert race["race_no"] == 1
        assert race["race_time"] == "17.15"
        assert len(race["horses"]) == 2

    def test_parse_winner_normalized_name(self):
        from bs4 import BeautifulSoup

        mod = _get_scraper()
        soup = BeautifulSoup(SAMPLE_HTML, "html.parser")
        races = mod._parse_races(soup, "İstanbul")
        winner = next(h for h in races[0]["horses"] if h["finish_pos"] == 1)
        assert winner["horse_name"] == "YAĞIZATEŞ"
        assert winner["start_no"] == 8
        assert winner["finish_time"] == "1.34.04"

    def test_parse_second_place(self):
        from bs4 import BeautifulSoup

        mod = _get_scraper()
        soup = BeautifulSoup(SAMPLE_HTML, "html.parser")
        races = mod._parse_races(soup, "İstanbul")
        second = next(h for h in races[0]["horses"] if h["finish_pos"] == 2)
        assert second["horse_name"] == "SAKIZ ADASI"
