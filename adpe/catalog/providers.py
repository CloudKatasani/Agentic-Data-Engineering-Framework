"""Model provider catalog.

Each provider type lists suggested models. Model lists are suggestions only: every
model field in the UI accepts free text, and "Discover models" queries the provider's
own model-listing endpoint where one exists.

Prices are USD per million tokens (input, output) and are used only for run cost
estimates; null means unknown, so only token counts are reported.
"""
from __future__ import annotations

PROVIDER_TYPES: dict[str, dict] = {
    "simulator": {
        "label": "ADPE Demo Simulator",
        "description": "Deterministic offline agent outputs for demos. No key, no network.",
        "needs_key": False, "needs_base_url": False,
        "models": [{"id": "adpe-simulator-1", "label": "Simulator v1", "price": [0, 0]}],
    },
    "anthropic": {
        "label": "Anthropic (Claude)",
        "description": "Claude models via the Anthropic API (official SDK).",
        "needs_key": True, "needs_base_url": False, "default_base_url": "https://api.anthropic.com",
        "models": [
            {"id": "claude-opus-5-5", "label": "Claude Opus 5.5 (default)", "price": [4.0, 20.0]},
            {"id": "claude-fable-5-2", "label": "Claude Fable 5.2 (most capable)", "price": [8.0, 40.0]},
            {"id": "claude-sonnet-5-5", "label": "Claude Sonnet 5.5", "price": [2.0, 10.0]},
            {"id": "claude-haiku-5-5", "label": "Claude Haiku 5.5", "price": [0.10, 0.50]},
        ],
    },
    "openai": {
        "label": "OpenAI",
        "description": "OpenAI Chat Completions API.",
        "needs_key": True, "needs_base_url": False, "default_base_url": "https://api.openai.com/v1",
        "models": [{"id": "gpt-5", "label": "gpt-5", "price": None},
                   {"id": "gpt-5-mini", "label": "gpt-5-mini", "price": None},
                   {"id": "gpt-4.1", "label": "gpt-4.1", "price": None}],
    },
    "azure_openai": {
        "label": "Azure OpenAI",
        "description": "Azure OpenAI deployment. Model = deployment name; set endpoint and api_version.",
        "needs_key": True, "needs_base_url": True,
        "default_base_url": "https://<resource>.openai.azure.com",
        "options": {"api_version": "2024-10-21"},
        "models": [{"id": "<deployment-name>", "label": "Your deployment name", "price": None}],
    },
    "google_gemini": {
        "label": "Google Gemini",
        "description": "Gemini API (Google AI Studio key).",
        "needs_key": True, "needs_base_url": False,
        "default_base_url": "https://generativelanguage.googleapis.com/v1beta",
        "models": [{"id": "gemini-2.5-pro", "label": "gemini-2.5-pro", "price": None},
                   {"id": "gemini-2.5-flash", "label": "gemini-2.5-flash", "price": None}],
    },
    "aws_bedrock": {
        "label": "Amazon Bedrock",
        "description": "Bedrock Converse API with a Bedrock API key (bearer). Set region in options.",
        "needs_key": True, "needs_base_url": False,
        "options": {"region": "us-east-1"},
        "models": [{"id": "anthropic.claude-opus-5-5", "label": "Claude Opus 5.5 on Bedrock", "price": None},
                   {"id": "anthropic.claude-sonnet-5-5", "label": "Claude Sonnet 5.5 on Bedrock", "price": None}],
    },
    "openai_compatible": {
        "label": "OpenAI-compatible endpoint",
        "description": "Any /chat/completions endpoint: Ollama, vLLM, Mistral, Groq, DeepSeek, Together, LiteLLM, enterprise gateways.",
        "needs_key": False, "needs_base_url": True, "default_base_url": "http://localhost:11434/v1",
        "models": [{"id": "llama3.3", "label": "llama3.3 (Ollama)", "price": None},
                   {"id": "mistral-large-latest", "label": "mistral-large-latest", "price": None}],
    },
}

EFFORT_LEVELS = ["low", "medium", "high", "xhigh", "max"]


def price_for(provider_type: str, model: str) -> list[float] | None:
    for m in PROVIDER_TYPES.get(provider_type, {}).get("models", []):
        if m["id"] == model:
            return m.get("price")
    return None
