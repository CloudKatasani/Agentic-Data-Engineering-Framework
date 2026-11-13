"""Claude via the official Anthropic Python SDK.

Streams every request (long agent outputs) and reads the final message. Adaptive
thinking is the default on current models, so depth is set with output_config.effort.
Refusal fallbacks are enabled server-side for the models that support them.
"""
from __future__ import annotations

import anthropic

from .base import LLMError, LLMResult, Provider

FALLBACK_MODELS = {"claude-fable-5-2", "claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}
EFFORT_MODELS_PREFIX = ("claude-fable-5", "claude-mythos-5", "claude-opus-5", "claude-opus-4-8", "claude-opus-4-7",
                        "claude-opus-4-6", "claude-sonnet-5", "claude-sonnet-4-6", "claude-haiku-5")


class AnthropicProvider(Provider):
    type = "anthropic"

    def _client(self) -> anthropic.Anthropic:
        if not self.api_key:
            raise LLMError("No API key configured for this Anthropic provider")
        kw = {"api_key": self.api_key, "max_retries": 3}
        if self.base_url:
            kw["base_url"] = self.base_url
        return anthropic.Anthropic(**kw)

    def complete(self, *, system, prompt, model, max_tokens=16000, effort="medium", context=None) -> LLMResult:
        client = self._client()
        kw: dict = {"model": model, "max_tokens": max_tokens, "system": system,
                    "messages": [{"role": "user", "content": prompt}]}
        if model.startswith(EFFORT_MODELS_PREFIX) and effort:
            # Opus 4.6 and Sonnet 4.6 have no xhigh level
            kw["output_config"] = {"effort": "high" if effort == "xhigh" and model.endswith("-4-6") else effort}
        if model in FALLBACK_MODELS:
            kw["betas"] = ["server-side-fallback-2026-07-01"]
            kw["fallbacks"] = "default"
        try:
            with client.beta.messages.stream(**kw) as stream:
                msg = stream.get_final_message()
        except anthropic.AuthenticationError as e:
            raise LLMError("Anthropic rejected the API key (401)") from e
        except anthropic.NotFoundError as e:
            raise LLMError(f"Model `{model}` not found or not available to this key") from e
        except anthropic.RateLimitError as e:
            raise LLMError("Anthropic rate limit hit; retry later") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"Anthropic API error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise LLMError("Cannot reach the Anthropic API (network)") from e
        if msg.stop_reason == "refusal":
            cat = getattr(getattr(msg, "stop_details", None), "category", None)
            raise LLMError(f"Model declined the request (refusal, category={cat})")
        text = "".join(b.text for b in msg.content if b.type == "text")
        return LLMResult(text=text, model=msg.model, provider="anthropic",
                         input_tokens=msg.usage.input_tokens, output_tokens=msg.usage.output_tokens,
                         meta={"stop_reason": msg.stop_reason, "request_id": getattr(msg, "_request_id", None)})

    def list_models(self) -> list[str]:
        try:
            return [m.id for m in self._client().models.list()]
        except anthropic.APIError as e:
            raise LLMError(f"Cannot list models: {e}") from e
