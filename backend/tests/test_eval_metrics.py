import math

import pytest
from evals.metrics import ndcg_at_k, recall_at_k, reciprocal_rank


def test_recall_at_k_single_relevant():
    ranked = ["a", "b", "c", "d"]
    assert recall_at_k(ranked, "b", 1) == 0.0
    assert recall_at_k(ranked, "b", 2) == 1.0
    assert recall_at_k(ranked, "z", 4) == 0.0


def test_recall_at_k_multiple_relevant():
    assert recall_at_k(["a", "x", "b", "y"], {"a", "b", "c"}, 3) == pytest.approx(2 / 3)


def test_reciprocal_rank_and_cutoff():
    assert reciprocal_rank(["a", "b", "c"], "a") == 1.0
    assert reciprocal_rank(["a", "b", "c"], "c") == pytest.approx(1 / 3)
    assert reciprocal_rank(["a", "b", "c"], "z") == 0.0
    ranked = [f"x{i}" for i in range(10)] + ["hit"]
    assert reciprocal_rank(ranked, "hit", k=10) == 0.0  # rank 11 is outside MRR@10
    assert reciprocal_rank(ranked, "hit", k=11) == pytest.approx(1 / 11)


def test_ndcg_hand_computed():
    assert ndcg_at_k(["a", "b"], "a", 5) == 1.0
    assert ndcg_at_k(["a", "b", "c"], "b", 5) == pytest.approx(1 / math.log2(3))
    assert ndcg_at_k(["a", "b", "c"], "z", 5) == 0.0
    assert ndcg_at_k(["x", "y", "z", "w", "v", "a"], "a", 5) == 0.0  # rank 6 is outside the cut-off
    # two relevant items at ranks 1 and 3: DCG = 1 + 1/2, ideal = 1 + 1/log2(3)
    expected = (1 + 1 / math.log2(4)) / (1 + 1 / math.log2(3))
    assert ndcg_at_k(["a", "x", "b"], {"a", "b"}, 5) == pytest.approx(expected)
