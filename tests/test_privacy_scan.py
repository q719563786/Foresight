import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from privacy_scan import scan_tree


class PrivacyScanTests(unittest.TestCase):
    def test_scanner_blocks_private_database_artifact(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "forecast.db").write_bytes(b"private")

            report = scan_tree(root)

            self.assertFalse(report.safe)
            self.assertEqual(report.blocked_files, ["forecast.db"])

    def test_scanner_accepts_sanitized_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "README.md").write_text("虚构示例数据", encoding="utf-8")

            report = scan_tree(root)

            self.assertTrue(report.safe)


if __name__ == "__main__":
    unittest.main()
