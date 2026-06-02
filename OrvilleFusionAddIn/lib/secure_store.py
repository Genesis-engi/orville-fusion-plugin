"""OS-backed secure storage for the Orville API key."""

from __future__ import annotations

import ctypes
import os
import platform
import subprocess
from ctypes import wintypes

ENV_API_KEY = "ORVILLE_API_KEY"
SERVICE_NAME = "Orville Fusion Plugin"
ACCOUNT_NAME = "api_key"


class SecureStoreUnavailable(RuntimeError):
    """Raised when no supported OS credential store is available."""


class SecureStore:
    def __init__(self, service: str = SERVICE_NAME, account: str = ACCOUNT_NAME) -> None:
        self.service = service
        self.account = account

    def get_api_key(self) -> str | None:
        env_key = normalize_api_key(os.environ.get(ENV_API_KEY))
        if env_key:
            return env_key

        system = platform.system()
        if system == "Windows":
            return self._windows_read()
        if system == "Darwin":
            return self._macos_read()
        raise SecureStoreUnavailable("Secure API key storage is supported on Windows and macOS.")

    def set_api_key(self, api_key: str) -> None:
        normalized = normalize_api_key(api_key)
        if not normalized:
            raise ValueError("API key is required.")

        system = platform.system()
        if system == "Windows":
            self._windows_write(normalized)
            return
        if system == "Darwin":
            self._macos_write(normalized)
            return
        raise SecureStoreUnavailable("Secure API key storage is supported on Windows and macOS.")

    def delete_api_key(self) -> None:
        system = platform.system()
        if system == "Windows":
            self._windows_delete()
            return
        if system == "Darwin":
            self._macos_delete()
            return
        raise SecureStoreUnavailable("Secure API key storage is supported on Windows and macOS.")

    @property
    def _target(self) -> str:
        return f"{self.service}:{self.account}"

    def _macos_read(self) -> str | None:
        result = subprocess.run(
            ["/usr/bin/security", "find-generic-password", "-s", self.service, "-a", self.account, "-w"],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        return normalize_api_key(result.stdout)

    def _macos_write(self, api_key: str) -> None:
        result = subprocess.run(
            [
                "/usr/bin/security",
                "add-generic-password",
                "-U",
                "-s",
                self.service,
                "-a",
                self.account,
                "-w",
                api_key,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise SecureStoreUnavailable(result.stderr.strip() or "macOS Keychain write failed.")

    def _macos_delete(self) -> None:
        subprocess.run(
            ["/usr/bin/security", "delete-generic-password", "-s", self.service, "-a", self.account],
            check=False,
            capture_output=True,
            text=True,
        )

    def _windows_read(self) -> str | None:
        credential_ptr = ctypes.POINTER(CREDENTIALW)()
        if not advapi32.CredReadW(self._target, CRED_TYPE_GENERIC, 0, ctypes.byref(credential_ptr)):
            return None
        try:
            credential = credential_ptr.contents
            if not credential.CredentialBlob or credential.CredentialBlobSize == 0:
                return None
            blob = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
            return normalize_api_key(blob.decode("utf-16-le"))
        finally:
            advapi32.CredFree(credential_ptr)

    def _windows_write(self, api_key: str) -> None:
        blob = api_key.encode("utf-16-le")
        blob_buffer = ctypes.create_string_buffer(blob)
        credential = CREDENTIALW()
        credential.Type = CRED_TYPE_GENERIC
        credential.TargetName = self._target
        credential.CredentialBlobSize = len(blob)
        credential.CredentialBlob = ctypes.cast(blob_buffer, ctypes.POINTER(wintypes.BYTE))
        credential.Persist = CRED_PERSIST_LOCAL_MACHINE
        credential.UserName = self.account
        if not advapi32.CredWriteW(ctypes.byref(credential), 0):
            raise ctypes.WinError()

    def _windows_delete(self) -> None:
        advapi32.CredDeleteW(self._target, CRED_TYPE_GENERIC, 0)


def normalize_api_key(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if any(ord(ch) < 32 for ch in stripped):
        raise ValueError("API key contains invalid control characters.")
    return stripped


class FILETIME(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", wintypes.DWORD),
        ("dwHighDateTime", wintypes.DWORD),
    ]


class CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(wintypes.BYTE)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2

if platform.system() == "Windows":
    advapi32 = ctypes.windll.advapi32
    advapi32.CredReadW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(CREDENTIALW)),
    ]
    advapi32.CredReadW.restype = wintypes.BOOL
    advapi32.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIALW), wintypes.DWORD]
    advapi32.CredWriteW.restype = wintypes.BOOL
    advapi32.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    advapi32.CredDeleteW.restype = wintypes.BOOL
    advapi32.CredFree.argtypes = [ctypes.c_void_p]
    advapi32.CredFree.restype = None
else:
    advapi32 = None
