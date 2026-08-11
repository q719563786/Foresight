import json
import threading
import time
from datetime import datetime, timezone

from .operations import CognitionOperation


def _iso(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class RadarScheduler:
    """Runs collection and cognition tasks with visible, independent state."""

    def __init__(
        self,
        service,
        poll_seconds=30,
        *,
        database=None,
        cognition=None,
        cognition_operation=None,
        now=lambda: datetime.now(timezone.utc),
    ):
        self.service = service
        self.poll_seconds = float(poll_seconds)
        self.database = database or getattr(service, "database", None)
        self.cognition = cognition
        self.cognition_operation = cognition_operation or (
            CognitionOperation(cognition) if cognition is not None else None
        )
        self.now = now
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._thread = None

    @property
    def running(self):
        return bool(self._thread and self._thread.is_alive())

    @property
    def paused(self):
        return self._paused.is_set()

    def pause(self):
        self._paused.set()

    def resume(self):
        self._paused.clear()

    def run_once(self):
        """Compatibility entry: immediately run only due external sources."""
        if self.paused:
            return 0
        return self.service.refresh_due_sources()

    def _record(self, task, payload):
        if self.database is None:
            return
        updated_at = _iso(self.now())
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO runtime_state(state_key,value_json,updated_at)
                VALUES (?,?,?)
                ON CONFLICT(state_key) DO UPDATE SET
                    value_json=excluded.value_json,updated_at=excluded.updated_at
                """,
                (f"task.{task}", json.dumps(payload, sort_keys=True), updated_at),
            )

    def _execute(self, name, callback):
        started_at = _iso(self.now())
        try:
            result = callback()
        except Exception as error:
            payload = {
                "status": "error",
                "started_at": started_at,
                "finished_at": _iso(self.now()),
                "error_type": type(error).__name__,
            }
            self._record(name, payload)
            return payload
        payload = {
            "status": "ok",
            "started_at": started_at,
            "finished_at": _iso(self.now()),
            "result": result,
        }
        self._record(name, payload)
        return payload

    def run_external_once(self):
        if self.paused:
            return {"status": "paused"}
        return self._execute("external", self.service.refresh_due_sources)

    def run_cognition_once(self):
        if self.paused:
            return {"status": "paused"}
        if self.cognition_operation is None:
            return {"status": "disabled"}
        return self._execute(
            "cognition", lambda: self.cognition_operation.run("scheduled")
        )

    def run_trends_once(self):
        if self.paused:
            return {"status": "paused"}
        if self.cognition is None:
            return {"status": "disabled"}
        return self._execute("trends", self.cognition.capture_trends)

    def _run(self):
        next_external = 0.0
        next_cognition = 0.0
        next_trends = 0.0
        while not self._stop.is_set():
            current = time.monotonic()
            if current >= next_external:
                self.run_external_once()
                next_external = current + self.poll_seconds
            if self.cognition is not None and current >= next_cognition:
                self.run_cognition_once()
                next_cognition = current + 60
            if self.cognition is not None and current >= next_trends:
                self.run_trends_once()
                next_trends = current + 3600
            waits = [next_external - time.monotonic()]
            if self.cognition is not None:
                waits.extend(
                    [next_cognition - time.monotonic(), next_trends - time.monotonic()]
                )
            self._stop.wait(max(0.01, min(max(0.0, value) for value in waits)))

    def start(self):
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="YuanJianCognition", daemon=True
        )
        self._thread.start()

    def stop(self, timeout=5):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=timeout)
