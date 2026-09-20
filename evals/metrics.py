"""Ranking metrics with binary relevance. `ranked` is the list of retrieved IDs, best first.

Classification metrics, bootstrap confidence intervals and Cohen's kappa are below.
"""

import math
import random
from collections import Counter
from collections.abc import Callable, Collection, Sequence


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


# ── classification ──────────────────────────────────────────────────────────


def accuracy(y_true: Sequence[str], y_pred: Sequence[str]) -> float:
    if len(y_true) != len(y_pred) or not y_true:
        raise ValueError("y_true and y_pred must be non-empty and equally long")
    return sum(t == p for t, p in zip(y_true, y_pred, strict=True)) / len(y_true)


def per_class_prf(y_true: Sequence[str], y_pred: Sequence[str], labels: Sequence[str] | None = None) -> dict:
    """Precision, recall, F1 and support per label. A label with no predictions has precision 0, with no true
    examples recall 0 (and F1 0), as scikit-learn does with zero_division=0."""
    labels = list(labels) if labels is not None else sorted(set(y_true) | set(y_pred))
    out = {}
    for lab in labels:
        tp = sum(t == lab and p == lab for t, p in zip(y_true, y_pred, strict=True))
        fp = sum(t != lab and p == lab for t, p in zip(y_true, y_pred, strict=True))
        fn = sum(t == lab and p != lab for t, p in zip(y_true, y_pred, strict=True))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        out[lab] = {"precision": precision, "recall": recall, "f1": f1, "support": tp + fn}
    return out


def macro_f1(y_true: Sequence[str], y_pred: Sequence[str], labels: Sequence[str] | None = None) -> float:
    """Unweighted mean of the per-label F1 over `labels` (default: every label seen in truth or prediction)."""
    scores = per_class_prf(y_true, y_pred, labels)
    return sum(s["f1"] for s in scores.values()) / len(scores)


def confusion(y_true: Sequence[str], y_pred: Sequence[str]) -> dict[str, dict[str, int]]:
    """{true label: {predicted label: count}}, only non-zero cells."""
    out: dict[str, Counter] = {}
    for t, p in zip(y_true, y_pred, strict=True):
        out.setdefault(t, Counter())[p] += 1
    return {t: dict(c) for t, c in out.items()}


def rate(flags: Sequence[bool]) -> float:
    """Share of True values; nan for an empty list, so a missing denominator is never reported as 0 or 1."""
    return sum(flags) / len(flags) if flags else float("nan")


# ── uncertainty and agreement ───────────────────────────────────────────────


def bootstrap_ci(
    values: Sequence[float],
    stat: Callable[[Sequence[float]], float] | None = None,
    n_boot: int = 2000,
    alpha: float = 0.05,
    seed: int = 20260920,
) -> tuple[float, float]:
    """Percentile bootstrap confidence interval of `stat` (default: the mean). Deterministic per seed."""
    if not values:
        raise ValueError("bootstrap needs at least one value")
    stat = stat or (lambda xs: sum(xs) / len(xs))
    rng = random.Random(seed)
    n = len(values)
    stats = sorted(stat([values[rng.randrange(n)] for _ in range(n)]) for _ in range(n_boot))
    lo = stats[int((alpha / 2) * n_boot)]
    hi = stats[min(n_boot - 1, int((1 - alpha / 2) * n_boot))]
    return lo, hi


def cohen_kappa(a: Sequence[int | str], b: Sequence[int | str], weights: str | None = None) -> float:
    """Cohen's kappa between two raters. `weights=None` is the unweighted kappa; "linear" or "quadratic" penalise
    ordinal disagreements by distance (labels must then be numbers). Returns nan when chance agreement is
    perfect (both raters always give the same single label), because kappa is undefined there."""
    if len(a) != len(b) or not a:
        raise ValueError("both raters must rate the same non-empty list of items")
    labels = sorted(set(a) | set(b))
    n = len(a)
    idx = {lab: i for i, lab in enumerate(labels)}
    k = len(labels)
    observed = [[0.0] * k for _ in range(k)]
    for x, y in zip(a, b, strict=True):
        observed[idx[x]][idx[y]] += 1 / n
    row = [sum(observed[i]) for i in range(k)]
    col = [sum(observed[i][j] for i in range(k)) for j in range(k)]

    def penalty(i: int, j: int) -> float:
        if weights is None:
            return 0.0 if i == j else 1.0
        d = abs(labels[i] - labels[j])  # type: ignore[operator]
        if weights == "linear":
            return d / (abs(labels[-1] - labels[0]) or 1)  # type: ignore[operator]
        if weights == "quadratic":
            return (d / (abs(labels[-1] - labels[0]) or 1)) ** 2  # type: ignore[operator]
        raise ValueError(f"unknown weights {weights!r}")

    observed_disagreement = sum(penalty(i, j) * observed[i][j] for i in range(k) for j in range(k))
    expected_disagreement = sum(penalty(i, j) * row[i] * col[j] for i in range(k) for j in range(k))
    if expected_disagreement == 0:
        return float("nan")
    return 1 - observed_disagreement / expected_disagreement
