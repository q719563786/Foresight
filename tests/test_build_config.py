import unittest
from pathlib import Path


class BuildConfigTests(unittest.TestCase):
    def test_windows_powershell_build_script_is_ascii_safe(self):
        project = Path(__file__).resolve().parents[1]
        script = (project / "build" / "build_windows.ps1").read_text(encoding="utf-8")
        script.encode("ascii")
        spec = (project / "build" / "yuanjian.spec").read_text(encoding="utf-8")
        self.assertIn('name="YuanJian"', spec)

    def test_packaged_smoke_script_does_not_shadow_home(self):
        project = Path(__file__).resolve().parents[1]
        script = (project / "tools" / "smoke_packaged.ps1").read_text(encoding="utf-8")
        self.assertNotRegex(script, r"(?i)\$home\b")


if __name__ == "__main__":
    unittest.main()
