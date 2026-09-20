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


# ── the one-click UI questions x every persona ──────────────────────────────
# A cassette is valid only for the persona it was recorded with (the system prompt names the customer), and the UI
# sends its example questions with whichever persona is selected. Found on a fresh clone: "Warum ist mein Depot im
# August gefallen?" as Anna was a cassette_miss (`differs in: system`), and five UI questions had no cassette at all.
import re  # noqa: E402

from smoke_demo import PERSONAS, load_ui_matrix  # noqa: E402

MATRIX = load_ui_matrix()
SRC = REPO_ROOT / "frontend" / "src" / "screens"


@pytest.mark.parametrize("question", MATRIX, ids=[q["id"] for q in MATRIX])
def test_ui_question_is_answered_for_every_persona(client, question):
    with client.stream(
        "POST", "/api/chat", json={"customer_id": question["customer_id"], "message": question["message"]}
    ) as res:
        events = parse_sse(res.iter_lines())
    assert check(question, events, "replay") == []


def _strings(source: str, declaration: str) -> list[str]:
    """The quoted strings of `const NAME = [ ... ]` or `const NAME = '...'` in a TSX file."""
    m = re.search(rf"const {declaration}\s*=\s*(\[.*?\]|'.*?')\s*\n", source, re.S)
    assert m, f"const {declaration} not found: was it renamed?"
    return re.findall(r"'((?:[^'\\]|\\.)*)'", m.group(1))


def test_every_question_the_ui_offers_is_in_the_recorded_matrix():
    """Editing a chip or example in frontend/src without re-recording would give a cassette miss in replay mode."""
    recorded = {q["message"] for q in MATRIX}
    home = (SRC / "HomeScreen.tsx").read_text(encoding="utf-8")
    chat = (SRC / "ChatScreen.tsx").read_text(encoding="utf-8")
    depot = (SRC / "DepotScreen.tsx").read_text(encoding="utf-8")
    offered = _strings(home, "EXAMPLES") + _strings(chat, "EXAMPLE") + _strings(chat, "CHIPS")
    assert len(offered) == 4 + 1 + 3
    assert [s for s in offered if s not in recorded] == []
    # the depot button builds "Warum hat sich mein Depot am {dayLong(date)} bewegt?"; only 12. August 2026 is recorded
    assert "Warum hat sich mein Depot am ${dayLong(marker.event.date)} bewegt?" in depot
    assert "Warum hat sich mein Depot am 12. August 2026 bewegt?" in recorded


def test_the_matrix_covers_all_personas():
    assert {q["customer_id"] for q in MATRIX} == set(PERSONAS)
    assert len(MATRIX) == 7 * 3
