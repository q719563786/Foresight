import tempfile
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from yuanjian_app.database import Database
from yuanjian_app.external_radar import ExternalRadarService, parse_iso
from yuanjian_app.external_sources import ExternalItem, FetchError
from yuanjian_app.radar_scheduler import RadarScheduler


class Clock:
    def __init__(self):
        self.value = datetime(2026, 8, 7, 10, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.value


class RadarSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "yuanjian.db")
        self.database.initialize()
        self.clock = Clock()

    def tearDown(self):
        self.temp_dir.cleanup()

    def service(self, fetcher):
        service = ExternalRadarService(self.database, fetcher=fetcher, now=self.clock)
        service.add_source(
            {
                "source_id": "S-1",
                "name": "Official",
                "kind": "rss",
                "endpoint": "https://example.com/feed.xml",
                "refresh_minutes": 15,
            }
        )
        return service

    def test_run_once_fetches_immediately_then_waits_for_due_time(self):
        item = ExternalItem("S-1", "Official", "https://example.com/1", "政策提醒")
        calls = 0

        def fetcher(source):
            nonlocal calls
            calls += 1
            return [item]

        scheduler = RadarScheduler(self.service(fetcher), poll_seconds=0.01)

        self.assertEqual(scheduler.run_once(), 1)
        self.assertEqual(scheduler.run_once(), 0)
        self.clock.value += timedelta(minutes=15)
        self.assertEqual(scheduler.run_once(), 1)
        self.assertEqual(calls, 2)

    def test_repeated_failures_back_off_at_15_30_then_60_minutes(self):
        def fetcher(source):
            raise FetchError("timeout", "超时")

        service = self.service(fetcher)
        scheduler = RadarScheduler(service, poll_seconds=0.01)
        delays = []
        for expected in (15, 30, 60, 60):
            self.assertEqual(scheduler.run_once(), 1)
            source = service.list_sources()[0]
            delay = parse_iso(source["next_fetch_at"]) - self.clock.value
            delays.append(int(delay.total_seconds() / 60))
            self.assertEqual(delays[-1], expected)
            self.clock.value += timedelta(minutes=expected)

        self.assertEqual(delays, [15, 30, 60, 60])

    def test_background_scheduler_stops_without_leaving_a_thread(self):
        service = self.service(lambda source: [])
        scheduler = RadarScheduler(service, poll_seconds=0.01)

        scheduler.start()
        scheduler.stop(timeout=1)

        self.assertFalse(scheduler.running)

    def test_paused_source_is_not_fetched_until_reenabled(self):
        calls = 0

        def fetcher(source):
            nonlocal calls
            calls += 1
            return []

        service = self.service(fetcher)
        scheduler = RadarScheduler(service, poll_seconds=0.01)

        service.set_source_enabled("S-1", False)
        self.assertEqual(scheduler.run_once(), 0)
        service.set_source_enabled("S-1", True)
        self.assertEqual(scheduler.run_once(), 1)
        self.assertEqual(calls, 1)

    def test_cognition_failure_is_visible_in_runtime_state(self):
        class FailingCognition:
            def process_once(self):
                raise RuntimeError("cognition boom")

            def capture_trends(self):
                return {"snapshots": []}

        scheduler = RadarScheduler(
            self.service(lambda source: []),
            poll_seconds=0.01,
            database=self.database,
            cognition=FailingCognition(),
            now=self.clock,
        )

        result = scheduler.run_cognition_once()

        self.assertEqual(result["status"], "error")
        with self.database.connect() as connection:
            state = connection.execute(
                "SELECT value_json FROM runtime_state WHERE state_key='task.cognition'"
            ).fetchone()[0]
        payload = json.loads(state)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error_type"], "RuntimeError")
        self.assertNotIn("boom", payload.get("message", ""))


if __name__ == "__main__":
    unittest.main()
