import tempfile
import unittest
from pathlib import Path

from yuanjian_app.startup import StartupTask


class StartupTaskTests(unittest.TestCase):
    def test_install_uses_current_user_startup_folder_and_hidden_background(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "Program Files" / "YuanJian.exe"
            executable.parent.mkdir()
            executable.touch()
            task = StartupTask(startup_dir=root / "Startup", executable=executable)

            result = task.install()

            self.assertTrue(result["installed"])
            startup_file = root / "Startup" / "YuanJian.vbs"
            content = startup_file.read_text(encoding="utf-8-sig")
            self.assertIn("YUANJIAN_BACKGROUND", content)
            self.assertIn("--background", content)
            self.assertIn(str(executable.resolve()), content)
            self.assertIn(", 0, False", content)
            self.assertNotIn("password", content.casefold())

    def test_status_and_remove_only_touch_injected_startup_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "YuanJian.exe"
            executable.touch()
            task = StartupTask(startup_dir=root / "Startup", executable=executable)

            self.assertFalse(task.status()["installed"])
            task.install()
            self.assertTrue(task.status()["installed"])
            self.assertTrue(task.remove()["removed"])
            self.assertFalse(task.status()["installed"])


if __name__ == "__main__":
    unittest.main()
