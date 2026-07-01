import sqlite3
import tempfile
import unittest
from pathlib import Path

from migrate_provenance_schema import apply_migrations
from results_coverage import build_results_coverage, coverage_warnings, write_results_coverage
from update_results import isolated_result_exists


class ResultsCoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.temp.name); self.db = self.root / "test.db"
        apply_migrations(self.db)
        self.output = self.root / "output"; self.reports = self.root / "reports"
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS horse_races(
                       horse_key TEXT,race_id TEXT,race_date TEXT,finish TEXT)"""
            )
            def program(race, horse, track, race_no, source):
                connection.execute(
                    """INSERT INTO program_snapshots(
                           race_id,horse_id,race_start_at,race_no,captured_at,
                           source_endpoint,source_request_id,track,horse_name)
                       VALUES(?,?,?,?,'2026-06-28T10:00:00+00:00','test',?,?,?)""",
                    (race, horse, "2026-06-28T15:30:00+00:00", race_no, source, track, horse),
                )

            program("ist-1", "tjk:1", "İstanbul (1. Y.G.)", 1, "p1")
            program("ist-1", "tjk:2", "İstanbul (1. Y.G.)", 1, "p2")
            program("izm-1", "tjk:3", "İzmir", 2, "p3")
            program("izm-1", "name:no-tjk", "İzmir", 2, "p4")
            program("izm-2", "tjk:5", "İzmir", 3, "p5")
            program("karma-1", "name:foreign", "Karma", 1, "p6")
            connection.execute(
                """INSERT INTO race_results(
                       race_id,horse_id,race_start_at,race_no,captured_at,source_endpoint,
                       source_request_id,finish_position,result_status)
                   VALUES('ist-1','tjk:1','2026-06-28T15:30:00+00:00',1,
                          '2026-06-28T17:00:00+00:00','test','r1',1,'finished')"""
            )
            # Legacy result exists but immutable race_results row does not: mapping pending.
            connection.execute(
                """INSERT INTO horse_races(horse_key,race_id,race_date,finish)
                   VALUES('tjk:5','legacy-izm-2','28.06.2026','1')"""
            )

    def tearDown(self):
        self.temp.cleanup()

    def test_track_coverage_and_missing_reasons(self):
        with sqlite3.connect(self.db) as connection:
            connection.row_factory = sqlite3.Row
            coverage = build_results_coverage(connection, "2026-06-28")
        tracks = {row["track"]: row for row in coverage["tracks"]}
        self.assertEqual(tracks["İstanbul"]["program_races"], 1)
        self.assertEqual(tracks["İstanbul"]["result_races"], 1)
        self.assertEqual(tracks["İstanbul"]["missing_races"], 0)
        self.assertEqual(tracks["İzmir"]["program_races"], 2)
        self.assertEqual(tracks["İzmir"]["result_races"], 0)
        self.assertEqual(tracks["İzmir"]["missing_races"], 2)
        self.assertEqual(tracks["İzmir"]["tjk_id_missing_horse_count"], 1)
        self.assertEqual(tracks["İzmir"]["source_not_published_count"], 1)
        self.assertIn("DATA_MISSING", tracks["İzmir"]["missing_reason"])
        self.assertEqual(tracks["Karma"]["missing_reason"], "SOURCE_UNSUPPORTED")

    def test_race_dashboard_statuses_are_distinct(self):
        with sqlite3.connect(self.db) as connection:
            connection.row_factory = sqlite3.Row
            coverage = build_results_coverage(connection, "2026-06-28")
        races = {row["race_id"]: row for row in coverage["races"]}
        self.assertEqual(races["ist-1"]["status"], "Sonuç çekildi")
        self.assertEqual(races["izm-1"]["status"], "TJK ID eksik")
        self.assertEqual(races["izm-2"]["status"], "Veri eksik")
        self.assertEqual(races["karma-1"]["status"], "Kaynak desteklenmiyor")

    def test_track_warnings_and_report_fields(self):
        coverage = write_results_coverage(self.db, "2026-06-28", self.output, self.reports)
        warnings = coverage_warnings(coverage)
        self.assertTrue(any("mandatory_track_missing: track=İzmir" in item for item in warnings))
        self.assertTrue(any("unsupported_track_pending: track=Karma" in item for item in warnings))
        report = (self.reports / "results_coverage_latest.md").read_text(encoding="utf-8")
        for field in (
            "Program races", "Result races", "Missing races", "Missing reason",
            "Missing TJK horses", "Source not published",
        ):
            self.assertIn(field, report)

    def test_legacy_result_does_not_suppress_missing_isolated_result(self):
        with sqlite3.connect(self.db) as connection:
            self.assertFalse(isolated_result_exists(connection, "tjk:5", "2026-06-28"))
            connection.execute(
                """INSERT INTO race_results(
                       race_id,horse_id,race_start_at,race_no,captured_at,source_endpoint,
                       source_request_id,finish_position,result_status)
                   VALUES('izm-2','tjk:5','2026-06-28T15:30:00+00:00',3,
                          '2026-06-28T17:00:00+00:00','test','r5',1,'finished')"""
            )
            self.assertTrue(isolated_result_exists(connection, "tjk:5", "2026-06-28"))


if __name__ == "__main__":
    unittest.main()
