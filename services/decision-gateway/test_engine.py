"""Unit tests for DecisionEngine — Decider payloads stay inside the adapter."""

from __future__ import annotations

import json

import httpx
import pytest

from engine import DeciderDecisionEngine, DecisionRequest


def test_decider_engine_maps_typed_response(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "answers": {
                    "handler": {
                        "type": "choice",
                        "choice": "personal",
                        "confidence": 0.91,
                        "probabilities": {
                            "personal": 0.91,
                            "finance": 0.03,
                            "development": 0.04,
                            "legal": 0.02,
                        },
                    }
                },
                "usage": {"input_tokens": 40, "output_tokens": 0},
            },
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    engine = DeciderDecisionEngine(base_url="http://decider:8000", client=client)

    result = engine.decide(
        DecisionRequest(
            context="Prepare today's weather report.",
            candidates=["personal", "finance", "development", "legal"],
            criteria={
                "personal": "daily brief / weather / lifestyle",
                "finance": "money",
                "development": "code",
                "legal": "law",
            },
        )
    )

    assert captured["url"].endswith("/v1/systemone")
    assert captured["body"]["questions"]["handler"]["type"] == "choice"
    assert result.choice == "personal"
    assert result.engine == "decider"
    assert result.confidence == pytest.approx(0.91)
    assert result.probabilities["personal"] == pytest.approx(0.91)
    # No Decider envelope keys on the public result type.
    assert not hasattr(result, "answers")
    assert "x_p_max" not in result.__dict__


def test_decider_engine_rejects_single_candidate() -> None:
    engine = DeciderDecisionEngine(base_url="http://decider:8000")
    with pytest.raises(ValueError):
        engine.decide(DecisionRequest(context="x", candidates=["only"]))
