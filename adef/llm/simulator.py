"""Offline demo simulator. Stage agents check `provider.type == "simulator"` and use
their deterministic generators instead of free text; this class only answers the
connectivity test and generic narrative requests."""
from __future__ import annotations

from .base import LLMResult, Provider


class SimulatorProvider(Provider):
    type = "simulator"

    def complete(self, *, system, prompt, model, max_tokens=16000, effort="medium", context=None) -> LLMResult:
        text = "ready" if "single word: ready" in prompt else "(simulated narrative)"
        return LLMResult(text=text, model=model, provider="simulator",
                         input_tokens=len(system + prompt) // 4, output_tokens=len(text) // 4)

    def list_models(self) -> list[str]:
        return ["adef-simulator-1"]
