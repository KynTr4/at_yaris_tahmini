import base64
import sqlite3
import tempfile
import unittest
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import web_app
from migrate_provenance_schema import apply_migrations


class RaceDayDashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.temp.name); self.db = self.root / "race-day.db"
        self.logs = self.root / "logs"; self.logs.mkdir()
        apply_migrations(self.db)
        tracks = ("İstanbul", "İzmir", "Karma", "Belmont", "Woodbine", "Hawthorne", "Selangor")
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS horse_races(horse_key TEXT,race_id TEXT,race_date TEXT,finish TEXT)"
            )
            connection.execute(
                """INSERT INTO race_results(
                       race_id,horse_id,race_start_at,race_no,captured_at,source_endpoint,
                       source_request_id,finish_position,result_odds,result_status)
                   VALUES('race-4','tjk:41','2026-06-28T15:00:00+00:00',4,
                          '2026-06-28T17:00:00+00:00','test','result-foreign',1,2.00,'finished')"""
            )
            snapshot_ids = {}
            for race_no, track in enumerate(tracks, 1):
                race_id = f"race-{race_no}"
                for horse_no in (1, 2):
                    horse_id = f"tjk:{race_no}{horse_no}"
                    source = f"program-{race_no}-{horse_no}"
                    cursor = connection.execute(
                        """INSERT INTO program_snapshots(
                               race_id,horse_id,race_start_at,race_no,captured_at,
                               source_endpoint,source_request_id,track,horse_name)
                           VALUES(?,?,?,?,'2026-06-28T12:00:00+00:00','test',?,?,?)""",
                        (race_id, horse_id, "2026-06-28T15:00:00+00:00", race_no,
                         source, track, f"{track} Horse {horse_no}"),
                    )
                    snapshot_ids[(race_no, horse_no)] = cursor.lastrowid
            for race_no in (1, 2, 4):  # Istanbul, Izmir and unsupported Belmont have predictions.
                for horse_no, ensemble in ((1, 0.70), (2, 0.30)):
                    connection.execute(
                        """INSERT INTO prediction_snapshots(
                               prediction_id,model_version,pipeline_version,race_id,horse_id,
                               prediction_time,race_start_at,logistic_probability,
                               catboost_probability,xgboost_probability,ensemble_probability,
                               predicted_rank,feature_hash,feature_values_json,
                               feature_contract_version,feature_snapshot_id,source_request_id)
                           VALUES(?,?,?,?,?,'2026-06-28T14:00:00+00:00','2026-06-28T15:00:00+00:00',
                                  ?,?,?,?,?,?,'{}','v1',?,?)""",
                        (f"prediction-{race_no}-{horse_no}", "model-v1", "pipeline-v1",
                         f"race-{race_no}", f"tjk:{race_no}{horse_no}", ensemble, ensemble,
                         ensemble, ensemble, horse_no, f"hash-{race_no}-{horse_no}",
                         snapshot_ids[(race_no, horse_no)], f"program-{race_no}-{horse_no}"),
                    )
            connection.execute(
                """INSERT INTO race_results(
                       race_id,horse_id,race_start_at,race_no,captured_at,source_endpoint,
                       source_request_id,finish_position,result_odds,result_status)
                   VALUES('race-1','tjk:11','2026-06-28T15:00:00+00:00',1,
                          '2026-06-28T17:00:00+00:00','test','result-1',1,3.40,'finished')"""
            )
        self.db_patch = patch.object(web_app, "DB_PATH", self.db); self.db_patch.start()
        self.log_patch = patch.object(web_app, "LOG_DIR", self.logs); self.log_patch.start()
        web_app._PERFORMANCE_CACHE.clear()
        self.client = TestClient(web_app.app)
        token = base64.b64encode(f"{web_app.WEB_USERNAME}:{web_app.WEB_PASSWORD}".encode()).decode()
        self.auth = {"Authorization": f"Basic {token}"}

    def tearDown(self):
        self.log_patch.stop(); self.db_patch.stop(); web_app._PERFORMANCE_CACHE.clear(); self.temp.cleanup()

    def get(self, path):
        response = self.client.get(path, headers=self.auth)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_selected_day_returns_all_program_tracks(self):
        payload = self.get("/api/race-day/tracks?date=2026-06-28")
        self.assertEqual(payload["count"], 7)
        self.assertEqual(
            {row["track"] for row in payload["tracks"]},
            {"İstanbul", "İzmir", "Karma", "Belmont", "Woodbine", "Hawthorne", "Selangor"},
        )
        self.assertEqual(payload["country"], "ALL")

    def test_foreign_tracks_are_visible_with_unsupported_status(self):
        races = self.get("/api/race-day/races?date=2026-06-28")["races"]
        by_track = {row["track"]: row for row in races}
        self.assertEqual(by_track["Karma"]["result_status"], "Kaynak desteklenmiyor")
        self.assertEqual(by_track["Woodbine"]["result_status"], "Kaynak desteklenmiyor")
        summary = self.get("/api/race-day/summary?date=2026-06-28")
        self.assertTrue(any("track=İzmir" in warning for warning in summary["warnings"]))

    def test_prediction_waiting_and_completed_result_statuses(self):
        races = self.get("/api/race-day/races?date=2026-06-28")["races"]
        by_track = {row["track"]: row for row in races}
        self.assertTrue(by_track["İzmir"]["prediction_available"])
        self.assertEqual(by_track["İzmir"]["result_status"], "Sonuç bekleniyor")
        self.assertTrue(by_track["İstanbul"]["prediction_available"])
        self.assertEqual(by_track["İstanbul"]["result_status"], "Sonuç çekildi")
        self.assertEqual(by_track["İstanbul"]["top1_horse"], "İstanbul Horse 1")
        self.assertEqual(by_track["İstanbul"]["actual_winner"], "İstanbul Horse 1")

    def test_performance_excludes_unsupported_and_unevaluated_races(self):
        performance = self.get("/api/race-day/performance?date=2026-06-28")
        self.assertEqual(performance["evaluated_races"], 1)
        self.assertEqual(performance["correct_races"], 1)
        self.assertEqual(performance["races"][0]["track"], "İstanbul")
        self.assertAlmostEqual(performance["net_profit"], 2.4)
        global_summary = self.get("/api/performance/summary?date=2026-06-28")
        self.assertEqual(global_summary["processed_races"], 2)

    def test_live_status_verifies_db_and_country_scope(self):
        ended = datetime.now(timezone.utc) - timedelta(seconds=120)
        (self.logs / "live_results_status.json").write_text(json.dumps({
            "date":"2026-06-28","country":"TR","status":"SUCCESS","ended_at":ended.isoformat()
        }),encoding="utf-8")
        payload = self.get("/api/results-refresh/status?date=2026-06-28&country=TR")
        self.assertEqual(payload["country"], "TR")
        self.assertEqual(payload["total_tracks"], 2)
        self.assertEqual({row["track"] for row in payload["tracks"]}, {"İstanbul", "İzmir"})
        self.assertTrue(175 <= payload["seconds_remaining"] <= 181)
        all_tracks = self.get("/api/results-refresh/status?date=2026-06-28&country=ALL")
        self.assertEqual(all_tracks["total_tracks"], 7)
        self.assertEqual(all_tracks["interval_seconds"], 300)
        self.assertIn("next_run_at", all_tracks)
        self.assertIn("server_now", all_tracks)

    def test_missing_horses_api_and_csv(self):
        payload=self.get("/api/race-day/missing-horses?date=2026-06-28&track=İstanbul")
        self.assertGreater(payload["count"],0)
        self.assertIn("jockey",payload["rows"][0]["missing_fields"])
        response=self.client.get("/api/race-day/missing-horses/export.csv?date=2026-06-28",headers=self.auth)
        self.assertEqual(response.status_code,200);self.assertIn("missing_fields",response.text)

    def test_track_filter_and_query_only_are_preserved(self):
        payload = self.get("/api/race-day/races?date=2026-06-28&track=Woodbine")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["races"][0]["track"], "Woodbine")
        with web_app.readonly_connection() as connection:
            self.assertEqual(connection.execute("PRAGMA query_only").fetchone()[0], 1)
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("INSERT INTO race_results(race_id) VALUES('forbidden')")


if __name__ == "__main__":
    unittest.main()
