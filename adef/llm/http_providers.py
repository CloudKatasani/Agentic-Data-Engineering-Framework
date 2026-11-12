"""Non-Anthropic providers over plain HTTPS (no vendor SDKs required)."""
from __future__ import annotations

import httpx

from .base import LLMError, LLMResult, Provider

TIMEOUT = httpx.Timeout(600.0, connect=15.0)


def _raise_for(resp: httpx.Response, who: str) -> None:
    if resp.status_code >= 400:
        detail = resp.text[:300]
        if resp.status_code in (401, 403):
            raise LLMError(f"{who} rejected the credentials ({resp.status_code})")
        raise LLMError(f"{who} error {resp.status_code}: {detail}")


class OpenAICompatibleProvider(Provider):
    """OpenAI Chat Completions and every API that mirrors it."""

    type = "openai_compatible"
    default_base = "http://localhost:11434/v1"
    who = "OpenAI-compatible endpoint"

    def _url(self, path: str) -> str:
        return (self.base_url or self.default_base) + path

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _body(self, system, prompt, model, max_tokens, effort):
        body = {"model": model, "messages": [{"role": "system", "content": system},
                                             {"role": "user", "content": prompt}],
                "max_tokens": max_tokens}
        return body

    def complete(self, *, system, prompt, model, max_tokens=16000, effort="medium", context=None) -> LLMResult:
        try:
            r = httpx.post(self._url("/chat/completions"), headers=self._headers(),
                           json=self._body(system, prompt, model, max_tokens, effort), timeout=TIMEOUT)
        except httpx.HTTPError as e:
            raise LLMError(f"Cannot reach {self.who}: {e}") from e
        _raise_for(r, self.who)
        d = r.json()
        try:
            text = d["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as e:
            raise LLMError(f"Unexpected response from {self.who}") from e
        u = d.get("usage") or {}
        return LLMResult(text=text, model=d.get("model", model), provider=self.type,
                         input_tokens=u.get("prompt_tokens", 0), output_tokens=u.get("completion_tokens", 0))

    def list_models(self) -> list[str]:
        try:
            r = httpx.get(self._url("/models"), headers=self._headers(), timeout=30)
        except httpx.HTTPError as e:
            raise LLMError(f"Cannot reach {self.who}: {e}") from e
        _raise_for(r, self.who)
        return sorted(m["id"] for m in r.json().get("data", []))


class OpenAIProvider(OpenAICompatibleProvider):
    type = "openai"
    default_base = "https://api.openai.com/v1"
    who = "OpenAI"

    def _body(self, system, prompt, model, max_tokens, effort):
        body = {"model": model, "messages": [{"role": "system", "content": system},
                                             {"role": "user", "content": prompt}],
                "max_completion_tokens": max_tokens}
        if model.startswith(("o", "gpt-5")) and effort in ("low", "medium", "high"):
            body["reasoning_effort"] = effort
        return body


class AzureOpenAIProvider(OpenAICompatibleProvider):
    type = "azure_openai"
    who = "Azure OpenAI"

    def _headers(self) -> dict:
        return {"Content-Type": "application/json", "api-key": self.api_key or ""}

    def complete(self, *, system, prompt, model, max_tokens=16000, effort="medium", context=None) -> LLMResult:
        if not self.base_url:
            raise LLMError("Azure OpenAI needs the resource endpoint as base URL")
        ver = self.options.get("api_version", "2024-10-21")
        url = f"{self.base_url}/openai/deployments/{model}/chat/completions?api-version={ver}"
        body = {"messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                "max_completion_tokens": max_tokens}
        try:
            r = httpx.post(url, headers=self._headers(), json=body, timeout=TIMEOUT)
        except httpx.HTTPError as e:
            raise LLMError(f"Cannot reach Azure OpenAI: {e}") from e
        _raise_for(r, self.who)
        d = r.json()
        u = d.get("usage") or {}
        return LLMResult(text=d["choices"][0]["message"]["content"] or "", model=model, provider=self.type,
                         input_tokens=u.get("prompt_tokens", 0), output_tokens=u.get("completion_tokens", 0))

    def list_models(self) -> list[str]:
        return []


class GeminiProvider(Provider):
    type = "google_gemini"

    def complete(self, *, system, prompt, model, max_tokens=16000, effort="medium", context=None) -> LLMResult:
        base = self.base_url or "https://generativelanguage.googleapis.com/v1beta"
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": max_tokens}}
        try:
            r = httpx.post(f"{base}/models/{model}:generateContent", json=body, timeout=TIMEOUT,
                           headers={"x-goog-api-key": self.api_key or "", "Content-Type": "application/json"})
        except httpx.HTTPError as e:
            raise LLMError(f"Cannot reach Gemini: {e}") from e
        _raise_for(r, "Gemini")
        d = r.json()
        cands = d.get("candidates") or []
        if not cands:
            raise LLMError(f"Gemini returned no candidates: {d.get('promptFeedback')}")
        text = "".join(p.get("text", "") for p in cands[0].get("content", {}).get("parts", []))
        u = d.get("usageMetadata") or {}
        return LLMResult(text=text, model=model, provider=self.type,
                         input_tokens=u.get("promptTokenCount", 0), output_tokens=u.get("candidatesTokenCount", 0))

    def list_models(self) -> list[str]:
        base = self.base_url or "https://generativelanguage.googleapis.com/v1beta"
        r = httpx.get(f"{base}/models", headers={"x-goog-api-key": self.api_key or ""}, timeout=30)
        _raise_for(r, "Gemini")
        return sorted(m["name"].removeprefix("models/") for m in r.json().get("models", [])
                      if "generateContent" in m.get("supportedGenerationMethods", []))


class BedrockProvider(Provider):
    """Amazon Bedrock Converse API authenticated with a Bedrock API key (bearer token)."""

    type = "aws_bedrock"

    def complete(self, *, system, prompt, model, max_tokens=16000, effort="medium", context=None) -> LLMResult:
        region = self.options.get("region", "us-east-1")
        base = self.base_url or f"https://bedrock-runtime.{region}.amazonaws.com"
        body = {"system": [{"text": system}], "messages": [{"role": "user", "content": [{"text": prompt}]}],
                "inferenceConfig": {"maxTokens": max_tokens}}
        try:
            r = httpx.post(f"{base}/model/{model}/converse", json=body, timeout=TIMEOUT,
                           headers={"Authorization": f"Bearer {self.api_key or ''}", "Content-Type": "application/json"})
        except httpx.HTTPError as e:
            raise LLMError(f"Cannot reach Bedrock: {e}") from e
        _raise_for(r, "Bedrock")
        d = r.json()
        parts = d.get("output", {}).get("message", {}).get("content", [])
        u = d.get("usage") or {}
        return LLMResult(text="".join(p.get("text", "") for p in parts), model=model, provider=self.type,
                         input_tokens=u.get("inputTokens", 0), output_tokens=u.get("outputTokens", 0))
