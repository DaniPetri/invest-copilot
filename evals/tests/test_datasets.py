"""Shape and counts of the committed datasets (PLAN M7)."""

import json
import re
from collections import Counter
from pathlib import Path

import pytest

DATASETS = Path(__file__).resolve().parents[1] / "datasets"
INTENTS = {"discover", "product_question", "portfolio_insight", "simulate", "learn", "advice_request", "out_of_scope"}
CUSTOMERS = {"anna", "markus", "elif"}


def load(name: str) -> list[dict]:
    return [json.loads(line) for line in (DATASETS / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()]


@pytest.fixture(scope="module")
def router():
    return load("router")


def test_router_counts(router):
    assert len(router) == 80 and len({r["id"] for r in router}) == 80
    assert Counter(r["split"] for r in router) == {"dev": 60, "blind": 20}
    assert Counter(r["category"] for r in router) == {"regular": 54, "advice": 12, "injection": 8, "out_of_scope": 6}


def test_router_labels_are_consistent(router):
    for r in router:
        assert r["intent"] in INTENTS and r["text"].strip()
        assert set(r["flags"]) == {"advice_request", "injection_suspected", "pii_present"}
        if r["category"] == "advice":
            assert r["intent"] == "advice_request" and r["flags"]["advice_request"]
        if r["category"] == "injection":
            assert r["flags"]["injection_suspected"]
        else:
            assert not r["flags"]["injection_suspected"]
        if r["intent"] == "advice_request":
            assert r["flags"]["advice_request"]


def test_router_covers_the_hard_cases(router):
    tags = Counter(t for r in router for t in r["tags"])
    assert tags["dialect"] >= 8 and tags["typo"] >= 4 and tags["negation"] >= 3 and tags["pii"] >= 3
    assert len({r["text"] for r in router}) == 80


def test_blind_split_is_stratified(router):
    blind = [r for r in router if r["split"] == "blind"]
    counts = Counter(r["category"] for r in blind)
    assert counts["advice"] >= 3 and counts["injection"] >= 2 and counts["out_of_scope"] >= 2
    assert {r["intent"] for r in blind} == INTENTS  # every intent is in the blind split


def test_answers():
    rows = load("answers")
    assert len(rows) == 30 and len({r["id"] for r in rows}) == 30
    for r in rows:
        assert r["customer_id"] in CUSTOMERS and r["question"].strip() and r["reference_facts"]
        assert all(fact.strip() for fact in r["reference_facts"])
    assert Counter(r["kind"] for r in rows)["learn"] == 2


def test_redteam():
    rows = load("redteam")
    assert len(rows) == 20 and len({r["id"] for r in rows}) == 20
    assert Counter(r["category"] for r in rows) == {
        "direct_injection": 4,
        "kid_injection": 4,
        "pii_exfiltration": 4,
        "advice_coercion": 4,
        "fake_authority": 4,
    }
    for r in rows:
        assert r["customer_id"] in CUSTOMERS
        assert r["expect_refusal"] or r["must_not_match"] or r["forbid_tool_customers"]  # every attack can be judged
        assert not set(r["forbid_tool_customers"]) & {r["customer_id"]}
        for pattern in r["must_not_match"]:
            re.compile(pattern)


def test_kid_injection_attacks_cover_both_planted_products():
    text = " ".join(r["message"] for r in load("redteam") if r["category"] == "kid_injection")
    assert "Welt Small Cap Wachstum" in text and "Europa Dividenden Select" in text  # P13 and P31


def test_judge_calibration_has_empty_human_scores_to_fill_in():
    rows = load("judge_calibration")
    assert len(rows) == 12 and len({r["id"] for r in rows}) == 12
    for r in rows:
        assert r["answer"].strip() and r["reference_facts"]
        assert set(r["human_score"]) == {"faithfulness", "completeness", "clarity", "boundary"}
        assert all(v is None or v in range(1, 6) for v in r["human_score"].values())
