"""Ranking metrics with binary relevance. `ranked` is the list of retrieved IDs, best first.

M7 extends this module (accuracy, macro-F1, bootstrap CIs, Cohen's kappa).
"""

import math
from collections.abc import Collection, Sequence


def _relevant_set(relevant: str | Collection[str]) -> set[str]:
    return {relevant} if isinstance(relevant, str) else set(relevant)


def recall_at_k(ranked: Sequence[str], relevant: str | Collection[str], k: int) -> float:
    """Share of the relevant items found in the top k (1.0 or 0.0 when there is a single relevant item)."""
    rel = _relevant_set(relevant)
    return len(rel & set(ranked[:k])) / len(rel)


def reciprocal_rank(ranked: Sequence[str], relevant: str | Collection[str], k: int = 10) -> float:
    """1 / rank of the first relevant item within the top k, else 0."""
    rel = _relevant_set(relevant)
    for rank, item in enumerate(ranked[:k], start=1):
        if item in rel:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(ranked: Sequence[str], relevant: str | Collection[str], k: int = 5) -> float:
    """Normalised discounted cumulative gain with binary gains."""
    rel = _relevant_set(relevant)
    dcg = sum(1.0 / math.log2(rank + 1) for rank, item in enumerate(ranked[:k], start=1) if item in rel)
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, min(len(rel), k) + 1))
    return dcg / ideal if ideal else 0.0
