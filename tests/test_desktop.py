import unittest

from yuanjian_app.desktop import DesktopLifecycle


class RecordingWindow:
    def __init__(self):
        self.calls = []

    def hide(self):
        self.calls.append("hide")

    def show(self):
        self.calls.append("show")

    def restore(self):
        self.calls.append("restore")


class RecordingTray:
    def __init__(self):
        self.calls = []

    def stop(self):
        self.calls.append("stop")


class RecordingMonitor:
    def __init__(self):
        self.paused = False

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False


class DesktopLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.window = RecordingWindow()
        self.tray = RecordingTray()
        self.monitor = RecordingMonitor()
        self.shutdown_calls = []
        self.cognition_calls = []
        self.lifecycle = DesktopLifecycle(
            window=self.window,
            tray=self.tray,
            monitor=self.monitor,
            run_cognition=lambda: self.cognition_calls.append("run") or {"status": "ok"},
            request_shutdown=lambda: self.shutdown_calls.append("shutdown"),
        )

    def test_close_hides_window_without_requesting_shutdown(self):
        self.assertFalse(self.lifecycle.close_to_tray())

        self.assertEqual(self.window.calls, ["hide"])
        self.assertEqual(self.shutdown_calls, [])

    def test_show_window_restores_the_existing_window(self):
        self.lifecycle.show_window()

        self.assertEqual(self.window.calls, ["show", "restore"])

    def test_tray_exit_stops_tray_and_requests_safe_shutdown_once(self):
        self.lifecycle.request_exit()
        self.lifecycle.request_exit()

        self.assertEqual(self.tray.calls, ["stop"])
        self.assertEqual(self.shutdown_calls, ["shutdown"])

    def test_close_allows_window_destruction_after_exit_begins(self):
        self.lifecycle.request_exit()

        self.assertTrue(self.lifecycle.close_to_tray())
        self.assertEqual(self.window.calls, [])

    def test_toggle_monitoring_returns_new_running_state(self):
        self.assertFalse(self.lifecycle.toggle_monitoring())
        self.assertTrue(self.monitor.paused)
        self.assertTrue(self.lifecycle.toggle_monitoring())
        self.assertFalse(self.monitor.paused)

    def test_manual_cognition_uses_the_shared_callback(self):
        self.assertEqual(self.lifecycle.run_cognition_once(), {"status": "ok"})
        self.assertEqual(self.cognition_calls, ["run"])


if __name__ == "__main__":
    unittest.main()
