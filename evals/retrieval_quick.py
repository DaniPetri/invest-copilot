"""Quick retrieval ablation: data/generated/retrieval.jsonl in every mode.

    cd backend && uv run python ../evals/retrieval_quick.py [--example "Was kostet der Welt ETF pro Jahr?"]

Prints recall@1, recall@5, MRR@10, nDCG@5 and p50 latency per mode. Exits 1 when hybrid recall@5 < 0.85
(SPEC §11 gate). `hybrid_rerank` only runs with RERANK=1 (downloads a ~1.1 GB model once).
"""

import argparse
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT), str(REPO_ROOT / "backend")]

from app.config import get_settings  # noqa: E402
from app.data.store import Store  # noqa: E402
from app.rag.search import KidIndex, RerankUnavailableError  # noqa: E402
from evals.metrics import ndcg_at_k, recall_at_k, reciprocal_rank  # noqa: E402

MODES = ["bm25", "dense", "hybrid", "hybrid_rerank"]
GATE = 0.85


def evaluate(index: KidIndex, questions: list[dict], mode: str) -> dict:
    rows, latencies, failures = [], [], []
    for q in questions:
        t0 = time.perf_counter()
        ranked = [c.id for c in index.retrieve(q["question"], k=10, mode=mode).chunks]
        latencies.append((time.perf_counter() - t0) * 1000)
        gold = q["expected_chunk_id"]
        rows.append(
            (
                recall_at_k(ranked, gold, 1),
                recall_at_k(ranked, gold, 5),
                reciprocal_rank(ranked, gold, 10),
                ndcg_at_k(ranked, gold, 5),
            )
        )
        if gold not in ranked[:5]:
            failures.append((q, ranked[:3]))
    n = len(rows)
    return {
        "recall@1": sum(r[0] for r in rows) / n,
        "recall@5": sum(r[1] for r in rows) / n,
        "mrr@10": sum(r[2] for r in rows) / n,
        "ndcg@5": sum(r[3] for r in rows) / n,
        "p50_ms": statistics.median(latencies),
        "failures": failures,
    }


def print_table(results: dict[str, dict | None], n_questions: int) -> None:
    print(f"\nRetrieval ablation: {n_questions} questions, 1 relevant chunk each\n")
    print(f"| {'mode':<14} | recall@1 | recall@5 | MRR@10 | nDCG@5 | p50 latency |")
    print(f"|{'-' * 16}|{'-' * 10}|{'-' * 10}|{'-' * 8}|{'-' * 8}|{'-' * 13}|")
    for mode, r in results.items():
        if r is None:
            print(f"| {mode:<14} | {'skipped (RERANK=0)':^47} |")
        else:
            cells = (r["recall@1"], r["recall@5"], r["mrr@10"], r["ndcg@5"])
            print(
                f"| {mode:<14} | {cells[0]:>8.3f} | {cells[1]:>8.3f} | {cells[2]:>6.3f} | {cells[3]:>6.3f} "
                f"| {r['p50_ms']:>8.1f} ms |"
            )


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--example", help="also print the top 3 chunks of this query in hybrid mode")
    ap.add_argument("--modes", nargs="+", choices=MODES, default=MODES)
    ap.add_argument("--every", type=int, default=1, help="use every N-th question (reranking is slow on CPU)")
    ap.add_argument("--failures", type=int, default=0, help="print this many hybrid misses")
    args = ap.parse_args(argv)

    root = get_settings().data_dir
    questions = Store(root).retrieval_questions[:: args.every]
    index = KidIndex(root)
    results: dict[str, dict | None] = {}
    for mode in args.modes:
        try:
            results[mode] = evaluate(index, questions, mode)
        except RerankUnavailableError:
            results[mode] = None
    print_table(results, len(questions))

    if args.failures and results.get("hybrid"):
        print(f"\nHybrid misses (recall@5), first {args.failures}:")
        for q, top in results["hybrid"]["failures"][: args.failures]:
            print(f"  {q['id']} {q['question']}\n    expected {q['expected_chunk_id']}\n    got      {top}")
    if args.example:
        print(f"\nExample query (hybrid): {args.example}")
        for i, c in enumerate(index.retrieve(args.example, k=3).chunks, start=1):
            print(f"  {i}. {c.id}  score={c.score:.4f}  flags={c.flags}\n     {c.text[:160]!r}")

    hybrid = results.get("hybrid")
    if hybrid and hybrid["recall@5"] < GATE:
        print(f"\nGATE FAILED: hybrid recall@5 {hybrid['recall@5']:.3f} < {GATE}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
