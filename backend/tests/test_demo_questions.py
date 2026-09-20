"""M8: the 8 demo questions (scripts/demo_questions.yaml) answered from the committed cassettes, with no API key.

Same expectations as `scripts/smoke_demo.py`, but through the real POST /api/chat in process, so a prompt, schema or
guardrail change that breaks a recording (cassette miss, fallback answer, missing block) fails the test suite.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agent.llm import ReplayClient
from app.agent.orchestrator import Agent
from app.config import Settings
from app.main import app, get_agent

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from smoke_demo import check, load_questions, parse_sse  # noqa: E402

QUESTIONS = load_questions()


def test_the_demo_has_the_requested_mix():
    cats = [q["category"] for q in QUESTIONS]
    assert len(QUESTIONS) == 8
    assert sorted(cats) == sorted(
        ["discover"] * 2 + ["product_question", "simulate", "advice_request", "injection"] + ["portfolio_insight"] * 2
    )
    assert any(
        q["message"] == "Warum ist mein Depot im August gefallen?" and q["customer_id"] == "markus" for q in QUESTIONS
    )


@pytest.fixture(scope="module")
def client(indexed_ctx):
    settings = Settings(_env_file=None, anthropic_api_key=None)  # no key: replay
    agent = Agent(ReplayClient(REPO_ROOT / "fixtures" / "cassettes"), indexed_ctx, settings, None)
    app.dependency_overrides[get_agent] = lambda: agent
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.parametrize("question", QUESTIONS, ids=[q["id"] for q in QUESTIONS])
def test_demo_question_is_answered_from_its_cassettes(client, question):
    with client.stream(
        "POST", "/api/chat", json={"customer_id": question["customer_id"], "message": question["message"]}
    ) as res:
        events = parse_sse(res.iter_lines())
    assert check(question, events, "replay") == []
