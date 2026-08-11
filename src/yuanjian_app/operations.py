"""Synchronization for user-visible long-running operations."""

from __future__ import annotations

import threading
import time


class OperationBusy(RuntimeError):
    """Raised when a second cognition run overlaps an active run."""


class CognitionOperation:
    """Allow only one cognition pass across every application entry point."""

    def __init__(self, controller) -> None:
        self.controller = controller
        self._lock = threading.Lock()

    def run(self, source: str = "manual") -> dict:
        if not self._lock.acquire(blocking=False):
            raise OperationBusy("认知任务正在运行")
        started = time.monotonic()
        try:
            result = self.controller.process_once()
            return {
                **result,
                "source": source,
                "elapsed_ms": round((time.monotonic() - started) * 1000),
            }
        finally:
            self._lock.release()
