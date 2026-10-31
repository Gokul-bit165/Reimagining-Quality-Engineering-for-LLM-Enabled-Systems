"""In-memory secret vault for target run-time env vars. Never persisted, never logged."""

from __future__ import annotations

import re
import threading
from typing import Any

MAX_SECRETS = 50
MAX_VALUE_LEN = 4096
_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_DENY_PREFIXES = ("DOCKER_", "QE_", "LD_", "DYLD_", "PYTHON", "BASH_", "SSL", "GIT_", "NODE_",
                  "CURL_", "REQUESTS_", "NPM_", "PIP_", "SSH_")
_DENY_EXACT = frozenset({"PATH", "HOME", "ENV", "IFS", "SHELL", "PS4", "USERPROFILE", "SYSTEMROOT",
                         "TEMP", "TMP", "APPDATA", "LOCALAPPDATA", "COMSPEC", "PATHEXT", "TZ",
                         "WINDIR", "OPENSSL_CONF"})


def is_allowed_name(name: str) -> bool:
    if not _NAME.match(name) or name in _DENY_EXACT or name.endswith("_PROXY"):
        return False
    return not name.startswith(_DENY_PREFIXES)


class SecretError(ValueError):
    pass


class SecretVault:
    def __init__(self) -> None:
        self._data: dict[str, dict[str, str]] = {}
        self._lock = threading.Lock()

    def set(self, project_id: str, values: dict[str, Any]) -> list[str]:
        if len(values) > MAX_SECRETS:
            raise SecretError(f"at most {MAX_SECRETS} secrets")
        for k, v in values.items():
            if not is_allowed_name(k):
                raise SecretError(f"invalid or reserved variable name: {k!r}")
            if not isinstance(v, str) or len(v) > MAX_VALUE_LEN or "\x00" in v:
                raise SecretError(f"invalid value for {k}")
        with self._lock:
            self._data[project_id] = {k: str(v) for k, v in values.items()}
            return sorted(values)

    def names(self, project_id: str) -> list[str]:
        with self._lock:
            return sorted(self._data.get(project_id, {}))

    def get(self, project_id: str) -> dict[str, str]:
        with self._lock:
            return dict(self._data.get(project_id, {}))

    def clear(self, project_id: str) -> None:
        with self._lock:
            self._data.pop(project_id, None)

    def __repr__(self) -> str:
        return "SecretVault(<redacted>)"


VAULT = SecretVault()
