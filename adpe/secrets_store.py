"""Encrypted secret vault.

Secrets (LLM API keys, Jira tokens) are stored encrypted at rest and referenced by
name everywhere else ("secret:anthropic-prod"). Values are never returned by the API,
never written to run workspaces, and never sent to a model. This implements the
guardrail "credentials come only from the configured secrets manager by reference".

Key source, in order: ADPE_MASTER_KEY env var (Fernet key), else a key file generated
at ADPE_HOME/master.key with 0600 permissions. In production point ADPE_MASTER_KEY at
your cloud secret manager, or replace this class with a cloud secret manager adapter.

References may also be "env:VAR_NAME" to read from the process environment.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from .config import adpe_home
from .util import now_iso

_lock = threading.Lock()


class SecretNotFound(KeyError):
    pass


class SecretStore:
    def __init__(self, home: Path | None = None):
        self.home = home or adpe_home()
        self.path = self.home / "secrets.enc.json"
        self._fernet = Fernet(self._load_key())

    def _load_key(self) -> bytes:
        env = os.environ.get("ADPE_MASTER_KEY")
        if env:
            return env.encode()
        key_file = self.home / "master.key"
        if not key_file.exists():
            key_file.write_bytes(Fernet.generate_key())
            os.chmod(key_file, 0o600)
        return key_file.read_bytes().strip()

    def _read(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text())

    def _write(self, data: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        os.chmod(tmp, 0o600)
        tmp.replace(self.path)

    def put(self, name: str, value: str, description: str = "") -> dict:
        name = name.strip()
        if not name or any(c in name for c in " /\\:"):
            raise ValueError("secret name must be non-empty with no spaces, slashes or colons")
        if not value:
            raise ValueError("secret value is empty")
        with _lock:
            data = self._read()
            data[name] = {
                "ciphertext": self._fernet.encrypt(value.encode()).decode(),
                "hint": ("••••" + value[-4:]) if len(value) >= 12 else "••••",
                "description": description,
                "updated": now_iso(),
            }
            self._write(data)
        return self.describe(name)

    def delete(self, name: str) -> None:
        with _lock:
            data = self._read()
            data.pop(name, None)
            self._write(data)

    def describe(self, name: str) -> dict:
        item = self._read().get(name)
        if not item:
            raise SecretNotFound(name)
        return {"name": name, "hint": item["hint"], "description": item.get("description", ""),
                "updated": item["updated"]}

    def list(self) -> list[dict]:
        return [self.describe(n) for n in sorted(self._read())]

    def resolve(self, ref: str | None) -> str | None:
        """Resolve 'secret:name', 'env:VAR' or a bare vault name. Tool-level only."""
        if not ref:
            return None
        if ref.startswith("env:"):
            v = os.environ.get(ref[4:])
            if v is None:
                raise SecretNotFound(ref)
            return v
        name = ref[7:] if ref.startswith("secret:") else ref
        item = self._read().get(name)
        if not item:
            raise SecretNotFound(ref)
        try:
            return self._fernet.decrypt(item["ciphertext"].encode()).decode()
        except InvalidToken as e:
            raise SecretNotFound(f"{ref} (cannot decrypt: master key changed?)") from e
