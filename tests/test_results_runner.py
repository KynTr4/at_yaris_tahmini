import json
import argparse
import os
import socket
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pipeline_runner
import run_results_update
from migrate_provenance_schema import apply_migrations


def step_result(script: str, exit_code: int = 0, stdout: str = "", stderr: str = ""):
    return {
        "script": script, "args": [], "started_at": "2030-01-01T10:00:00+00:00",
        "ended_at": "2030-01-01T10:00:01+00:00", "duration_seconds": 1.0,
        "exit_code": exit_code, "stdout": stdout, "stderr": stderr,
    }


class ResultsRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.temp.name)
        self.log_dir = self.root / "service-logs"; self.log_dir.mkdir()
        self.output_dir = self.root / "output"; self.output_dir.mkdir()
        self.db = self.root / "test.db"; apply_migrations(self.db)
        self.patchers = (
            patch.object(pipeline_runner, "LOG_DIR", self.log_dir),
            patch.object(pipeline_runner, "PROJECT_ROOT", self.root),
            patch.object(run_results_update, "DB_PATH", self.db),
            patch.object(run_results_update, "OUTPUT_DIR", self.output_dir),
            patch.object(run_results_update, "LOG_DIR", self.log_dir),
        )
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp.cleanup()

    def latest_payload(self):
        return json.loads((self.log_dir / "results_update_latest.json").read_text(encoding="utf-8"))

    def test_stale_lock_is_removed_and_runner_acquires_it(self):
        path = self.log_dir / "results_update.lock"
        path.write_text(json.dumps({
            "pid": 99999999, "started_at": "2020-01-01T00:00:00+00:00",
            "hostname": socket.gethostname(),
        }), encoding="utf-8")
        with pipeline_runner.runner_lock("results_update", skip_if_active=True) as lock:
            self.assertTrue(lock.acquired)
            self.assertTrue(lock.stale_lock_removed)
            self.assertEqual(pipeline_runner.read_lock_metadata(path)["pid"], os.getpid())
        self.assertFalse(path.exists())

    def test_active_pid_skips_exit_zero_and_writes_latest_json(self):
        path = self.log_dir / "results_update.lock"
        path.write_text(json.dumps({
            "pid": os.getpid(), "started_at": "2030-01-01T00:00:00+00:00",
            "hostname": socket.gethostname(), "lock_id": "active-test",
        }), encoding="utf-8")
        with patch.object(run_results_update, "run_step") as run_step:
            self.assertEqual(run_results_update.main(), 0)
            run_step.assert_not_called()
        payload = self.latest_payload()
        self.assertEqual(payload["status"], "SKIPPED_ALREADY_RUNNING")
        self.assertEqual(payload["errors"], [])

    def test_shadow_monitor_missed_races_is_warning_exit_zero(self):
        def fake_run_step(script, args, timeout):
            if script == "shadow_monitor.py":
                with sqlite3.connect(self.db) as connection:
                    connection.execute(
                        """INSERT INTO shadow_monitoring_runs(
                               run_id,run_at,shadow_date,leakage_gate_pass,feature_contract_pass,
                               snapshot_coverage_pass,prediction_drift_status,calibration_status,
                               feature_drift_status,pipeline_status,production_ready,details_json)
                           VALUES('warning-run','2030-01-01T10:00:00+00:00','2030-01-01',
                                  1,1,0,'INSUFFICIENT_DATA','INSUFFICIENT_DATA',
                                  'INSUFFICIENT_DATA','FAIL',0,?)""",
                        (json.dumps({"missed_shadow_races": 1}),),
                    )
                return step_result(script, exit_code=1, stdout="monitoring warning")
            return step_result(script)

        with patch.object(run_results_update, "run_step", side_effect=fake_run_step):
            self.assertEqual(run_results_update.main(), 0)
        payload = self.latest_payload()
        self.assertEqual(payload["status"], "WARNING")
        self.assertEqual(payload["shadow_monitor_exit_code"], 1)
        self.assertIn("snapshot_coverage_fail", payload["warnings"])
        self.assertIn("missed_shadow_races=1", payload["warnings"])
        self.assertEqual(payload["errors"], [])

    def test_update_results_exception_is_failed_exit_one_and_writes_json(self):
        with patch.object(run_results_update, "run_step", side_effect=RuntimeError("update exploded")):
            self.assertEqual(run_results_update.main(), 1)
        payload = self.latest_payload()
        self.assertEqual(payload["status"], "FAILED")
        self.assertTrue(any("update exploded" in error for error in payload["errors"]))
        self.assertTrue(payload["ended_at"])

    def test_success_payload_contains_counts_and_required_format(self):
        now = datetime.now(timezone.utc)

        def fake_run_step(script, args, timeout):
            with sqlite3.connect(self.db) as connection:
                if script == "update_results.py":
                    connection.execute(
                        """INSERT INTO race_results(
                               race_id,horse_id,race_start_at,race_no,captured_at,
                               source_endpoint,source_request_id,finish_position,result_odds,result_status)
                           VALUES('today-race','horse-1',?,1,?,'test','result-1',1,3.0,'finished')""",
                        (now.isoformat(), (now + timedelta(hours=1)).isoformat()),
                    )
                    (self.output_dir / "results_coverage_run.json").write_text(
                        json.dumps({"dates": []}), encoding="utf-8"
                    )
                elif script == "shadow_monitor.py":
                    connection.execute(
                        """INSERT INTO shadow_monitoring_runs(
                               run_id,run_at,shadow_date,leakage_gate_pass,feature_contract_pass,
                               snapshot_coverage_pass,prediction_drift_status,calibration_status,
                               feature_drift_status,pipeline_status,production_ready,details_json)
                           VALUES('success-run',?,?,1,1,1,'OK','OK','OK','PASS',0,?)""",
                        (now.isoformat(), now.date().isoformat(), json.dumps({"missed_shadow_races": 0})),
                    )
            return step_result(script)

        with patch.object(run_results_update, "run_step", side_effect=fake_run_step):
            self.assertEqual(run_results_update.main(), 0)
        payload = self.latest_payload()
        self.assertEqual(payload["status"], "SUCCESS")
        self.assertEqual(payload["inserted_results_count"], 1)
        self.assertEqual(payload["distinct_result_races_today"], 1)
        self.assertEqual(payload["matched_predictions_count"], 0)
        self.assertEqual(payload["warnings"], [])
        self.assertEqual(payload["errors"], [])
        required = {
            "runner", "status", "started_at", "ended_at", "duration_seconds",
            "update_results_exit_code", "shadow_monitor_exit_code",
            "inserted_results_count", "distinct_result_races_today",
            "matched_predictions_count", "warnings", "errors",
        }
        self.assertEqual(set(payload), required)

    def test_shadow_traceback_is_technical_failure_even_if_monitor_row_exists(self):
        def fake_run_step(script, args, timeout):
            if script == "shadow_monitor.py":
                with sqlite3.connect(self.db) as connection:
                    connection.execute(
                        """INSERT INTO shadow_monitoring_runs(
                               run_id,run_at,shadow_date,leakage_gate_pass,feature_contract_pass,
                               snapshot_coverage_pass,prediction_drift_status,calibration_status,
                               feature_drift_status,pipeline_status,production_ready,details_json)
                           VALUES('partial-run','2030-01-01T10:00:00+00:00','2030-01-01',
                                  1,1,1,'OK','OK','OK','PASS',0,'{}')"""
                    )
                return step_result(script, exit_code=1, stderr="Traceback: report write exploded")
            return step_result(script)

        with patch.object(run_results_update, "run_step", side_effect=fake_run_step):
            self.assertEqual(run_results_update.main(), 1)
        payload = self.latest_payload()
        self.assertEqual(payload["status"], "FAILED")
        self.assertTrue(any("technical failure" in error for error in payload["errors"]))

    def test_at_yaris_systemd_contract_and_overlap_success(self):
        service = (
            Path(__file__).resolve().parents[1]
            / "deploy" / "systemd" / "at-yaris-results-update.service"
        ).read_text(encoding="utf-8")
        self.assertIn("User=at_yaris", service)
        self.assertIn("StandardOutput=append:/var/log/at_yaris_tahmini/results.log", service)
        self.assertIn("StandardError=append:/var/log/at_yaris_tahmini/results.err.log", service)
        self.assertIn("TimeoutStartSec=3900", service)
        self.assertIn("KillMode=control-group", service)
        self.assertNotIn("SuccessExitStatus", service)

    def test_track_coverage_warnings_are_added_to_latest_payload_contract(self):
        coverage = {
            "date": "2026-06-28",
            "tracks": [{
                "track": "İzmir", "track_policy": "mandatory", "program_races": 8,
                "result_races": 0, "missing_races": 8, "missing_reason": "source_not_published",
                "tjk_id_missing_horse_count": 3, "source_not_published_count": 51,
            }],
            "races": [],
        }
        (self.output_dir / "results_coverage_run.json").write_text(
            json.dumps({"dates": [coverage]}, ensure_ascii=False), encoding="utf-8"
        )
        warnings = run_results_update.result_coverage_warnings()
        self.assertEqual(len(warnings), 1)
        self.assertIn("date=2026-06-28 mandatory_track_missing: track=İzmir", warnings[0])

    def test_live_mode_passes_tr_scope_skips_monitor_and_writes_status(self):
        with sqlite3.connect(self.db) as connection:
            connection.execute("CREATE TABLE horse_races(horse_key TEXT,race_id TEXT,race_date TEXT,finish TEXT)")
            connection.execute(
                """INSERT INTO program_snapshots(
                       race_id,horse_id,race_start_at,race_no,captured_at,
                       source_endpoint,source_request_id,track)
                   VALUES('tr-race','tjk:1','2030-01-01T12:00:00+00:00',1,
                          '2030-01-01T10:00:00+00:00','test','program-tr','İstanbul')"""
            )
        calls = []
        def fake_run_step(script, args, timeout):
            calls.append((script, args))
            (self.output_dir / "results_coverage_run.json").write_text(
                json.dumps({"dates": []}), encoding="utf-8"
            )
            return step_result(script)
        options = argparse.Namespace(
            date="2030-01-01", today_tracks=True, country="TR", track=[],
            skip_monitor=True, live_status=True,
        )
        with patch.object(run_results_update, "run_step", side_effect=fake_run_step):
            self.assertEqual(run_results_update.main(options), 0)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][0], "update_results.py")
        self.assertIn("--country", calls[0][1]); self.assertIn("TR", calls[0][1])
        self.assertIn("--today-tracks", calls[0][1])
        self.assertEqual(calls[1], ("import_race_results_csv.py", ["--date", "2030-01-01"]))
        payload = json.loads((self.log_dir / "live_results_status.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["country"], "TR")
        self.assertEqual(payload["total_tracks"], 1)


if __name__ == "__main__":
    unittest.main()
