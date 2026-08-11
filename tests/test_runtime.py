import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from yuanjian_app.runtime import (
    RuntimeClient,
    RuntimeDiscovery,
    SingleInstance,
    _process_exists,
)


class RecordingResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return b'{"status":"shown"}'


class RecordingOpener:
    def __init__(self):
        self.request = None
        self.timeout = None

    def __call__(self, request, timeout):
        self.request = request
        self.timeout = timeout
        return RecordingResponse()


class RuntimeTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows process probe regression")
    def test_windows_process_probe_recognizes_a_gui_process(self):
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        if not pythonw.exists():
            self.skipTest("pythonw.exe is unavailable")
        child = subprocess.Popen(
            [str(pythonw), "-c", "import time; time.sleep(30)"],
        )
        try:
            self.assertTrue(_process_exists(child.pid))
            with self.assertRaises(subprocess.TimeoutExpired):
                child.wait(timeout=0.25)
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=5)

    @unittest.skipUnless(os.name == "nt", "Windows process probe regression")
    def test_windows_process_probe_never_sends_a_signal(self):
        with mock.patch(
            "yuanjian_app.runtime.os.kill",
            side_effect=AssertionError("Windows process probes must be read-only"),
        ):
            self.assertTrue(_process_exists(os.getpid()))

    def test_runtime_client_posts_token_to_existing_instance(self):
        opener = RecordingOpener()
        client = RuntimeClient(
            {"port": 4567, "token": "session-token"}, opener=opener
        )

        self.assertTrue(client.show_window())
        self.assertEqual(
            opener.request.full_url, "http://127.0.0.1:4567/api/window/show"
        )
        self.assertEqual(opener.request.get_method(), "POST")
        self.assertEqual(
            opener.request.headers["X-yuanjian-token"], "session-token"
        )
        self.assertEqual(opener.timeout, 2)

    def test_runtime_client_rejects_invalid_state_without_opening_network(self):
        opener = RecordingOpener()

        self.assertFalse(RuntimeClient({"port": 0, "token": "x"}, opener).show_window())
        self.assertIsNone(opener.request)
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
