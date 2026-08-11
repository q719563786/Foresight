"""Desktop lifecycle rules that do not depend on GUI libraries."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class DesktopLifecycle:
    """Coordinate one window, one tray icon, and safe application shutdown."""

    def __init__(
        self,
        window: Any,
        tray: Any,
        monitor: Any,
        run_cognition: Callable[[], dict],
        request_shutdown: Callable[[], None],
    ) -> None:
        self.window = window
        self.tray = tray
        self.monitor = monitor
        self._run_cognition = run_cognition
        self._request_shutdown = request_shutdown
        self.exiting = False

    def close_to_tray(self) -> bool:
        """Hide a normal close, but allow destruction during a real exit."""
        if self.exiting:
            return True
        self.window.hide()
        return False

    def show_window(self) -> None:
        self.window.show()
        self.window.restore()

    def run_cognition_once(self) -> dict:
        return self._run_cognition()

    def toggle_monitoring(self) -> bool:
        """Toggle automatic monitoring and return whether it is now running."""
        if self.monitor.paused:
            self.monitor.resume()
            return True
        self.monitor.pause()
        return False

    def request_exit(self) -> None:
        if self.exiting:
            return
        self.exiting = True
        self.tray.stop()
        self._request_shutdown()
