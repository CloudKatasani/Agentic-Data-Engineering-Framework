"""Resolve the provider and model bound to each agent."""
from __future__ import annotations

from ..catalog.providers import price_for
from ..secrets_store import SecretNotFound, SecretStore
from ..settings_store import SettingsStore
from .anthropic_provider import AnthropicProvider
from .base import LLMError, Provider
from .http_providers import (AzureOpenAIProvider, BedrockProvider, GeminiProvider, OpenAICompatibleProvider,
                             OpenAIProvider)
from .simulator import SimulatorProvider

CLASSES: dict[str, type[Provider]] = {
    "simulator": SimulatorProvider, "anthropic": AnthropicProvider, "openai": OpenAIProvider,
    "azure_openai": AzureOpenAIProvider, "google_gemini": GeminiProvider, "aws_bedrock": BedrockProvider,
    "openai_compatible": OpenAICompatibleProvider,
}


def build_provider(cfg: dict, secrets: SecretStore | None = None) -> Provider:
    cls = CLASSES.get(cfg["type"])
    if not cls:
        raise LLMError(f"Unknown provider type {cfg['type']}")
    key = None
    if cfg.get("api_key_ref"):
        try:
            key = (secrets or SecretStore()).resolve(cfg["api_key_ref"])
        except SecretNotFound as e:
            raise LLMError(f"API key reference `{cfg['api_key_ref']}` not found in the vault") from e
    return cls(cfg, key)


def binding_for(agent: str, settings: dict | None = None, override: dict | None = None) -> dict:
    """The provider and model for an agent: the saved team binding, or a per-run override chosen at launch."""
    settings = settings or SettingsStore().load()
    b = dict(settings["agents"].get(agent) or {})
    b.update({k: v for k, v in (override or {}).items() if k in ("provider_id", "model", "effort", "max_tokens") and v})
    prov = next((p for p in settings["providers"] if p["id"] == b.get("provider_id")), None)
    if not prov:
        prov = next(p for p in settings["providers"] if p["id"] == "demo")
        b.update(provider_id="demo", model="adef-simulator-1")
    b["provider"] = prov
    return b


def provider_for(agent: str, settings: dict | None = None) -> tuple[Provider, dict]:
    b = binding_for(agent, settings)
    return build_provider(b["provider"]), b


def estimate_cost(provider_type: str, model: str, tin: int, tout: int) -> float | None:
    p = price_for(provider_type, model)
    if not p:
        return None
    return round(tin / 1e6 * p[0] + tout / 1e6 * p[1], 4)
