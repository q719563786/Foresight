import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from yuanjian_app.database import Database
from yuanjian_app.notifications import NotificationService


class MutableClock:
    def __init__(self):
        self.value = datetime(2026, 8, 11, 8, tzinfo=timezone.utc)

    def __call__(self):
        return self.value


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temporary.name) / "yuanjian.db")
        self.database.initialize()
        self.clock = MutableClock()
        self.delivered = []
        self.service = NotificationService(
            self.database,
            notifier=lambda title, body: self.delivered.append((title, body)),
            now=self.clock,
        )

    def tearDown(self):
        self.temporary.cleanup()

    def impact(self, level="L3", evidence_hash="hash-1", window=24):
        return {
            "impact_id": "P-1",
            "cluster_id": "C-1",
            "alert_level": level,
            "evidence_hash": evidence_hash,
            "action_window_hours": window,
            "interest_name": "不应出现在系统通知的私人利益",
        }

    def test_six_hour_throttle_allows_material_upgrades(self):
        first = self.service.consider(self.impact(), "需要关注")
        repeated = self.service.consider(self.impact(), "重复消息")
        upgraded = self.service.consider(self.impact(level="L4"), "等级上升")
        new_evidence = self.service.consider(
            self.impact(level="L4", evidence_hash="hash-2"), "证据提升"
        )
        shorter = self.service.consider(
            self.impact(level="L4", evidence_hash="hash-2", window=6), "窗口缩短"
        )

        self.assertEqual(first["status"], "created")
        self.assertEqual(repeated["status"], "suppressed")
        self.assertEqual(upgraded["status"], "created")
        self.assertEqual(new_evidence["status"], "created")
        self.assertEqual(shorter["status"], "created")
        self.assertEqual(len(self.service.list_notifications()), 4)

        self.clock.value += timedelta(hours=6, seconds=1)
        self.assertEqual(
            self.service.consider(self.impact(level="L4", evidence_hash="hash-2", window=6), "到期")["status"],
            "created",
        )

    def test_l1_is_ignored_l2_is_digest_and_l4_system_text_is_generic(self):
        self.assertEqual(self.service.consider(self.impact("L1"), "低等级")["status"], "ignored")
        digest = self.service.consider(self.impact("L2"), "每日汇总")
        urgent = self.service.consider(self.impact("L4", "hash-2"), "私人医疗债务细节")

        self.assertEqual(digest["delivery"], "daily_digest")
        self.assertEqual(urgent["delivery"], "windows")
        system_text = " ".join(self.delivered[0])
        self.assertNotIn("私人", system_text)
        self.assertNotIn("医疗债务", system_text)

    def test_windows_failure_falls_back_to_readable_local_center(self):
        service = NotificationService(
            self.database,
            notifier=lambda title, body: (_ for _ in ()).throw(RuntimeError("toast failed")),
            now=self.clock,
        )

        result = service.consider(self.impact("L4"), "仍需保留")
        notifications = service.list_notifications()

        self.assertEqual(result["delivery"], "local_only")
        self.assertEqual(notifications[0]["reason"], "仍需保留")
        self.assertEqual(notifications[0]["status"], "unread")
        marked = service.mark_read(notifications[0]["notification_id"])
        self.assertEqual(marked["status"], "read")


if __name__ == "__main__":
    unittest.main()
