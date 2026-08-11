import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from yuanjian_app.cognition import CognitionService
from yuanjian_app.database import Database


class CognitionServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temporary.name) / "yuanjian.db")
        self.database.initialize()
        self.service = CognitionService(self.database)

    def tearDown(self):
        self.temporary.cleanup()

    def add_source(self, source_id, domain, primary=False):
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO external_sources(
                    source_id, name, kind, endpoint, config_json
                ) VALUES (?, ?, 'rss', ?, ?)
                """,
                (
                    source_id,
                    source_id,
                    f"https://{domain}/feed",
                    json.dumps({"primary_source": primary}),
                ),
            )

    def add_item(self, item_id, source_id, domain, title, summary, hour=0):
        timestamp = f"2026-08-11T{hour:02d}:00:00Z"
        url = f"https://{domain}/{item_id.lower()}"
        content_hash = hashlib.sha256(f"{title}\n{summary}".encode()).hexdigest()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO external_items(
                    item_id, canonical_url, title, summary, published_at,
                    fetched_at, source_id, source_name, language, content_hash,
                    first_seen_at, last_seen_at, source_count, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Chinese', ?, ?, ?, 1, '{}')
                """,
                (
                    item_id,
                    url,
                    title,
                    summary,
                    timestamp,
                    timestamp,
                    source_id,
                    source_id,
                    content_hash,
                    timestamp,
                    timestamp,
                ),
            )
            connection.execute(
                "INSERT INTO external_item_sources VALUES (?, ?, ?, ?)",
                (item_id, source_id, url, timestamp),
            )

    def test_three_reports_become_one_traceable_cluster(self):
        self.add_source("S-A", "a.example")
        self.add_source("S-B", "b.example")
        reports = (
            ("E-1", "S-A", "a.example", "广东医保报销比例升至70%", "新政策本月实施", 0),
            ("E-2", "S-B", "b.example", "广东调整医保报销政策", "报销比例提高至70%", 2),
            ("E-3", "S-A", "a.example", "广东医保新规：报销比例提高到70%", "本月开始执行", 4),
        )
        for report in reports:
            self.add_item(*report)
            self.service.process_item(report[0])

        clusters = self.service.list_clusters()

        self.assertEqual(len(clusters), 1)
        detail = self.service.get_cluster(clusters[0]["cluster_id"])
        self.assertEqual(len(detail["items"]), 3)
        self.assertEqual(detail["independent_domains"], 2)
        self.assertTrue(all(item["merge_reason"] for item in detail["items"]))
        self.assertTrue(all(0 <= item["similarity"] <= 1 for item in detail["items"]))

    def test_evidence_levels_require_independence_and_primary_source(self):
        self.add_source("S-A", "a.example")
        self.add_source("S-B", "b.example")
        self.add_source("S-OFFICIAL", "a.example", primary=True)
        self.add_source("S-C", "c.example")
        base = ("广东医保报销比例升至70%", "政策本月实施")

        self.add_item("E-1", "S-A", "a.example", *base, 0)
        result = self.service.process_item("E-1")
        self.assertEqual(result["evidence_level"], "E1")

        self.add_item("E-2", "S-B", "b.example", *base, 1)
        result = self.service.process_item("E-2")
        self.assertEqual(result["evidence_level"], "E2")

        self.add_item("E-3", "S-OFFICIAL", "a.example", *base, 2)
        result = self.service.process_item("E-3")
        self.assertEqual(result["evidence_level"], "E3")

        self.add_item("E-4", "S-C", "c.example", *base, 3)
        result = self.service.process_item("E-4")
        self.assertEqual(result["evidence_level"], "E4")

    def test_evidence_hash_changes_only_when_evidence_changes(self):
        self.add_source("S-A", "a.example")
        self.add_source("S-B", "b.example")
        base = ("广东医保报销比例升至70%", "政策本月实施")
        self.add_item("E-1", "S-A", "a.example", *base, 0)

        first = self.service.process_item("E-1")
        repeated = self.service.process_item("E-1")

        self.assertEqual(first["evidence_hash"], repeated["evidence_hash"])
        self.assertFalse(repeated["changed"])
        with self.database.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM judgment_jobs").fetchone()[0], 0)

        self.add_item("E-2", "S-B", "b.example", *base, 1)
        expanded = self.service.process_item("E-2")

        self.assertNotEqual(first["evidence_hash"], expanded["evidence_hash"])
        self.assertTrue(expanded["changed"])
        self.assertTrue(expanded["needs_judgment"])

    def test_backfill_is_idempotent(self):
        self.add_source("S-A", "a.example")
        self.add_item(
            "E-1", "S-A", "a.example", "广东医保报销比例升至70%", "政策实施", 0
        )

        first = self.service.backfill_unclustered()
        second = self.service.backfill_unclustered()

        self.assertEqual(first["processed"], 1)
        self.assertEqual(second["processed"], 0)
        self.assertEqual(len(self.service.list_clusters()), 1)

    def test_historical_rfc2822_published_time_is_accepted(self):
        self.add_source("S-A", "a.example")
        self.add_item(
            "E-1", "S-A", "a.example", "广东医保报销比例升至70%", "政策实施", 0
        )
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE external_items SET published_at='Tue, 11 Aug 2026 00:00:00 GMT' WHERE item_id='E-1'"
            )

        result = self.service.process_item("E-1")

        self.assertEqual(result["evidence_level"], "E1")


if __name__ == "__main__":
    unittest.main()
