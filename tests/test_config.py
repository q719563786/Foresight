import tempfile
import unittest
from pathlib import Path

from yuanjian_app.config import AppPaths


class AppPathsTests(unittest.TestCase):
    def test_environment_override_keeps_runtime_data_outside_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            private = Path(temp_dir) / "private"

            paths = AppPaths.from_environment({"YUANJIAN_DATA_DIR": str(private)})
            paths.ensure_directories()

            self.assertEqual(paths.database, private / "data" / "yuanjian.db")
            self.assertEqual(paths.logs, private / "logs")
            self.assertTrue(paths.database.parent.is_dir())


if __name__ == "__main__":
    unittest.main()
