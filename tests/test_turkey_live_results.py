import unittest
from pathlib import Path

import pandas as pd

from race_scope import clean_track, is_turkey_track
from shadow_mode import eligible_today
from update_results import filter_program_horses


class TurkeyLiveResultsTests(unittest.TestCase):
    def test_turkey_scope_aliases_and_foreign_rejection(self):
        self.assertEqual(clean_track("Veliefendi"), "İstanbul")
        for track in ("İstanbul", "Ankara", "İzmir", "Şanlıurfa", "Osmangazi"):
            self.assertTrue(is_turkey_track(track), track)
        for track in ("Belmont", "Hawthorne", "Woodbine", "Selangor", "Karma"):
            self.assertFalse(is_turkey_track(track), track)

    def test_result_selection_excludes_foreign_and_completed_tracks(self):
        horses = [
            {"city_name": "İstanbul", "horse_id": "i"},
            {"city_name": "İzmir", "horse_id": "z"},
            {"city_name": "Woodbine", "horse_id": "w"},
        ]
        selected = filter_program_horses(horses, "TR", completed_tracks={"İstanbul"})
        self.assertEqual([row["horse_id"] for row in selected], ["z"])

    def test_shadow_eligibility_includes_all_program_tracks(self):
        now = pd.Timestamp("2030-01-01T10:00:00Z")
        frame = pd.DataFrame({
            "race_id": ["tr", "foreign"], "track": ["Ankara", "Belmont"],
            "race_start_at": ["2030-01-01T12:00:00Z", "2030-01-01T12:00:00Z"],
        })
        selected = eligible_today(frame, "2030-01-01", now)
        self.assertEqual(selected["race_id"].tolist(), ["tr", "foreign"])

    def test_polling_script_has_countdown_overlap_and_visibility_guards(self):
        script = (Path(__file__).resolve().parents[1] / "web" / "static" / "live-results.js").read_text(encoding="utf-8")
        self.assertIn("this.remaining = 300", script)
        self.assertIn("this.inFlight", script)
        self.assertIn("visibilitychange", script)
        self.assertIn("this.remaining=300", script)
        self.assertIn("data.seconds_remaining", script)
        self.assertIn("this.deadline", script)
        self.assertIn("/api/results-refresh/status", script)


if __name__ == "__main__":
    unittest.main()
