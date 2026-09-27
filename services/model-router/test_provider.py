from provider import GenerateRequest, StubModelProvider, build_provider_from_env


def test_stub_provider_tracks_usage() -> None:
    p = StubModelProvider()
    r = p.generate(GenerateRequest(prompt="Write a one-line weather note.", system="Be brief."))
    assert r.provider == "stub"
    assert "stub model" in r.text
    assert r.total_tokens and r.total_tokens > 0
    s = p.stats()
    assert s.request_count == 1
    assert s.last_provider == "stub"


def test_build_provider_defaults_to_stub() -> None:
    p = build_provider_from_env({"MODEL_PROVIDER": "stub"})
    assert isinstance(p, StubModelProvider)
