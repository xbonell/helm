"""Minimal ModelProvider abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
import threading

import httpx


@dataclass(frozen=True)
class GenerateRequest:
    prompt: str
    system: str | None = None
    max_tokens: int = 512
    temperature: float = 0.2


@dataclass(frozen=True)
class GenerateResult:
    text: str
    provider: str
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass
class UsageStats:
    request_count: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    last_provider: str | None = None
    last_model: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_count": self.request_count,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "last_provider": self.last_provider,
            "last_model": self.last_model,
        }


class ModelProvider(ABC):
    @abstractmethod
    def generate(self, request: GenerateRequest) -> GenerateResult:
        raise NotImplementedError

    @abstractmethod
    def stats(self) -> UsageStats:
        raise NotImplementedError


class _StatsMixin:
    def __init__(self) -> None:
        self._stats = UsageStats()
        self._lock = threading.Lock()

    def stats(self) -> UsageStats:
        with self._lock:
            return UsageStats(**self._stats.__dict__)

    def _record(self, result: GenerateResult) -> None:
        with self._lock:
            self._stats.request_count += 1
            self._stats.last_provider = result.provider
            self._stats.last_model = result.model
            if result.prompt_tokens is not None:
                self._stats.prompt_tokens += result.prompt_tokens
            if result.completion_tokens is not None:
                self._stats.completion_tokens += result.completion_tokens
            if result.total_tokens is not None:
                self._stats.total_tokens += result.total_tokens
            elif result.prompt_tokens is not None or result.completion_tokens is not None:
                self._stats.total_tokens += (result.prompt_tokens or 0) + (
                    result.completion_tokens or 0
                )


class StubModelProvider(_StatsMixin, ModelProvider):
    """Zero-cost deterministic provider for local MVP without API keys."""

    def __init__(self, model: str = "stub/local") -> None:
        super().__init__()
        self._model = model

    def generate(self, request: GenerateRequest) -> GenerateResult:
        preview = request.prompt.strip().replace("\n", " ")
        if len(preview) > 160:
            preview = preview[:157] + "..."
        text = (
            "[stub model]\n"
            f"system={request.system or '(none)'}\n"
            f"prompt_preview={preview}\n"
            "This is a local stub response used when MODEL_PROVIDER=stub."
        )
        # Rough char/4 token estimate for measurability without a tokenizer.
        prompt_tokens = max(1, len(request.prompt) // 4)
        completion_tokens = max(1, len(text) // 4)
        result = GenerateResult(
            text=text,
            provider="stub",
            model=self._model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )
        self._record(result)
        return result


class OpenAICompatibleProvider(_StatsMixin, ModelProvider):
    """OpenAI chat-completions compatible endpoint (OpenRouter, Groq, OpenAI, etc.)."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 120.0,
        client: httpx.Client | None = None,
    ) -> None:
        super().__init__()
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._client = client

    def generate(self, request: GenerateRequest) -> GenerateResult:
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})

        payload = {
            "model": self._model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        client = self._client or httpx.Client(timeout=self._timeout)
        owns = self._client is None
        try:
            response = client.post(
                f"{self._base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        finally:
            if owns:
                client.close()

        text = body["choices"][0]["message"]["content"]
        usage = body.get("usage") or {}
        result = GenerateResult(
            text=text,
            provider="openai_compatible",
            model=str(body.get("model") or self._model),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        )
        self._record(result)
        return result


def build_provider_from_env(env: dict[str, str] | None = None) -> ModelProvider:
    import os

    e = env or os.environ
    kind = (e.get("MODEL_PROVIDER") or "stub").strip().lower()
    if kind in {"stub", "local", "none", ""}:
        return StubModelProvider(model=e.get("MODEL_NAME") or "stub/local")
    if kind in {"openai_compatible", "openai", "openrouter", "groq"}:
        base = e.get("MODEL_BASE_URL") or "https://openrouter.ai/api/v1"
        key = e.get("MODEL_API_KEY") or ""
        model = e.get("MODEL_NAME") or "openrouter/free"
        if not key:
            raise ValueError("MODEL_API_KEY is required for openai_compatible provider")
        return OpenAICompatibleProvider(base_url=base, api_key=key, model=model)
    raise ValueError(f"Unknown MODEL_PROVIDER={kind!r}")
