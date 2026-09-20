import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.delenv("LLM_MODE", raising=False)
    get_settings.cache_clear()
    yield TestClient(app)
    get_settings.cache_clear()


def test_health_ok_and_replay_without_key(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["llm_mode"] == "replay"
    assert body["has_api_key"] is False


def test_health_never_leaks_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-secret-value")
    monkeypatch.setenv("LLM_MODE", "live")
    get_settings.cache_clear()
    try:
        res = TestClient(app).get("/api/health")
        assert res.json()["llm_mode"] == "live"
        assert "sk-test-secret-value" not in res.text
    finally:
        get_settings.cache_clear()
