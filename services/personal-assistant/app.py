"""Personal assistant HTTP API."""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

from brief import generate_daily_brief

app = FastAPI(title="helm-personal-assistant", version="0.1.0")


class BriefRequest(BaseModel):
    pass


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "personal-assistant", "agent": "personal-assistant"}


@app.post("/v1/generate-daily-brief")
def daily_brief(body: BriefRequest | None = None) -> dict[str, Any]:
    try:
        return generate_daily_brief()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc


if __name__ == "__main__":
    host = os.environ.get("PERSONAL_ASSISTANT_HOST", "0.0.0.0")
    port = int(os.environ.get("PERSONAL_ASSISTANT_PORT", "8083"))
    uvicorn.run(app, host=host, port=port)
