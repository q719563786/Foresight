import tempfile
import unittest
from pathlib import Path

from yuanjian_app.application import Application, is_background_mode, should_open_browser
from yuanjian_app.http_api import resolve_static_root


class ApplicationTests(unittest.TestCase):
    def test_no_browser_environment_is_reserved_for_automated_smoke_tests(self):
        self.assertTrue(should_open_browser({}))
        self.assertFalse(should_open_browser({"YUANJIAN_NO_BROWSER": "1"}))

    def test_background_argument_or_environment_disables_browser(self):
        self.assertTrue(is_background_mode(["--background"], {}))
        self.assertTrue(is_background_mode([], {"YUANJIAN_BACKGROUND": "1"}))
        self.assertFalse(is_background_mode([], {}))

    def test_static_root_supports_source_and_frozen_layouts(self):
        module_file = Path("C:/project/yuanjian_app/http_api.py")
        self.assertEqual(resolve_static_root(module_file), module_file.parent / "static")
        self.assertEqual(
            resolve_static_root(module_file, Path("C:/bundle")),
            Path("C:/bundle/yuanjian_app/static"),
        )

    def test_application_uses_ephemeral_loopback_port_and_session_token(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            app = Application.create(
                data_root=Path(temp_dir), open_browser=False, legacy_path=None
            )
            try:
                self.assertEqual(app.server.server_address[0], "127.0.0.1")
                self.assertGreater(app.server.server_address[1], 0)
                self.assertGreaterEqual(len(app.session_token), 32)
                self.assertTrue((Path(temp_dir) / "data" / "yuanjian.db").is_file())
                self.assertGreaterEqual(len(app.external.list_sources()), 2)
            finally:
                app.close()
            self.assertFalse(app.scheduler.running)


if __name__ == "__main__":
    unittest.main()
