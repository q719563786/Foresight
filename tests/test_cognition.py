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

    def test_historical_cluster_markup_is_cleaned_when_read(self):
        self.add_source("S-A", "a.example")
        self.add_item("E-1", "S-A", "a.example", "医保政策", "公开说明", 0)
        cluster_id = self.service.process_item("E-1")["cluster_id"]
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE event_clusters SET title=?,summary=? WHERE cluster_id=?",
                (
                    '<a href="x">医保政策</a>',
                    '<font color="red">公开&nbsp;说明</font><script>bad()</script>',
                    cluster_id,
                ),
            )

        listed = self.service.list_clusters()[0]
        detailed = self.service.get_cluster(cluster_id)

        self.assertEqual((listed["title"], listed["summary"]), ("医保政策", "公开 说明"))
        self.assertEqual((detailed["title"], detailed["summary"]), ("医保政策", "公开 说明"))

    def test_cluster_page_filters_counts_and_validates_bounds(self):
        rows = (
            ("C-1", "广东医保政策", '["health","policy"]', "E3", 1, "2026-08-11T03:00:00Z"),
            ("C-2", "河源医院通知", '["health"]', "E2", 1, "2026-08-11T02:00:00Z"),
            ("C-3", "银行利率变化", '["finance"]', "E1", 0, "2026-08-11T01:00:00Z"),
        )
        with self.database.connect() as connection:
            for cluster_id, title, categories, evidence, needs, timestamp in rows:
                connection.execute(
                    """
                    INSERT INTO event_clusters(
                        cluster_id,title,summary,first_seen_at,last_seen_at,
                        evidence_level,evidence_hash,categories_json,status,
                        needs_judgment,independent_domains,primary_source_count,
                        created_at,updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        cluster_id, title, "摘要", timestamp, timestamp, evidence,
                        f"hash-{cluster_id}", categories, "active", needs, 1, 0,
                        timestamp, timestamp,
                    ),
                )

        page = self.service.list_clusters_page(
            limit=1, offset=1, query="", category="health", needs_judgment=True
        )

        self.assertEqual(page["total"], 2)
        self.assertEqual([item["cluster_id"] for item in page["items"]], ["C-2"])
        self.assertEqual((page["limit"], page["offset"]), (1, 1))
        with self.assertRaisesRegex(ValueError, "分页"):
            self.service.list_clusters_page(limit=0)
        with self.assertRaisesRegex(ValueError, "证据"):
            self.service.list_clusters_page(evidence="E9")


if __name__ == "__main__":
    unittest.main()
