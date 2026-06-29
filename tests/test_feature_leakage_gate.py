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


if __name__ == "__main__":
    unittest.main()
