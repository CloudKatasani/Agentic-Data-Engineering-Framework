from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LLMResult:
    text: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    meta: dict = field(default_factory=dict)


class LLMError(Exception):
    pass


class Provider:
    """One configured provider. `config` is the settings entry; `api_key` is resolved
    from the vault at call time and never logged or returned."""

    type = "base"

    def __init__(self, config: dict, api_key: str | None):
        self.config = config
        self.api_key = api_key
        self.options = config.get("options") or {}
        self.base_url = (config.get("base_url") or "").rstrip("/")

    def complete(self, *, system: str, prompt: str, model: str, max_tokens: int = 16000,
                 effort: str = "medium", context: dict | None = None) -> LLMResult:
        raise NotImplementedError

    def list_models(self) -> list[str]:
        return []

    def test(self, model: str) -> LLMResult:
        return self.complete(system="You are a connectivity check.", prompt="Reply with the single word: ready",
                             model=model, max_tokens=64, effort="low")
