"""Model router HTTP service — thin ModelProvider façade."""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import uvicorn

from provider import GenerateRequest, ModelProvider, build_provider_from_env

app = FastAPI(title="helm-model-router", version="0.1.0")
PROVIDER: ModelProvider = build_provider_from_env()


class GenerateBody(BaseModel):
    prompt: str
    system: str | None = None
    max_tokens: int = Field(default=512, ge=1, le=4096)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)


@app.get("/health")
def health() -> dict[str, Any]:
    stats = PROVIDER.stats().as_dict()
    return {
        "ok": True,
        "service": "model-router",
        "provider": os.environ.get("MODEL_PROVIDER", "stub"),
        "model": os.environ.get("MODEL_NAME", "stub/local"),
        "stats": stats,
    }


@app.get("/v1/stats")
def stats() -> dict[str, Any]:
    return PROVIDER.stats().as_dict()


@app.post("/v1/generate")
def generate(body: GenerateBody) -> dict[str, Any]:
    try:
        result = PROVIDER.generate(
            GenerateRequest(
                prompt=body.prompt,
                system=body.system,
                max_tokens=body.max_tokens,
                temperature=body.temperature,
            )
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "text": result.text,
        "provider": result.provider,
        "model": result.model,
        "usage": {
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "total_tokens": result.total_tokens,
        },
        "stats": PROVIDER.stats().as_dict(),
    }


if __name__ == "__main__":
    host = os.environ.get("MODEL_ROUTER_HOST", "0.0.0.0")
    port = int(os.environ.get("MODEL_ROUTER_PORT", "8082"))
    uvicorn.run(app, host=host, port=port)
