"""DecisionEngine abstraction and Decider-backed implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import httpx


@dataclass(frozen=True)
class DecisionRequest:
    """Provider-agnostic decision request."""

    context: str
    candidates: Sequence[str]
    instructions: str = "Which candidate best handles this request?"
    criteria: Mapping[str, str] | None = None


@dataclass(frozen=True)
class DecisionResult:
    """Typed decision result — no Decider-specific payload leaks."""

    choice: str
    confidence: float
    probabilities: Mapping[str, float] = field(default_factory=dict)
    engine: str = "unknown"
    raw_usage: Mapping[str, Any] = field(default_factory=dict)


class DecisionEngine(ABC):
    @abstractmethod
    def decide(self, request: DecisionRequest) -> DecisionResult:
        raise NotImplementedError


class DeciderDecisionEngine(DecisionEngine):
    """Adapters Mapika Decider HTTP API to DecisionEngine."""

    def __init__(
        self,
        base_url: str = "http://decider:8000",
        *,
        timeout: float = 300.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = client

    def decide(self, request: DecisionRequest) -> DecisionResult:
        if len(request.candidates) < 2:
            raise ValueError("DecisionRequest.candidates requires at least 2 options")

        criteria = dict(request.criteria or {})
        for name in request.candidates:
            criteria.setdefault(name, name)

        # Prefer native typed wire format.
        payload = {
            "state": {"message": request.context},
            "questions": {
                "handler": {
                    "type": "choice",
                    "instructions": request.instructions,
                    "criteria": {name: criteria[name] for name in request.candidates},
                }
            },
        }

        client = self._client or httpx.Client(timeout=self._timeout)
        owns_client = self._client is None
        try:
            response = client.post(f"{self._base_url}/v1/systemone", json=payload)
            response.raise_for_status()
            body = response.json()
        finally:
            if owns_client:
                client.close()

        answer = body["answers"]["handler"]
        choice = str(answer["choice"])
        if choice not in request.candidates:
            raise RuntimeError(f"Decider returned unexpected choice {choice!r}")

        probs = {str(k): float(v) for k, v in (answer.get("probabilities") or {}).items()}
        confidence = float(answer.get("confidence", probs.get(choice, 0.0)))
        usage = body.get("usage") or {}

        return DecisionResult(
            choice=choice,
            confidence=confidence,
            probabilities=probs,
            engine="decider",
            raw_usage=usage if isinstance(usage, dict) else {},
        )
