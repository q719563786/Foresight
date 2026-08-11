"""Current-user Windows Startup-folder management.

This deliberately avoids Task Scheduler: creating logon tasks can require
administrator privileges on supported Windows installations.  A per-user
Startup shortcut is sufficient and keeps installation reversible.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


TASK_NAME = "YuanJian"


def _default_startup_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


class StartupTask:
    def __init__(self, task_name=TASK_NAME, startup_dir=None, executable=None):
        self.task_name = str(task_name)
        if not self.task_name or any(character in self.task_name for character in '<>:"/\\|?*'):
            raise ValueError("invalid startup task name")
        self.startup_dir = Path(startup_dir) if startup_dir is not None else _default_startup_dir()
        self.executable = None if executable is None else Path(executable)

    @property
    def path(self) -> Path:
        return self.startup_dir / f"{self.task_name}.vbs"

    def install(self, executable: Path = None) -> dict:
        executable = Path(executable or self.executable or "").resolve()
        if not executable.is_file():
            raise FileNotFoundError(executable)

        escaped = str(executable).replace('"', '""')
        content = (
            'Set shell = CreateObject("WScript.Shell")\n'
            'shell.Environment("Process")("YUANJIAN_BACKGROUND") = "1"\n'
            f'shell.Run Chr(34) & "{escaped}" & Chr(34) & " --background", 0, False\n'
        )

        self.startup_dir.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8-sig",
                newline="\r\n",
                prefix=f".{self.task_name}-",
                suffix=".tmp",
                dir=self.startup_dir,
                delete=False,
            ) as handle:
                handle.write(content)
                temporary_path = Path(handle.name)
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

        return {"installed": self.path.is_file(), "message": str(self.path)}

    def status(self) -> dict:
        installed = self.path.is_file()
        return {"installed": installed, "message": str(self.path)}

    def remove(self) -> dict:
        if self.path.exists():
            self.path.unlink()
        return {"removed": not self.path.exists(), "message": str(self.path)}
