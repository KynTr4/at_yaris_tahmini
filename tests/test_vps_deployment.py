import sqlite3
import tarfile
import tempfile
import unittest
from pathlib import Path

import pandas as pd

import backup_daily
import create_vps_bundle
from migrate_provenance_schema import apply_migrations
from run_agf_update import select_upcoming
from run_daily_pipeline import STEPS


class VpsDeploymentTests(unittest.TestCase):
    def test_daily_step_order_and_fail_closed_tail(self):
        scripts = [step[0] for step in STEPS]
        self.assertEqual(scripts[-3:], [
            "build_asof_features.py", "validate_feature_provenance.py", "shadow_monitor.py",
        ])

    def test_agf_ten_minute_priority_and_started_race_exclusion(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / "test.db"; apply_migrations(db)
            now = pd.Timestamp("2030-01-01T10:00:00Z")
            with sqlite3.connect(db) as con:
                for index, minutes in enumerate((-1, 5, 30), 1):
                    start = now + pd.Timedelta(minutes=minutes)
                    con.execute(
                        """INSERT INTO program_snapshots(
                               race_id,horse_id,race_start_at,race_no,captured_at,
                               source_endpoint,source_request_id)
                           VALUES(?,?,?,?,?,?,?)""",
                        (f"prog_2030-01-01_3_{index}", f"h{index}", start.isoformat(), index,
                         (now - pd.Timedelta(hours=1)).isoformat(), "test", f"s{index}"),
                    )
            selected, mode = select_upcoming(now, db)
            self.assertEqual(mode, "urgent_10m_60s")
            self.assertEqual(selected.race_no.tolist(), [2])

    def test_agf_tiered_cadence_uses_latest_snapshot_age(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / "test.db"; apply_migrations(db)
            now = pd.Timestamp("2030-01-01T10:00:00Z")
            cases = (
                (1, 120, 14),  # >60m: wait until 15 minutes
                (2, 45, 5),    # 60–30m: due every 5 minutes
                (3, 20, 1),    # 30–10m: wait until 2 minutes
            )
            with sqlite3.connect(db) as con:
                for race_no, minutes_to_start, snapshot_age in cases:
                    race_id = f"prog_2030-01-01_3_{race_no}"
                    start = now + pd.Timedelta(minutes=minutes_to_start)
                    con.execute(
                        """INSERT INTO program_snapshots(
                               race_id,horse_id,race_start_at,race_no,captured_at,
                               source_endpoint,source_request_id)
                           VALUES(?,?,?,?,?,?,?)""",
                        (race_id, f"h{race_no}", start.isoformat(), race_no,
                         (now - pd.Timedelta(hours=1)).isoformat(), "test", f"p{race_no}"),
                    )
                    con.execute(
                        """INSERT INTO agf_snapshots(
                               race_id,horse_id,captured_at,agf_percent,agf_rank,source_request_id)
                           VALUES(?,?,?,?,?,?)""",
                        (race_id, f"h{race_no}",
                         (now - pd.Timedelta(minutes=snapshot_age)).isoformat(),
                         10.0, race_no, f"a{race_no}"),
                    )
            selected, mode = select_upcoming(now, db)
            self.assertEqual(mode, "tiered_due")
            self.assertEqual(selected.race_no.tolist(), [2])

    def test_agf_final_window_selects_only_nearest_race(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / "test.db"; apply_migrations(db)
            now = pd.Timestamp("2030-01-01T10:00:00Z")
            with sqlite3.connect(db) as con:
                for race_no, minutes in ((1, 4), (2, 8)):
                    con.execute(
                        """INSERT INTO program_snapshots(
                               race_id,horse_id,race_start_at,race_no,captured_at,
                               source_endpoint,source_request_id)
                           VALUES(?,?,?,?,?,?,?)""",
                        (f"prog_2030-01-01_3_{race_no}", f"h{race_no}",
                         (now + pd.Timedelta(minutes=minutes)).isoformat(), race_no,
                         (now - pd.Timedelta(hours=1)).isoformat(), "test", f"p{race_no}"),
                    )
            selected, mode = select_upcoming(now, db)
            self.assertEqual(mode, "urgent_10m_60s")
            self.assertEqual(selected.race_no.tolist(), [1])

    def test_systemd_templates_exist(self):
        root = Path(__file__).resolve().parents[1] / "deploy" / "systemd"
        self.assertEqual(len(list(root.glob("*.service"))), 7)
        self.assertEqual(len(list(root.glob("*.timer"))), 6)
        agf_timer = (root / "at-yaris-agf-update.timer").read_text(encoding="utf-8")
        self.assertIn("OnCalendar=*-*-* 09..23:*:00 Europe/Istanbul", agf_timer)
        self.assertTrue((root / "at-yaris-web.service").is_file())
        self.assertIn("00/5:00", (root / "at-yaris-live-results.timer").read_text(encoding="utf-8"))
        self.assertIn("--country ALL", (root / "at-yaris-live-results.service").read_text(encoding="utf-8"))
        self.assertTrue((root / "at-yaris-race-freeze.timer").is_file())
        self.assertTrue((root.parent / "nginx" / "at-yaris-dashboard.conf").is_file())

    def test_bundle_manifest_includes_required_runtime_directories(self):
        self.assertEqual(
            set(create_vps_bundle.RUNTIME_DIRS),
            {"models", "output", "reports"},
        )
        self.assertTrue({"migrations", "tests", "docs", "web"}.issubset(create_vps_bundle.CODE_DIRS))

    def test_bundle_checksum_sidecar(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            archive = Path(tmp) / "bundle.tar.gz"
            archive.write_bytes(b"bundle")
            sidecar = create_vps_bundle.write_checksum(archive)
            self.assertTrue(sidecar.read_text(encoding="ascii").endswith("  bundle.tar.gz\n"))

    def test_sqlite_backup_archive(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            root = Path(tmp); db = root / "db.sqlite"; out = root / "output"; reports = root / "reports"; models = root / "models"; backups = root / "backups"
            with sqlite3.connect(db) as con: con.execute("CREATE TABLE t(x)"); con.execute("INSERT INTO t VALUES(1)")
            for folder in (out, reports, models): folder.mkdir(); (folder / "x.txt").write_text("x")
            old = (backup_daily.DB_PATH, backup_daily.OUTPUT_DIR, backup_daily.REPORTS_DIR, backup_daily.MODELS_DIR, backup_daily.BACKUP_DIR, backup_daily.PROJECT_ROOT)
            backup_daily.DB_PATH, backup_daily.OUTPUT_DIR, backup_daily.REPORTS_DIR, backup_daily.MODELS_DIR, backup_daily.BACKUP_DIR, backup_daily.PROJECT_ROOT = db, out, reports, models, backups, root
            try:
                archive = backup_daily.create_backup()
                self.assertTrue(archive.exists())
                with tarfile.open(archive) as tar: self.assertTrue(any(name.endswith("db.sqlite") for name in tar.getnames()))
            finally:
                (backup_daily.DB_PATH, backup_daily.OUTPUT_DIR, backup_daily.REPORTS_DIR, backup_daily.MODELS_DIR, backup_daily.BACKUP_DIR, backup_daily.PROJECT_ROOT) = old


if __name__ == "__main__": unittest.main()
