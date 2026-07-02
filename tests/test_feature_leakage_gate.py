import sqlite3
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from build_asof_features import history_features, latest_program_asof
from feature_contract import MODEL_FEATURES, validate_model_feature_contract
from migrate_provenance_schema import apply_migrations
from validate_feature_provenance import synthetic_invariance_checks


class FeatureLeakageGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "audit.db"
        apply_migrations(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def _insert_program(self, captured="2026-01-01T09:00:00+00:00", start="2026-01-01T10:00:00+00:00", request="r1"):
        with sqlite3.connect(self.db) as db:
            db.execute(
                """INSERT INTO program_snapshots(
                       race_id,horse_id,race_start_at,race_no,captured_at,source_endpoint,
                       source_request_id,draw,carried_weight,race_class,track,surface,distance)
                   VALUES('race1','horse:1',?,1,?,'test',?,1,55,'A','T','K:',1400)""",
                (start, captured, request),
            )

    def test_captured_at_before_race_start(self):
        self._insert_program()
        self._insert_program("2026-01-01T11:00:00+00:00", request="late")
        with sqlite3.connect(self.db) as db:
            frame = latest_program_asof(db)
        self.assertEqual(len(frame), 1)
        self.assertEqual(frame.iloc[0]["source_request_id"], "r1")

    def test_duplicate_snapshot_rejected(self):
        self._insert_program()
        with self.assertRaises(sqlite3.IntegrityError):
            self._insert_program()

    def test_append_only_update_and_delete_rejected(self):
        self._insert_program()
        for sql in ("UPDATE program_snapshots SET draw=2", "DELETE FROM program_snapshots"):
            with self.assertRaises(sqlite3.IntegrityError):
                with sqlite3.connect(self.db) as db:
                    db.execute(sql)

    def test_feature_prefix_invariance(self):
        checks = synthetic_invariance_checks()
        self.assertTrue(checks["feature_prefix_invariance"])

    def test_target_mutation_invariance(self):
        checks = synthetic_invariance_checks()
        self.assertTrue(checks["target_mutation_invariance"])

    def test_future_row_invariance(self):
        checks = synthetic_invariance_checks()
        self.assertTrue(checks["future_row_invariance"])

    def test_same_day_ordering(self):
        checks = synthetic_invariance_checks()
        self.assertTrue(checks["same_day_race_start_ordering"])

    def test_outcome_feature_detection(self):
        with self.assertRaises(ValueError):
            validate_model_feature_contract(MODEL_FEATURES + ["finish_position"])

    def test_horse_races_fallback_and_leakage_safety(self):
        self._insert_program()
        # Create a temporary table structure for horse_races in the test DB
        with sqlite3.connect(self.db) as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS horse_races (
                       horse_key TEXT,
                       race_id TEXT,
                       race_date TEXT,
                       hippodrome TEXT,
                       distance INTEGER,
                       surface TEXT,
                       race_class TEXT,
                       finish TEXT,
                       weight TEXT,
                       jockey TEXT,
                       trainer TEXT
                   )"""
            )
            # Insert a fallback record for horse:1 which runs BEFORE the target race (target is 2026-01-01)
            db.execute(
                """INSERT INTO horse_races (
                       horse_key, race_id, race_date, hippodrome, distance, surface,
                       race_class, finish, weight, jockey, trainer
                   )
                   VALUES ('horse:1', 'past_hr_1', '15.12.2025', 'T', 1400, 'K:', 'B', '2', '54', 'J', 'T')"""
            )
            # Insert a record dated AFTER target (2026-01-01) to verify it is NOT used (prevent future leakage)
            db.execute(
                """INSERT INTO horse_races (
                       horse_key, race_id, race_date, hippodrome, distance, surface,
                       race_class, finish, weight, jockey, trainer
                   )
                   VALUES ('horse:1', 'leak_future', '10.01.2026', 'T', 1400, 'K:', 'B', '1', '54', 'J', 'T')"""
            )
        
        # Now run build_frame using self.db (which has results table empty!)
        from build_asof_features import build_frame
        frame = build_frame(self.db)
        
        # Verify that the frame is built and class_change, distance_change, surface_change are populated!
        self.assertFalse(frame.empty)

        row = frame.iloc[0]
        # class_change: target race_class is 'A', last was 'B' -> should be 1
        self.assertEqual(row["class_change"], 1)
        # distance_change: target distance is 1400, last was 1400 -> should be 0
        self.assertEqual(row["distance_change"], 0)
        # surface_change: target surface is 'K:', last was 'K:' -> should be 0
        self.assertEqual(row["surface_change"], 0)
        # days_since_last_race: target is 2026-01-01 10:00, last is 2025-12-15 (17 days 10 hours difference = 17.416)
        self.assertAlmostEqual(row["days_since_last_race"], 17.4, places=1)

        # win rates: surface win rate should be 0.0 (past finish was 2, which is not 1)
        self.assertEqual(row["surface_win_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()

