import json
import os
import tempfile
import unittest
from pathlib import Path

from yuanjian_app.runtime import RuntimeDiscovery, SingleInstance


class RuntimeTests(unittest.TestCase):
    def test_only_one_instance_can_hold_the_same_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "runtime" / "yuanjian.lock"
            first = SingleInstance(path)
            second = SingleInstance(path)

            self.assertTrue(first.acquire())
            self.assertFalse(second.acquire())
            first.release()
            self.assertTrue(second.acquire())
            second.release()

    def test_discovery_publishes_valid_state_and_clears_stale_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "runtime.json"
            alive = {123}
            discovery = RuntimeDiscovery(path, process_exists=lambda pid: pid in alive)

            discovery.publish(123, 54321, "session-token", "2026-08-11T08:00:00Z")

            self.assertEqual(discovery.read_valid()["port"], 54321)
            self.assertNotIn("other secret", path.read_text(encoding="utf-8"))
            alive.clear()
            self.assertIsNone(discovery.read_valid())
            self.assertFalse(path.exists())

    def test_invalid_or_currently_unowned_state_is_removed(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "runtime.json"
            path.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
            discovery = RuntimeDiscovery(path, process_exists=lambda pid: True)

            self.assertIsNone(discovery.read_valid())
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
