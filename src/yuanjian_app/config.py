from dataclasses import dataclass
from os import environ
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    root: Path
    database: Path
    logs: Path
    backups: Path
    cache: Path

    @classmethod
    def from_environment(cls, env):
        """Resolve private runtime paths without placing data beside source code."""
        configured = env.get("YUANJIAN_DATA_DIR")
        if configured:
            root = Path(configured).expanduser().resolve()
        else:
            local_app_data = env.get("LOCALAPPDATA") or environ.get("LOCALAPPDATA")
            if not local_app_data:
                raise RuntimeError("无法确定Windows本地数据目录")
            root = (Path(local_app_data) / "YuanJian").resolve()
        return cls(
            root=root,
            database=root / "data" / "yuanjian.db",
            logs=root / "logs",
            backups=root / "backups",
            cache=root / "cache",
        )

    def ensure_directories(self):
        """Create runtime directories while leaving application source untouched."""
        for directory in (self.database.parent, self.logs, self.backups, self.cache):
            directory.mkdir(parents=True, exist_ok=True)
