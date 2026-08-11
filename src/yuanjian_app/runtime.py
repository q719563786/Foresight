"""Single-instance locking and local runtime discovery."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request


_HELD_PATHS = set()
_HELD_GUARD = threading.Lock()


class RuntimeClient:
    """Send authenticated loopback commands to an existing YuanJian instance."""

    def __init__(self, runtime, opener=urllib_request.urlopen):
        self.runtime = runtime
        self.opener = opener

    def show_window(self) -> bool:
        try:
            port = self.runtime["port"]
            token = self.runtime["token"]
            if (
                isinstance(port, bool)
                or not isinstance(port, int)
                or not 1 <= port <= 65535
                or not isinstance(token, str)
                or not token
            ):
                return False
            request = urllib_request.Request(
                f"http://127.0.0.1:{port}/api/window/show",
                data=b"{}",
                headers={
                    "Content-Type": "application/json",
                    "X-YuanJian-Token": token,
                },
                method="POST",
            )
            with self.opener(request, timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return response.status == 200 and payload.get("status") == "shown"
        except (
            KeyError,
            TypeError,
            ValueError,
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            urllib_error.URLError,
        ):
            return False


class SingleInstance:
    def __init__(self, lock_path: Path):
        self.lock_path = Path(lock_path).resolve()
        self.handle = None

    def acquire(self) -> bool:
        if self.handle is not None:
            return True
        key = str(self.lock_path).casefold()
        with _HELD_GUARD:
            if key in _HELD_PATHS:
                return False
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            handle = self.lock_path.open("a+b")
            if self.lock_path.stat().st_size == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (OSError, BlockingIOError):
                handle.close()
                return False
            _HELD_PATHS.add(key)
            self.handle = handle
            return True

    def release(self):
        if self.handle is None:
            return
        key = str(self.lock_path).casefold()
        try:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None
            with _HELD_GUARD:
                _HELD_PATHS.discard(key)

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError("远见已有实例正在运行")
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.release()


def _process_exists(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        still_active = 259
        error_access_denied = 5
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        )
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, wintypes.LPDWORD)
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL

        handle = kernel32.OpenProcess(
            process_query_limited_information, False, pid
        )
        if not handle:
            return ctypes.get_last_error() == error_access_denied
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


class RuntimeDiscovery:
    REQUIRED = {"pid", "port", "token", "started_at"}

    def __init__(self, path: Path, process_exists=None):
        self.path = Path(path)
        self.process_exists = process_exists or _process_exists

    def publish(self, pid, port, token, started_at):
        state = {
            "pid": int(pid),
            "port": int(port),
            "token": str(token),
            "started_at": str(started_at),
        }
        if state["pid"] <= 0 or not 1 <= state["port"] <= 65535 or not state["token"]:
            raise ValueError("运行状态无效")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(state, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
        os.replace(temporary, self.path)
        return state

    def read_valid(self):
        if not self.path.exists():
            return None
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
            valid = (
                isinstance(state, dict)
                and set(state) == self.REQUIRED
                and isinstance(state["pid"], int)
                and isinstance(state["port"], int)
                and 1 <= state["port"] <= 65535
                and isinstance(state["token"], str)
                and bool(state["token"])
                and isinstance(state["started_at"], str)
                and self.process_exists(state["pid"])
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
            valid = False
            state = None
        if not valid:
            self.clear()
            return None
        return state

    def clear(self):
        self.path.unlink(missing_ok=True)
