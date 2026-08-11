import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from yuanjian_app.database import Database
from yuanjian_app.external_radar import ExternalRadarService
from yuanjian_app.external_sources import ExternalItem, FetchError


class MutableClock:
    def __init__(self):
        self.value = datetime(2026, 8, 7, 9, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.value


class ExternalRadarTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "yuanjian.db")
        self.database.initialize()
        self.clock = MutableClock()

    def tearDown(self):
        self.temp_dir.cleanup()

    def item(self, source_id="S-1", source_name="Official feed"):
        return ExternalItem(
            source_id=source_id,
            source_name=source_name,
            url="https://example.com/notices/88?utm_source=rss",
            title="河源水泵项目公开招标",
            summary="消防工程设备采购",
            published_at="2026-08-07T08:30:00Z",
        )

    def service(self, fetcher):
        return ExternalRadarService(self.database, fetcher=fetcher, now=self.clock)

    def add_source_and_rule(self, service, source_id="S-1", name="Official feed"):
        service.add_source(
            {
                "source_id": source_id,
                "name": name,
                "kind": "rss",
                "endpoint": f"https://example.com/{source_id}.xml",
                "refresh_minutes": 15,
                "reliability_weight": 0.9,
            }
        )
        service.add_watch_rule(
            {"rule_id": "W-1", "query": "水泵", "importance": 5}
        )

    def test_repeated_refresh_is_idempotent_and_only_matches_relevant_items(self):
        service = self.service(lambda source: [self.item()])
        self.add_source_and_rule(service)

        first = service.refresh_source("S-1")
        second = service.refresh_source("S-1")
        radar = service.radar_items()

        self.assertEqual(first["new_count"], 1)
        self.assertEqual(second["new_count"], 0)
        self.assertEqual(len(radar), 1)
        self.assertEqual(radar[0]["matched_rules"][0]["query"], "水泵")
        self.assertIn(radar[0]["alert_level"], {"L3", "L4"})

    def test_unmatched_external_item_stays_out_of_main_radar(self):
        irrelevant = ExternalItem(
            source_id="S-1",
            source_name="Official feed",
            url="https://example.com/sports/1",
            title="足球比赛结果",
            summary="本轮联赛比分",
        )
        service = self.service(lambda source: [irrelevant])
        self.add_source_and_rule(service)

        service.refresh_source("S-1")

        self.assertEqual(service.radar_items(), [])
        with self.database.connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM external_items").fetchone()[0]
        self.assertEqual(count, 1)

    def test_same_url_from_two_sources_increases_independent_source_count(self):
        def fetcher(source):
            return [self.item(source["source_id"], source["name"])]

        service = self.service(fetcher)
        self.add_source_and_rule(service)
        service.add_source(
            {
                "source_id": "S-2",
                "name": "Second source",
                "kind": "rss",
                "endpoint": "https://example.org/feed.xml",
            }
        )

        service.refresh_source("S-1")
        service.refresh_source("S-2")

        self.assertEqual(service.radar_items()[0]["source_count"], 2)

    def test_source_failure_keeps_cached_items_and_records_failure_type(self):
        calls = 0

        def fetcher(source):
            nonlocal calls
            calls += 1
            if calls == 1:
                return [self.item()]
            raise FetchError("timeout", "外部源请求超时")

        service = self.service(fetcher)
        self.add_source_and_rule(service)
        service.refresh_source("S-1")

        failed = service.refresh_source("S-1")

        self.assertEqual(failed["status"], "error")
        self.assertEqual(failed["error_type"], "timeout")
        self.assertEqual(len(service.radar_items()), 1)
        source = service.list_sources()[0]
        self.assertEqual(source["consecutive_failures"], 1)
        self.assertIn("超时", source["last_error"])

    def test_source_becomes_stale_after_twice_its_refresh_interval(self):
        service = self.service(lambda source: [self.item()])
        self.add_source_and_rule(service)
        service.refresh_source("S-1")

        self.clock.value += timedelta(minutes=31)

        self.assertTrue(service.list_sources()[0]["stale"])

    def test_identical_watch_rule_is_reused_instead_of_duplicated(self):
        service = self.service(lambda source: [])

        first = service.add_watch_rule({"query": "水泵", "importance": 5})
        second = service.add_watch_rule({"query": "水泵", "importance": 5})

        self.assertEqual(second, first)
        self.assertEqual(len(service.list_rules()), 1)

    def test_item_callback_runs_after_commit_and_failure_is_audited(self):
        observed = []

        def callback(item_id):
            with self.database.connect() as connection:
                observed.append(
                    connection.execute(
                        "SELECT title FROM external_items WHERE item_id=?", (item_id,)
                    ).fetchone()[0]
                )
            raise RuntimeError("cluster test failure")

        service = ExternalRadarService(
            self.database,
            fetcher=lambda source: [self.item()],
            now=self.clock,
            on_item_stored=callback,
        )
        self.add_source_and_rule(service)

        result = service.refresh_source("S-1")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(observed, ["河源水泵项目公开招标"])
        with self.database.connect() as connection:
            audit = connection.execute(
                "SELECT action, details_json FROM audit_log ORDER BY audit_id DESC"
            ).fetchone()
        self.assertEqual(audit["action"], "cognition.process_failed")
        self.assertIn("RuntimeError", audit["details_json"])


if __name__ == "__main__":
    unittest.main()
