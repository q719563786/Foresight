import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from yuanjian_app.database import Database
from yuanjian_app.trends import TrendService


class TrendServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temporary.name) / "yuanjian.db")
        self.database.initialize()
        self.service = TrendService(self.database)
        self.now = datetime(2026, 8, 11, 12, tzinfo=timezone.utc)
        self.counter = 0

    def tearDown(self):
        self.temporary.cleanup()

    def add_cluster(self, seen_at, category="health"):
        self.counter += 1
        timestamp = seen_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO event_clusters(
                    cluster_id,title,summary,first_seen_at,last_seen_at,
                    evidence_hash,categories_json,created_at,updated_at
                ) VALUES (?,?, '',?,?,?, ?,?,?)
                """,
                (
                    f"C-{self.counter}",
                    f"事件{self.counter}",
                    timestamp,
                    timestamp,
                    f"hash-{self.counter}",
                    json.dumps([category]),
                    timestamp,
                    timestamp,
                ),
            )

    def summary_for(self, window_hours=24):
        return next(
            row
            for row in self.service.summary(self.now)
            if row["category"] == "health" and row["window_hours"] == window_hours
        )

    def test_six_days_of_history_is_reported_as_accumulating(self):
        for day in range(6):
            self.add_cluster(self.now - timedelta(days=day, hours=2))

        result = self.summary_for()

        self.assertEqual(result["status"], "accumulating")
        self.assertNotIn("surge_ratio", result)
        self.assertNotIn("baseline_count", result)

    def test_recent_surge_is_compared_with_prior_daily_baseline(self):
        for day in range(2, 31):
            self.add_cluster(self.now - timedelta(days=day, hours=2))
            self.add_cluster(self.now - timedelta(days=day, hours=8))
        for hour in range(1, 11):
            self.add_cluster(self.now - timedelta(hours=hour))

        result = self.summary_for()

        self.assertEqual(result["event_count"], 10)
        self.assertEqual(result["status"], "rising")
        self.assertAlmostEqual(result["baseline_count"], 2.0, delta=0.2)
        self.assertGreater(result["surge_ratio"], 4)

    def test_small_recent_sample_is_not_called_a_surge(self):
        for day in range(2, 15):
            self.add_cluster(self.now - timedelta(days=day, hours=2))
            self.add_cluster(self.now - timedelta(days=day, hours=8))
        for hour in (2, 5, 8):
            self.add_cluster(self.now - timedelta(hours=hour))

        result = self.summary_for()

        self.assertEqual(result["event_count"], 3)
        self.assertEqual(result["status"], "low_sample")
        self.assertNotIn("surge_ratio", result)

    def test_capture_is_idempotent_for_same_time(self):
        self.add_cluster(self.now - timedelta(days=10))

        first = self.service.capture(self.now)
        second = self.service.capture(self.now)

        self.assertEqual(first, second)
        with self.database.connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM trend_snapshots").fetchone()[0]
        self.assertEqual(count, len(first["snapshots"]))


if __name__ == "__main__":
    unittest.main()
