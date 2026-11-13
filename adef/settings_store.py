"""Persistent platform settings: providers, per-agent model bindings, Jira, stacks.

Settings never contain secret values, only references to the secret vault.
"""
from __future__ import annotations

import copy
import json
import threading
from pathlib import Path
from typing import Any

from .catalog.providers import ENV_KEYS, SEED_PROVIDERS, TEAM_PRESETS, env_key_for, preset_for_env
from .config import adef_home

AGENT_NAMES = [
    "adef-orchestrator", "adef-intent-requirements", "adef-source-target-mapping",
    "adef-solution-design", "adef-pipeline-build", "adef-test-quality",
    "adef-release-deploy", "adef-operations-observability", "adef-data-consumption",
]

DEFAULTS: dict[str, Any] = {
    "providers": copy.deepcopy(SEED_PROVIDERS),
    "agents": copy.deepcopy(TEAM_PRESETS["multi-vendor"]["agents"]),
    "runtime": {"simulate_unavailable_providers": True, "team_preset": "multi-vendor"},
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
        self.path = (home or adef_home()) / "settings.json"

    def load(self) -> dict:
        data = copy.deepcopy(DEFAULTS)
        if not self.path.exists():  # fresh install: choose the agent team from the keys in the environment
            name = preset_for_env()
            data["agents"] = copy.deepcopy(TEAM_PRESETS[name]["agents"])
            data["runtime"]["team_preset"] = name
        if self.path.exists():
            saved = json.loads(self.path.read_text())
            # settings written before the ADPE -> ADEF rename keyed agents as adpe-*
            if isinstance(saved.get("agents"), dict):
                saved["agents"] = {("adef-" + k[5:] if k.startswith("adpe-") else k): v for k, v in saved["agents"].items()}
            for k, v in saved.items():
                if isinstance(v, dict) and isinstance(data.get(k), dict):
                    data[k].update(v)
                else:
                    data[k] = v
        if not any(p["id"] == "demo" for p in data["providers"]):
            data["providers"].insert(0, copy.deepcopy(DEFAULTS["providers"][0]))
        for name in AGENT_NAMES:
            data["agents"].setdefault(name, copy.deepcopy(DEFAULTS["agents"][name]))
        # make sure every provider referenced by an agent exists (older settings files)
        have = {p["id"] for p in data["providers"]}
        for seed in SEED_PROVIDERS:
            if seed["id"] not in have and any(b.get("provider_id") == seed["id"] for b in data["agents"].values()):
                data["providers"].append(copy.deepcopy(seed))
        return self._apply_env(data)

    @staticmethod
    def _apply_env(data: dict) -> dict:
        """Reference provider keys found in the environment (in memory only; never written to disk)."""
        import os
        for p in data["providers"]:
            spec = ENV_KEYS.get(p["id"], {})
            var = env_key_for(p["id"])
            if var and not p.get("api_key_ref"):
                p["api_key_ref"] = f"env:{var}"
                p["key_source"] = "environment"
            if spec.get("base_url") and os.environ.get(spec["base_url"]) and not p.get("base_url_locked"):
                p["base_url"] = os.environ[spec["base_url"]]
            if spec.get("region") and os.environ.get(spec["region"]):
                p.setdefault("options", {})["region"] = os.environ[spec["region"]]
        return data

    def save(self, data: dict) -> dict:
        disk = copy.deepcopy(data)
        for p in disk.get("providers", []):  # environment-derived references are not persisted
            if p.pop("key_source", None) == "environment":
                p["api_key_ref"] = ""
        with _lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(disk, indent=2))
            tmp.replace(self.path)
        return self._apply_env(disk)

    def update(self, key: str, value: Any) -> dict:
        data = self.load()
        data[key] = value
        return self.save(data)

    def provider(self, provider_id: str) -> dict | None:
        return next((p for p in self.load()["providers"] if p["id"] == provider_id), None)
