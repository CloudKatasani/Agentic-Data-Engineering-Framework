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
        "label": "ADEF Demo Simulator",
        "description": "Deterministic offline agent outputs for demos. No key, no network.",
        "needs_key": False, "needs_base_url": False,
        "models": [{"id": "adef-simulator-1", "label": "Simulator v1", "price": [0, 0]}],
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
        "models": [{"id": "gpt-5.6-sol", "label": "GPT-5.6 Sol (production)", "price": None},
                   {"id": "gpt-5.6-terra", "label": "GPT-5.6 Terra", "price": None},
                   {"id": "gpt-5.6-luna", "label": "GPT-5.6 Luna", "price": None}],
    },
    "azure_openai": {
        "label": "Azure OpenAI",
        "description": "Azure OpenAI deployment. Model = deployment name; set endpoint and api_version.",
        "needs_key": True, "needs_base_url": True,
        "default_base_url": "https://<resource>.openai.azure.com",
        "options": {"api_version": "2024-10-21"},
        "models": [{"id": "gpt-5-6-terra-prod", "label": "Deployment name (example)", "price": None}],
    },
    "google_gemini": {
        "label": "Google Gemini",
        "description": "Gemini API (Google AI Studio key).",
        "needs_key": True, "needs_base_url": False,
        "default_base_url": "https://generativelanguage.googleapis.com/v1beta",
        "models": [{"id": "gemini-4-argon", "label": "Gemini 4 Argon", "price": None},
                   {"id": "gemini-3.8-flash", "label": "Gemini 3.8 Flash", "price": None},
                   {"id": "gemini-3.5-flash-lite", "label": "Gemini 3.5 Flash-Lite", "price": None}],
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


# Model names are suggestions current at the time of writing; confirm with "Discover models".
# Providers seeded into new installations. Keys are added later through the vault.
SEED_PROVIDERS: list[dict] = [
    {"id": "demo", "type": "simulator", "label": "ADEF Demo Simulator (offline)", "base_url": "", "api_key_ref": "", "options": {}},
    {"id": "anthropic", "type": "anthropic", "label": "Anthropic (Claude)", "base_url": "", "api_key_ref": "", "options": {}},
    {"id": "openai", "type": "openai", "label": "OpenAI", "base_url": "", "api_key_ref": "", "options": {}},
    {"id": "google-gemini", "type": "google_gemini", "label": "Google Gemini", "base_url": "", "api_key_ref": "", "options": {}},
    {"id": "azure-openai", "type": "azure_openai", "label": "Azure OpenAI", "base_url": "https://contoso-ai.openai.azure.com",
     "api_key_ref": "", "options": {"api_version": "2024-10-21"}},
    {"id": "aws-bedrock", "type": "aws_bedrock", "label": "Amazon Bedrock", "base_url": "", "api_key_ref": "",
     "options": {"region": "us-east-1"}},
    {"id": "ollama-local", "type": "openai_compatible", "label": "Ollama (local, open-weight)", "base_url": "http://localhost:11434/v1",
     "api_key_ref": "", "options": {}},
]


def _b(provider_id: str, model: str, effort: str = "medium", max_tokens: int = 16000) -> dict:
    return {"provider_id": provider_id, "model": model, "effort": effort, "max_tokens": max_tokens}


# Agent team presets: provider + model per agent.
TEAM_PRESETS: dict[str, dict] = {
    "multi-vendor": {
        "label": "Multi-vendor enterprise team",
        "description": "A different provider and model per agent, matched to each stage's work.",
        "agents": {
            "adef-orchestrator": _b("anthropic", "claude-opus-5-5", "high"),
            "adef-intent-requirements": _b("openai", "gpt-5.6-sol", "high"),
            "adef-source-target-mapping": _b("google-gemini", "gemini-4-argon", "high", 32000),
            "adef-solution-design": _b("anthropic", "claude-fable-5-2", "high", 32000),
            "adef-pipeline-build": _b("azure-openai", "gpt-5-6-terra-prod", "medium", 32000),
            "adef-test-quality": _b("aws-bedrock", "anthropic.claude-sonnet-5-5", "medium"),
            "adef-release-deploy": _b("anthropic", "claude-sonnet-5-5", "medium"),
            "adef-operations-observability": _b("ollama-local", "llama3.3", "low", 8000),
            "adef-data-consumption": _b("google-gemini", "gemini-3.8-flash", "medium"),
        },
    },
    "all-claude": {
        "label": "All Claude (tiered)",
        "description": "Fable for design, Opus for coordination and build, Sonnet for analysis, Haiku for operations.",
        "agents": {
            "adef-orchestrator": _b("anthropic", "claude-opus-5-5", "high"),
            "adef-intent-requirements": _b("anthropic", "claude-sonnet-5-5", "high"),
            "adef-source-target-mapping": _b("anthropic", "claude-sonnet-5-5", "high", 32000),
            "adef-solution-design": _b("anthropic", "claude-fable-5-2", "high", 32000),
            "adef-pipeline-build": _b("anthropic", "claude-opus-5-5", "high", 32000),
            "adef-test-quality": _b("anthropic", "claude-sonnet-5-5", "medium"),
            "adef-release-deploy": _b("anthropic", "claude-sonnet-5-5", "medium"),
            "adef-operations-observability": _b("anthropic", "claude-haiku-5-5", "low", 8000),
            "adef-data-consumption": _b("anthropic", "claude-sonnet-5-5", "medium"),
        },
    },
    "all-openai": {
        "label": "All OpenAI",
        "description": "GPT-5.6 Sol for heavy stages, Terra and Luna for the rest.",
        "agents": {a: _b("openai", m, e) for a, m, e in [
            ("adef-orchestrator", "gpt-5.6-sol", "high"), ("adef-intent-requirements", "gpt-5.6-sol", "high"),
            ("adef-source-target-mapping", "gpt-5.6-sol", "high"), ("adef-solution-design", "gpt-5.6-sol", "high"),
            ("adef-pipeline-build", "gpt-5.6-terra", "medium"), ("adef-test-quality", "gpt-5.6-terra", "medium"),
            ("adef-release-deploy", "gpt-5.6-luna", "low"), ("adef-operations-observability", "gpt-5.6-luna", "low"),
            ("adef-data-consumption", "gpt-5.6-terra", "medium")]},
    },
    "cost-optimized": {
        "label": "Cost-optimised mix",
        "description": "Small, fast models everywhere except Design.",
        "agents": {
            "adef-orchestrator": _b("anthropic", "claude-haiku-5-5", "medium"),
            "adef-intent-requirements": _b("google-gemini", "gemini-3.8-flash", "medium"),
            "adef-source-target-mapping": _b("google-gemini", "gemini-3.8-flash", "medium", 32000),
            "adef-solution-design": _b("anthropic", "claude-sonnet-5-5", "high", 32000),
            "adef-pipeline-build": _b("openai", "gpt-5.6-luna", "medium", 32000),
            "adef-test-quality": _b("anthropic", "claude-haiku-5-5", "medium"),
            "adef-release-deploy": _b("google-gemini", "gemini-3.5-flash-lite", "low"),
            "adef-operations-observability": _b("ollama-local", "llama3.3", "low", 8000),
            "adef-data-consumption": _b("google-gemini", "gemini-3.5-flash-lite", "low"),
        },
    },
    "all-gemini": {
        "label": "All Google Gemini",
        "description": "Gemini 4 Argon for heavy stages, Gemini 3.8 Flash for the rest.",
        "agents": {a: _b("google-gemini", m, e) for a, m, e in [
            ("adef-orchestrator", "gemini-4-argon", "high"), ("adef-intent-requirements", "gemini-4-argon", "high"),
            ("adef-source-target-mapping", "gemini-4-argon", "high"), ("adef-solution-design", "gemini-4-argon", "high"),
            ("adef-pipeline-build", "gemini-4-argon", "medium"), ("adef-test-quality", "gemini-3.8-flash", "medium"),
            ("adef-release-deploy", "gemini-3.8-flash", "low"), ("adef-operations-observability", "gemini-3.8-flash", "low"),
            ("adef-data-consumption", "gemini-3.8-flash", "medium")]},
    },
    "simulator": {
        "label": "Demo Simulator only",
        "description": "Every agent offline and deterministic. No keys, no network.",
        "agents": {a: _b("demo", "adef-simulator-1") for a in [
            "adef-orchestrator", "adef-intent-requirements", "adef-source-target-mapping", "adef-solution-design",
            "adef-pipeline-build", "adef-test-quality", "adef-release-deploy", "adef-operations-observability",
            "adef-data-consumption"]},
    },
}


def provider_ready(p: dict) -> bool:
    """True when the provider has what it needs to be called (a key where one is required)."""
    t = PROVIDER_TYPES.get(p.get("type"), {})
    return p.get("type") == "simulator" or not t.get("needs_key") or bool(p.get("api_key_ref"))


# Standard environment variables per seeded provider. When a key is present in the environment the
# provider references it (env:VAR); the value itself is never copied into settings or the vault.
ENV_KEYS = {
    "anthropic": {"key": ["ANTHROPIC_API_KEY"]},
    "openai": {"key": ["OPENAI_API_KEY"]},
    "google-gemini": {"key": ["GEMINI_API_KEY", "GOOGLE_API_KEY"]},
    "azure-openai": {"key": ["AZURE_OPENAI_API_KEY"], "base_url": "AZURE_OPENAI_ENDPOINT"},
    "aws-bedrock": {"key": ["AWS_BEARER_TOKEN_BEDROCK"], "region": "AWS_REGION"},
    "ollama-local": {"base_url": "OLLAMA_BASE_URL"},
}


def env_key_for(provider_id: str) -> str | None:
    import os
    for var in ENV_KEYS.get(provider_id, {}).get("key", []):
        if os.environ.get(var):
            return var
    return None


def preset_for_env() -> str:
    """Pick the agent team for a fresh install from the keys present in the environment."""
    import os
    if os.environ.get("ADEF_TEAM_PRESET") in TEAM_PRESETS:
        return os.environ["ADEF_TEAM_PRESET"]
    vendors = {p for p in ("anthropic", "openai", "google-gemini", "azure-openai", "aws-bedrock") if env_key_for(p)}
    if vendors == {"anthropic"}:
        return "all-claude"
    if vendors == {"openai"}:
        return "all-openai"
    if vendors == {"google-gemini"}:
        return "all-gemini"
    return "multi-vendor"
