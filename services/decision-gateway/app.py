"""Decision gateway HTTP service.

Exposes DecisionEngine without leaking Decider-specific payloads.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import uvicorn

from engine import DeciderDecisionEngine, DecisionEngine, DecisionRequest, DecisionResult

app = FastAPI(title="helm-decision-gateway", version="0.2.0")


def _build_engine() -> DecisionEngine:
    base = os.environ.get("DECIDER_BASE_URL", "http://decider:8000")
    return DeciderDecisionEngine(base_url=base)


ENGINE: DecisionEngine = _build_engine()


class DecideBody(BaseModel):
    context: str
    candidates: list[str] = Field(min_length=2)
    instructions: str = "Which candidate best handles this request?"
    criteria: dict[str, str] | None = None


class DecideResponse(BaseModel):
    choice: str
    confidence: float
    probabilities: dict[str, float]
    engine: str
    usage: dict[str, Any] = Field(default_factory=dict)


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "service": "decision-gateway",
        "decider_base_url": os.environ.get("DECIDER_BASE_URL", "http://decider:8000"),
        "engine": "decider",
    }


@app.post("/v1/decide", response_model=DecideResponse)
def decide(body: DecideBody) -> DecideResponse:
    request = DecisionRequest(
        context=body.context,
        candidates=body.candidates,
        instructions=body.instructions,
        criteria=body.criteria,
    )
    try:
        result: DecisionResult = ENGINE.decide(request)
    except Exception as exc:  # noqa: BLE001 — surface upstream failures cleanly
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return DecideResponse(
        choice=result.choice,
        confidence=result.confidence,
        probabilities=dict(result.probabilities),
        engine=result.engine,
        usage=dict(result.raw_usage),
    )


if __name__ == "__main__":
    host = os.environ.get("DECISION_GATEWAY_HOST", "0.0.0.0")
    port = int(os.environ.get("DECISION_GATEWAY_PORT", "8081"))
    uvicorn.run(app, host=host, port=port)
