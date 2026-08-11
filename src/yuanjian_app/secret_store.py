"""Current-user encrypted secret storage for Windows."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path


_HEADER = b"YJDP1\x00"


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.c_uint32),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _blob(data: bytes):
    buffer = ctypes.create_string_buffer(data)
    value = _DataBlob(
        len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
    )
    return value, buffer


def _dpapi_protect(data: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("DPAPI只在Windows可用")
    source, source_buffer = _blob(data)
    output = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    success = crypt32.CryptProtectData(
        ctypes.byref(source),
        "YuanJian AI token",
        None,
        None,
        None,
        0x1,
        ctypes.byref(output),
    )
    del source_buffer
    if not success:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel32.LocalFree(output.pbData)


def _dpapi_unprotect(data: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("DPAPI只在Windows可用")
    source, source_buffer = _blob(data)
    output = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    success = crypt32.CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, 0x1, ctypes.byref(output)
    )
    del source_buffer
    if not success:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel32.LocalFree(output.pbData)


class DpapiSecretStore:
    def __init__(self, path: Path, protect=None, unprotect=None):
        self.path = Path(path)
        self.protect = protect or _dpapi_protect
        self.unprotect = unprotect or _dpapi_unprotect

    def save(self, token: str):
        value = str(token or "").strip()
        if not value:
            self.clear()
            return
        encrypted = self.protect(value.encode("utf-8"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_bytes(_HEADER + encrypted)
        os.replace(temporary, self.path)

    def load(self) -> str:
        if not self.path.exists():
            return ""
        payload = self.path.read_bytes()
        if not payload.startswith(_HEADER):
            raise ValueError("密钥文件格式无效")
        return self.unprotect(payload[len(_HEADER) :]).decode("utf-8")

    def clear(self):
        self.path.unlink(missing_ok=True)
