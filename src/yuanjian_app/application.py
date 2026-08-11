import os
import secrets
import sys
import webbrowser
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path

from .config import AppPaths
from .cognition import CognitionController, CognitionService
from .database import Database
from .forecasts import ForecastService
from .external_radar import ExternalRadarService
from .http_api import Services, create_server
from .interests import InterestService
from .knowledge import KnowledgeService
from .impacts import ImpactService
from .judgments import LocalHeuristicProvider, build_public_bundle
from .notifications import NotificationService
from .remote_ai import AiSettingsService, JudgmentQueue
from .secret_store import DpapiSecretStore
from .signals import SignalService
from .radar_scheduler import RadarScheduler
from .runtime import RuntimeDiscovery, SingleInstance
from .startup import StartupTask
from .trends import TrendService


@dataclass
class Application:
    server: object
    session_token: str
    open_browser: bool
    external: object
    scheduler: object

    @classmethod
    def create(cls, data_root, open_browser=True, legacy_path=None):
        """Build an application without starting its blocking serve loop."""
        root = Path(data_root)
        database = Database(root / "data" / "yuanjian.db")
        if legacy_path is not None and Path(legacy_path).is_file() and not database.path.exists():
            database.import_legacy(legacy_path)
        else:
            database.initialize()
        session_token = secrets.token_urlsafe(32)
        interests = InterestService(database)
        interests.ensure_defaults()
        signals = SignalService(database, interests)
        knowledge = KnowledgeService(database)
        cognition = CognitionService(database)
        external = ExternalRadarService(
            database, on_item_stored=cognition.process_item
        )
        external.ensure_public_defaults()
        trends = TrendService(database)
        local_provider = LocalHeuristicProvider()
        ai_settings = AiSettingsService(
            database, DpapiSecretStore(root / "secrets" / "ai-token.dpapi")
        )
        queue = JudgmentQueue(
            database,
            providers={"local": local_provider},
            bundle_loader=lambda cluster_id: build_public_bundle(
                cognition.get_cluster(cluster_id),
                cognition.get_cluster(cluster_id)["items"],
            ),
            local_provider=local_provider,
        )
        forecasts = ForecastService(database)
        impacts = ImpactService(database, interests, forecasts)
        notifications = NotificationService(database)
        controller = CognitionController(
            database,
            cognition,
            trends,
            queue,
            impacts,
            notifications,
            ai_settings,
        )
        scheduler = RadarScheduler(
            external, database=database, cognition=controller
        )
        startup = (
            StartupTask(executable=Path(sys.executable))
            if getattr(sys, "frozen", False)
            else None
        )
        server = create_server(
            "127.0.0.1",
            0,
            session_token,
            Services(
                forecasts,
                interests,
                signals,
                knowledge,
                external,
                cognition,
                trends,
                controller,
                notifications,
                impacts,
                startup,
                ai_settings,
            ),
        )
        return cls(
            server=server,
            session_token=session_token,
            open_browser=open_browser,
            external=external,
            scheduler=scheduler,
        )

    @property
    def url(self):
        """Return the tokenized local URL opened for this process only."""
        port = self.server.server_address[1]
        return f"http://127.0.0.1:{port}/?token={self.session_token}"

    def run(self):
        """Open the interface and serve until the user closes the process."""
        self.scheduler.start()
        if self.open_browser:
            webbrowser.open(self.url)
        try:
            self.server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            return 0
        finally:
            self.scheduler.stop()
            self.server.server_close()
        return 0

    def close(self):
        """Close a server that has not entered or has left its serve loop."""
        self.scheduler.stop()
        self.server.server_close()


def should_open_browser(env):
    """Disable browser launch only for explicit local automation."""
    return env.get("YUANJIAN_NO_BROWSER") != "1"


def is_background_mode(argv, env):
    return "--background" in set(argv or ()) or env.get("YUANJIAN_BACKGROUND") == "1"


def run_application(open_browser=None, argv=None):
    """Resolve private paths and run the local application."""
    paths = AppPaths.from_environment(os.environ)
    paths.ensure_directories()
    legacy = os.environ.get("YUANJIAN_LEGACY_DB")
    arguments = list(sys.argv[1:] if argv is None else argv)
    background = is_background_mode(arguments, os.environ)
    if open_browser is None:
        open_browser = should_open_browser(os.environ) and not background
    runtime_root = paths.root / "runtime"
    instance = SingleInstance(runtime_root / "yuanjian.lock")
    discovery = RuntimeDiscovery(runtime_root / "runtime.json")
    if not instance.acquire():
        existing = discovery.read_valid()
        if existing and open_browser:
            webbrowser.open(
                f"http://127.0.0.1:{existing['port']}/?token={existing['token']}"
            )
        return 0
    try:
        application = Application.create(paths.root, open_browser, legacy)
        discovery.publish(
            os.getpid(),
            application.server.server_address[1],
            application.session_token,
            datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )
        return application.run()
    finally:
        discovery.clear()
        instance.release()


if __name__ == "__main__":
    raise SystemExit(run_application())
