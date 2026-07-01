import sqlite3
import tempfile
import unittest
from pathlib import Path

from migrate_provenance_schema import apply_migrations
from pedigreeall_core import resolve_tjk_id
from results_coverage import build_results_coverage
from backfill_tjk_links_from_program import backfill_links


class TjkResolverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.temp.name)
        self.db = self.root / "test.db"
        apply_migrations(self.db)
        
        # Populate DDL of horse_links, horse_profiles, horse_mapping, race_program_entries, etc.
        # Note: apply_migrations already creates the migration tables.
        # But we also make sure core tables exist:
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS horse_links(
                       tjk_id TEXT PRIMARY KEY,
                       horse_id INTEGER,
                       match_method TEXT NOT NULL,
                       confidence REAL NOT NULL,
                       evidence_json TEXT,
                       verified INTEGER NOT NULL DEFAULT 0,
                       updated_at TEXT NOT NULL
                   )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS horse_mapping(
                       tjk_id TEXT,
                       horse_id INTEGER,
                       source_name TEXT,
                       api_name TEXT,
                       match_method TEXT,
                       confidence REAL,
                       verified INTEGER,
                       updated_at TEXT
                   )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS race_program_entries(
                       program_date TEXT NOT NULL,
                       city_id INTEGER,
                       city_name TEXT,
                       race_tab_id INTEGER,
                       race_name TEXT,
                       race_no TEXT,
                       tjk_id TEXT,
                       horse_id INTEGER,
                       horse_name TEXT,
                       age INTEGER,
                       weight TEXT,
                       jockey TEXT,
                       owner TEXT,
                       trainer TEXT,
                       gate TEXT,
                       handicap TEXT,
                       last_6_race TEXT,
                       kgs TEXT,
                       odds TEXT,
                       agf TEXT,
                       race_time TEXT,
                       horse_info_json TEXT,
                       PRIMARY KEY(program_date, city_id, race_tab_id, tjk_id)
                   )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS horse_profiles(
                       horse_key TEXT PRIMARY KEY,
                       tjk_id TEXT,
                       horse_id INTEGER,
                       name TEXT,
                       updated_at TEXT
                   )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS horse_races(
                       horse_key TEXT NOT NULL,
                       race_id TEXT NOT NULL,
                       race_date TEXT,
                       finish TEXT,
                       PRIMARY KEY(horse_key, race_id)
                   )"""
            )

    def tearDown(self):
        self.temp.cleanup()

    def test_vital_resolver_program_entry_priority(self):
        # VİTAL: race_program_entries.tjk_id=97242 is resolved even if horse_links is empty.
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                """INSERT INTO race_program_entries(program_date, city_id, race_tab_id, tjk_id, horse_id, horse_name)
                   VALUES('2026-07-01', 1, 1, '97242', 1745492, 'VİTAL')"""
            )
            
            res = resolve_tjk_id(connection, 1745492, "VİTAL", "2026-07-01")
            self.assertEqual(res["tjk_id"], "97242")
            self.assertEqual(res["source_table"], "race_program_entries")

    def test_resolver_links_priority(self):
        # race_program_entries is empty, but horse_links verified=1 exists
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                """INSERT INTO horse_links(tjk_id, horse_id, match_method, confidence, verified, updated_at)
                   VALUES('8888', 12345, 'manual', 1.0, 1, 'now')"""
            )
            
            res = resolve_tjk_id(connection, 12345)
            self.assertEqual(res["tjk_id"], "8888")
            self.assertEqual(res["source_table"], "horse_links")

    def test_resolver_profiles_priority(self):
        # horse_links empty, but horse_profiles exists
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                """INSERT INTO horse_profiles(horse_key, tjk_id, horse_id, name, updated_at)
                   VALUES('tjk:7777', '7777', 112233, 'STAR', 'now')"""
            )
            
            res = resolve_tjk_id(connection, 112233)
            self.assertEqual(res["tjk_id"], "7777")
            self.assertEqual(res["source_table"], "horse_profiles")

    def test_resolver_name_fallback(self):
        # horse_id lookup fails, fallback to name matching in horse_profiles
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                """INSERT INTO horse_profiles(horse_key, tjk_id, horse_id, name, updated_at)
                   VALUES('tjk:9999', '9999', 99999, 'SHADOW', 'now')"""
            )
            
            # Using lowercase name and dotless i/dotted i equivalents
            res = resolve_tjk_id(connection, None, "shadow")
            self.assertEqual(res["tjk_id"], "9999")
            self.assertTrue("normalized name fallback" in res["reason"])

    def test_resolver_mapping_fallback(self):
        # legacy horse_mapping works as fallback
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                """INSERT INTO horse_mapping(tjk_id, horse_id, verified, updated_at)
                   VALUES('5555', 443322, 1, 'now')"""
            )
            
            res = resolve_tjk_id(connection, 443322)
            self.assertEqual(res["tjk_id"], "5555")
            self.assertEqual(res["source_table"], "horse_mapping")

    def test_resolver_no_id_found(self):
        # When no source contains the ID
        with sqlite3.connect(self.db) as connection:
            res = resolve_tjk_id(connection, 999999)
            self.assertIsNone(res["tjk_id"])

    def test_coverage_categories_ambiguous_and_unpublished(self):
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                """INSERT INTO program_snapshots(
                       race_id, horse_id, race_start_at, race_no, captured_at, source_endpoint, source_request_id, track, horse_name
                   ) VALUES('race-1', 'horse:111', '2026-07-01T15:00:00', 1, 'now', 'endpoint', 'req1', 'İZMİR', 'AT1')"""
            )
            connection.execute(
                """INSERT INTO program_snapshots(
                       race_id, horse_id, race_start_at, race_no, captured_at, source_endpoint, source_request_id, track, horse_name
                   ) VALUES('race-1', 'horse:222', '2026-07-01T15:00:00', 1, 'now', 'endpoint', 'req1', 'İZMİR', 'AT2')"""
            )
            
            # Resolve mapping so TJK IDs are known
            connection.execute(
                "INSERT INTO horse_links(tjk_id, horse_id, match_method, confidence, verified, updated_at) VALUES('tjk1', 111, 'manual', 1.0, 1, 'now')"
            )
            connection.execute(
                "INSERT INTO horse_links(tjk_id, horse_id, match_method, confidence, verified, updated_at) VALUES('tjk2', 222, 'manual', 1.0, 1, 'now')"
            )

            # 1. AT1 has no results published -> PROVIDER_RESULT_NOT_PUBLISHED
            # 2. Let's make AT2 have results published, but no race_results row -> DATA_MISSING
            connection.execute(
                "INSERT INTO horse_races(horse_key, race_id, race_date, finish) VALUES('tjk:tjk2', 'r-legacy', '01.07.2026', '1')"
            )
            
            coverage = build_results_coverage(connection, "2026-07-01")
            
            missing_horses = {h["horse_name"]: h for h in coverage["missing_horses"]}
            self.assertEqual(missing_horses["AT1"]["missing_reason"], "PROVIDER_RESULT_NOT_PUBLISHED")
            self.assertEqual(missing_horses["AT2"]["missing_reason"], "DATA_MISSING")

            # Assert TJK_ID_MISSING is NOT used for AT1 or AT2
            self.assertNotEqual(missing_horses["AT1"]["missing_reason"], "TJK_ID_MISSING")
            self.assertNotEqual(missing_horses["AT2"]["missing_reason"], "TJK_ID_MISSING")

    def test_backfill_links_script(self):
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                """INSERT INTO race_program_entries(program_date, city_id, race_tab_id, tjk_id, horse_id, horse_name)
                   VALUES('2026-07-01', 1, 1, '9911', 8811, 'AT_BACKFILL')"""
            )
            
        report = backfill_links(self.db, "2026-07-01")
        self.assertEqual(report["inserted_count"], 1)

        # Check in DB that links were inserted
        with sqlite3.connect(self.db) as connection:
            row = connection.execute("SELECT tjk_id, verified FROM horse_links WHERE horse_id = 8811").fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], "9911")
            self.assertEqual(row[1], 1)


if __name__ == "__main__":
    unittest.main()
