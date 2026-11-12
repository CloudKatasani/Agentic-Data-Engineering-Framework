"""Persistent platform settings: providers, per-agent model bindings, Jira, stacks.

Settings never contain secret values, only references to the secret vault.
"""
from __future__ import annotations

import copy
import json
import threading
from pathlib import Path
from typing import Any

from .config import adpe_home

AGENT_NAMES = [
    "adpe-orchestrator", "adpe-intent-requirements", "adpe-source-target-mapping",
    "adpe-solution-design", "adpe-pipeline-build", "adpe-test-quality",
    "adpe-release-deploy", "adpe-operations-observability", "adpe-data-consumption",
]

DEFAULTS: dict[str, Any] = {
    "providers": [
        {"id": "demo", "type": "simulator", "label": "ADPE Demo Simulator (offline)",
         "base_url": "", "api_key_ref": "", "options": {}},
    ],
    "agents": {name: {"provider_id": "demo", "model": "adpe-simulator-1", "effort": "medium",
                      "max_tokens": 16000} for name in AGENT_NAMES},
    "jira": {"mode": "demo", "base_url": "", "deployment": "cloud", "email": "",
             "token_ref": "", "default_jql": "project = DATA AND issuetype in (Story, Epic) ORDER BY key"},
    "stack_profiles": [],
    "approver_defaults": {
        "product_owner": "Demo Presenter", "data_architect": "Demo Presenter",
        "data_steward": "Demo Presenter", "tech_lead": "Demo Presenter",
        "release_manager": "Demo Presenter", "platform_owner": "Demo Presenter",
        "security_compliance": "Demo Presenter",
    },
}

_lock = threading.Lock()


class SettingsStore:
    def __init__(self, home: Path | None = None):
        self.path = (home or adpe_home()) / "settings.json"

    def load(self) -> dict:
        data = copy.deepcopy(DEFAULTS)
        if self.path.exists():
            saved = json.loads(self.path.read_text())
            for k, v in saved.items():
                if isinstance(v, dict) and isinstance(data.get(k), dict):
                    data[k].update(v)
                else:
                    data[k] = v
        if not any(p["id"] == "demo" for p in data["providers"]):
            data["providers"].insert(0, copy.deepcopy(DEFAULTS["providers"][0]))
        for name in AGENT_NAMES:
            data["agents"].setdefault(name, copy.deepcopy(DEFAULTS["agents"][name]))
        return data

    def save(self, data: dict) -> dict:
        with _lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2))
            tmp.replace(self.path)
        return data

    def update(self, key: str, value: Any) -> dict:
        data = self.load()
        data[key] = value
        return self.save(data)

    def provider(self, provider_id: str) -> dict | None:
        return next((p for p in self.load()["providers"] if p["id"] == provider_id), None)
