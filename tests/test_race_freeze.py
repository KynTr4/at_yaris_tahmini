import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from migrate_provenance_schema import apply_migrations
from run_race_freeze import classify_race, process


class RaceFreezeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(ignore_cleanup_errors=True);self.db=Path(self.tmp.name)/"freeze.db";apply_migrations(self.db)
        with sqlite3.connect(self.db) as c:
            self.snapshot=c.execute("""INSERT INTO program_snapshots(
                race_id,horse_id,race_start_at,race_no,captured_at,source_endpoint,
                source_request_id,track,horse_name)
                VALUES('race-1430','h1','2030-01-01T14:30:00+00:00',1,
                       '2030-01-01T12:00:00+00:00','test','program-1','İstanbul','AT 1')""").lastrowid
    def tearDown(self): self.tmp.cleanup()

    def test_window_classification(self):
        start=datetime(2030,1,1,14,30,tzinfo=timezone.utc)
        self.assertEqual(classify_race(datetime(2030,1,1,14,20,tzinfo=timezone.utc),start,False,False,True),"FINAL_REFRESH_DUE")
        self.assertEqual(classify_race(datetime(2030,1,1,14,31,tzinfo=timezone.utc),start,False,False,True),"MISSED_FINAL_WINDOW")
        self.assertEqual(classify_race(datetime(2030,1,1,14,20,tzinfo=timezone.utc),start,False,False,False),"SOURCE_UNSUPPORTED")

    def test_final_prediction_is_created_once_and_frozen(self):
        now=datetime(2030,1,1,14,20,tzinfo=timezone.utc);calls=[]
        def fake(script,args,timeout):
            calls.append(script)
            if script=="shadow_mode.py":
                with sqlite3.connect(self.db) as c:
                    c.execute("""INSERT INTO prediction_snapshots(
                        prediction_id,model_version,pipeline_version,race_id,horse_id,prediction_time,
                        race_start_at,logistic_probability,catboost_probability,xgboost_probability,
                        ensemble_probability,predicted_rank,feature_hash,feature_values_json,
                        feature_contract_version,feature_snapshot_id,source_request_id)
                        VALUES('run1:0','m','p','race-1430','h1','2030-01-01T14:20:00+00:00',
                        '2030-01-01T14:30:00+00:00',1,1,1,1,1,'hash','{}','v1',?,'program-1')""",(self.snapshot,))
            return {"script":script,"args":args,"exit_code":0,"stdout":"","stderr":"",
                    "started_at":now.isoformat(),"ended_at":now.isoformat(),"duration_seconds":0}
        first=process("2030-01-01",now,self.db,fake)
        self.assertIn("race-1430",first["due_races"]);self.assertEqual(calls.count("shadow_mode.py"),1)
        calls.clear();second=process("2030-01-01",datetime(2030,1,1,14,21,tzinfo=timezone.utc),self.db,fake)
        self.assertEqual(second["due_races"],[]);self.assertEqual(calls,[])
        with sqlite3.connect(self.db) as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM prediction_snapshots").fetchone()[0],1)
            row=c.execute("SELECT status,final_prediction_done_at,prediction_run_id FROM race_prediction_lifecycle").fetchone()
        self.assertEqual(row[0],"FINAL_PREDICTION_DONE");self.assertTrue(row[1]);self.assertEqual(row[2],"run1")

    def test_missed_window_never_calls_prediction(self):
        calls=[]
        result=process("2030-01-01",datetime(2030,1,1,14,31,tzinfo=timezone.utc),self.db,
                       lambda *args:(calls.append(args) or {"exit_code":0}))
        self.assertEqual(calls,[]);self.assertEqual(result["due_races"],[])
        with sqlite3.connect(self.db) as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM prediction_snapshots").fetchone()[0],0)
            self.assertEqual(c.execute("SELECT status FROM race_prediction_lifecycle").fetchone()[0],"MISSED_FINAL_WINDOW")


if __name__=="__main__":unittest.main()
