import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from yuanjian_app.database import Database
from yuanjian_app.external_radar import ExternalRadarService
from yuanjian_app.external_sources import ExternalItem
from yuanjian_app.forecasts import ForecastService
from yuanjian_app.cognition import CognitionController, CognitionService
from yuanjian_app.http_api import Services, create_server
from yuanjian_app.impacts import ImpactService
from yuanjian_app.interests import InterestService
from yuanjian_app.knowledge import KnowledgeService
from yuanjian_app.signals import SignalService
from yuanjian_app.judgments import LocalHeuristicProvider, build_public_bundle
from yuanjian_app.notifications import NotificationService
from yuanjian_app.remote_ai import AiSettingsService, JudgmentQueue
from yuanjian_app.secret_store import DpapiSecretStore
from yuanjian_app.trends import TrendService


class HttpApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database = Database(Path(self.temp_dir.name) / "yuanjian.db")
        database.initialize()
        interests = InterestService(database)
        interests.ensure_defaults()
        signals = SignalService(database, interests)
        vault = Path(self.temp_dir.name) / "Obsidian" / "Vault"
        (vault / ".obsidian").mkdir(parents=True)
        (vault / "note.md").write_text("# 测试知识\n只读内容", encoding="utf-8")
        knowledge = KnowledgeService(database, home=Path(self.temp_dir.name))
        cognition = CognitionService(database)
        external = ExternalRadarService(
            database,
            fetcher=lambda source: [
                ExternalItem(
                    source["source_id"],
                    source["name"],
                    "https://example.com/policy/1",
                    "医保政策调整",
                    "公开征求意见",
                )
            ],
            on_item_stored=cognition.process_item,
        )
        forecasts = ForecastService(database)
        trends = TrendService(database)
        secret_store = DpapiSecretStore(
            Path(self.temp_dir.name) / "secrets" / "ai-token.dpapi",
            protect=lambda value: bytes(byte ^ 0xA5 for byte in value),
            unprotect=lambda value: bytes(byte ^ 0xA5 for byte in value),
        )
        ai_settings = AiSettingsService(database, secret_store)
        local = LocalHeuristicProvider()
        queue = JudgmentQueue(
            database,
            providers={"local": local},
            bundle_loader=lambda cluster_id: build_public_bundle(
                cognition.get_cluster(cluster_id), cognition.get_cluster(cluster_id)["items"]
            ),
            local_provider=local,
        )
        impacts = ImpactService(database, interests, forecasts)
        notifications = NotificationService(database, notifier=lambda title, body: None)
        controller = CognitionController(
            database,
            cognition,
            trends,
            queue,
            impacts,
            notifications,
            ai_settings,
            now=lambda: datetime(2026, 8, 11, 8, tzinfo=timezone.utc),
        )
        self.services = Services(
            forecasts,
            interests,
            signals,
            knowledge,
            external,
            cognition,
            trends,
            controller,
            notifications,
            impacts,
            None,
            ai_settings,
        )
        self.server = create_server("127.0.0.1", 0, "test-token", self.services)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp_dir.cleanup()

    def test_server_rejects_non_loopback_binding(self):
        with self.assertRaisesRegex(ValueError, "只允许本机访问"):
            create_server("0.0.0.0", 0, "token", self.services)

    def test_post_without_session_token_is_forbidden(self):
        request = urllib.request.Request(
            self.base_url + "/api/events",
            data=json.dumps({"text": "新事件"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(request, timeout=2)

        self.assertEqual(raised.exception.code, 403)
        raised.exception.close()

    def test_home_page_is_local_chinese_ui(self):
        with urllib.request.urlopen(self.base_url + "/", timeout=2) as response:
            body = response.read().decode("utf-8")

        self.assertIn("今日雷达", body)
        self.assertNotIn("https://", body)

    def test_home_page_exposes_formal_forecast_and_safe_exit_controls(self):
        with urllib.request.urlopen(self.base_url + "/", timeout=2) as response:
            body = response.read().decode("utf-8")

        self.assertIn("新建预测", body)
        self.assertIn('data-view="create"', body)
        self.assertIn("安全退出", body)

    def test_home_page_exposes_sensory_center_navigation(self):
        with urllib.request.urlopen(self.base_url + "/", timeout=2) as response:
            body = response.read().decode("utf-8")

        self.assertIn("利益地图", body)
        self.assertIn("信号收件箱", body)
        self.assertIn("知识库", body)

    def test_home_page_makes_external_information_radar_the_default_view(self):
        with urllib.request.urlopen(self.base_url + "/", timeout=2) as response:
            body = response.read().decode("utf-8")

        self.assertIn("事件判断雷达", body)
        self.assertIn('data-view="cognition"', body)
        self.assertIn("后台监控", body)
        self.assertIn("证据等级", body)
        self.assertIn("反对证据", body)
        self.assertIn("时间窗口", body)
        with urllib.request.urlopen(self.base_url + "/app.js", timeout=2) as response:
            script = response.read().decode("utf-8")
        self.assertIn("showCognition().catch(showError)", script)

    def test_forecast_api_returns_json(self):
        request = urllib.request.Request(
            self.base_url + "/api/forecasts",
            headers={"X-YuanJian-Token": "test-token"},
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))

        self.assertEqual(payload, {"forecasts": []})

    def test_external_source_rule_refresh_and_radar_apis_form_a_complete_flow(self):
        status, source = self.post_json(
            "/api/external/sources",
            {
                "name": "官方政策源",
                "kind": "rss",
                "endpoint": "https://example.com/feed.xml",
            },
        )
        _, rule = self.post_json(
            "/api/external/rules", {"query": "医保", "importance": 5}
        )
        _, refresh = self.post_json(
            "/api/external/refresh", {"source_id": source["source_id"]}
        )

        sources = self.get_json("/api/external/sources")
        rules = self.get_json("/api/external/rules")
        radar = self.get_json("/api/external/radar")

        self.assertEqual(status, 201)
        self.assertEqual(rule["rule_id"], rules["rules"][0]["rule_id"])
        self.assertEqual(refresh["new_count"], 1)
        self.assertEqual(sources["sources"][0]["last_status"], "ok")
        self.assertEqual(radar["items"][0]["title"], "医保政策调整")

        _, paused = self.post_json(
            f"/api/external/sources/{source['source_id']}/enabled", {"enabled": False}
        )
        self.assertFalse(paused["enabled"])

    def test_event_api_persists_signal_and_interest_api_lists_filters(self):
        status, created = self.post_json(
            "/api/events", {"text": "明天预计支付12000元医疗费用", "occurred_at": "2026-08-06"}
        )

        self.assertEqual(status, 201)
        self.assertEqual(created["signal"]["alert_level"], "L4")
        signal_request = urllib.request.Request(
            self.base_url + "/api/signals",
            headers={"X-YuanJian-Token": "test-token"},
        )
        interest_request = urllib.request.Request(
            self.base_url + "/api/interests",
            headers={"X-YuanJian-Token": "test-token"},
        )
        with urllib.request.urlopen(signal_request, timeout=2) as response:
            signals = json.loads(response.read().decode("utf-8"))["signals"]
        with urllib.request.urlopen(interest_request, timeout=2) as response:
            interests = json.loads(response.read().decode("utf-8"))["objects"]

        self.assertEqual(len(signals), 1)
        self.assertEqual(len(interests), 7)

    def test_knowledge_api_discovers_indexes_and_lists_documents(self):
        request = urllib.request.Request(
            self.base_url + "/api/knowledge/vaults",
            headers={"X-YuanJian-Token": "test-token"},
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            vaults = json.loads(response.read().decode("utf-8"))["vaults"]

        status, result = self.post_json("/api/knowledge/index", {"path": vaults[0]["path"]})
        documents_request = urllib.request.Request(
            self.base_url + "/api/knowledge/documents?q=" + urllib.parse.quote("测试"),
            headers={"X-YuanJian-Token": "test-token"},
        )
        with urllib.request.urlopen(documents_request, timeout=2) as response:
            documents = json.loads(response.read().decode("utf-8"))["documents"]

        self.assertEqual(status, 201)
        self.assertEqual(result["indexed"], 1)
        self.assertEqual(documents[0]["title"], "测试知识")

    def valid_forecast(self, **changes):
        data = {
            "forecast_id": "F-HTTP-1",
            "title": "本地接口预测",
            "resolution_criteria": "到期可以核验",
            "window_start": "2026-08-06",
            "window_end": "2026-08-31",
            "probability": 0.65,
            "confidence": "medium",
            "alert_level": "L2",
            "privacy_level": "P2",
        }
        data.update(changes)
        return data

    def post_json(self, path, payload, token="test-token"):
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-YuanJian-Token": token,
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def get_json(self, path, token="test-token"):
        request = urllib.request.Request(
            self.base_url + path, headers={"X-YuanJian-Token": token}
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_create_forecast_api_records_formal_prediction(self):
        status, created = self.post_json("/api/forecasts", self.valid_forecast())

        self.assertEqual(status, 201)
        self.assertEqual(created["version"], 1)
        request = urllib.request.Request(
            self.base_url + "/api/forecasts",
            headers={"X-YuanJian-Token": "test-token"},
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(payload["forecasts"][0]["forecast_id"], "F-HTTP-1")

    def test_create_forecast_api_reports_duplicate_identity_as_conflict(self):
        self.post_json("/api/forecasts", self.valid_forecast())

        request = urllib.request.Request(
            self.base_url + "/api/forecasts",
            data=json.dumps(self.valid_forecast()).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-YuanJian-Token": "test-token",
            },
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(request, timeout=2)
        self.assertEqual(raised.exception.code, 409)
        raised.exception.close()

    def test_add_forecast_version_api_deduplicates_identical_revision(self):
        self.post_json("/api/forecasts", self.valid_forecast())

        _, changed = self.post_json(
            "/api/forecasts/F-HTTP-1/versions",
            self.valid_forecast(probability=0.80),
        )
        _, duplicate = self.post_json(
            "/api/forecasts/F-HTTP-1/versions",
            self.valid_forecast(probability=0.80),
        )

        self.assertEqual(changed, {"forecast_id": "F-HTTP-1", "version": 2, "duplicate": False})
        self.assertEqual(duplicate, {"forecast_id": "F-HTTP-1", "version": 2, "duplicate": True})

    def test_shutdown_api_requires_token_and_stops_server(self):
        forbidden = urllib.request.Request(
            self.base_url + "/api/shutdown",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(forbidden, timeout=2)
        self.assertEqual(raised.exception.code, 403)
        raised.exception.close()

        status, payload = self.post_json("/api/shutdown", {})
        self.thread.join(timeout=2)

        self.assertEqual(status, 200)
        self.assertEqual(payload, {"status": "shutting_down"})
        self.assertFalse(self.thread.is_alive())

    def test_cognition_run_returns_cluster_judgment_impacts_and_candidate(self):
        self.services.external.fetcher = lambda source: [
            ExternalItem(
                source["source_id"],
                source["name"],
                f"https://{source['source_id'].lower()}.example/policy",
                "广东医保报销比例升至70%",
                "政策本月实施",
                "2026-08-11T00:00:00Z",
            )
        ]
        for index in range(1, 4):
            _, source = self.post_json(
                "/api/external/sources",
                {
                    "source_id": f"S-C{index}",
                    "name": f"来源{index}",
                    "kind": "rss",
                    "endpoint": f"https://feed{index}.example/rss",
                },
            )
            self.post_json("/api/external/refresh", {"source_id": source["source_id"]})

        _, run = self.post_json("/api/cognition/run", {})
        clusters = self.get_json("/api/cognition/clusters")["clusters"]
        detail = self.get_json(
            f"/api/cognition/clusters/{clusters[0]['cluster_id']}"
        )

        self.assertGreaterEqual(run["judgments"]["succeeded"], 1)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(detail["items"]), 3)
        self.assertIn("evidence_level", detail)
        self.assertTrue(detail["judgment"]["causal_chain"])
        self.assertIn("uncertainties", detail["judgment"])
        self.assertTrue(detail["judgment"]["horizons"])
        self.assertTrue(detail["impacts"])
        self.assertTrue(detail["impacts"][0]["candidate"])

    def test_ai_settings_never_return_secret_and_posts_require_token(self):
        status, saved = self.post_json(
            "/api/settings/ai",
            {
                "enabled": True,
                "endpoint": "https://api.openai.com/v1/responses",
                "model": "explicit-model",
                "token": "private-api-token",
            },
        )
        visible = self.get_json("/api/settings/ai")

        self.assertEqual(status, 200)
        self.assertTrue(saved["configured"])
        self.assertNotIn("token", visible)
        self.assertNotIn("private-api-token", json.dumps(visible))
        request = urllib.request.Request(
            self.base_url + "/api/settings/ai",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(request, timeout=2)
        self.assertEqual(raised.exception.code, 403)
        raised.exception.close()

    def test_feedback_stays_in_local_personal_impacts(self):
        cluster_id, judgment_id = "C-feedback", "J-feedback"
        now = "2026-08-11T08:00:00Z"
        result = LocalHeuristicProvider().analyze(
            build_public_bundle(
                {"cluster_id": cluster_id, "title": "政策", "summary": "", "evidence_level": "E1", "categories": ["policy"]},
                [{"source_id": "S-1", "title": "通知", "summary": "公开", "canonical_url": "https://news.example/1", "published_at": now}],
            )
        )
        with self.services.cognition.database.connect() as connection:
            connection.execute("INSERT INTO event_clusters(cluster_id,title,summary,first_seen_at,last_seen_at,evidence_hash,categories_json,latest_judgment_id,created_at,updated_at) VALUES (?,?,'',?,?,?,?,?,?,?)", (cluster_id,"政策",now,now,"hash",'["policy"]',judgment_id,now,now))
            connection.execute("INSERT INTO judgments VALUES (?,?,?,?,?,?)", (judgment_id,cluster_id,"local","hash",json.dumps(result.to_dict(),ensure_ascii=False),now))
        self.services.impacts.map_judgment(cluster_id, judgment_id)

        self.post_json(f"/api/cognition/clusters/{cluster_id}/feedback", {"action": "false_positive"})

        with self.services.cognition.database.connect() as connection:
            labels = [row[0] for row in connection.execute("SELECT user_label FROM personal_impacts WHERE cluster_id=?", (cluster_id,))]
        self.assertTrue(labels)
        self.assertEqual(set(labels), {"false_positive"})


if __name__ == "__main__":
    unittest.main()
