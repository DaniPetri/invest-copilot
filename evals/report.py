"""Markdown rendering of an eval report (`latest.md`). Pure function of the report dict."""

from typing import Any


def _f(x: Any, digits: int = 3) -> str:
    if x is None:
        return "–"
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, float):
        return f"{x:.{digits}f}"
    return str(x)


def _table(header: list[str], rows: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(str(c).replace("|", "\\|").replace("\n", " ") for c in row) + " |" for row in rows]
    return lines + [""]


def _gate_bound(g: dict) -> str:
    parts = []
    if g["min"] is not None:
        parts.append(f"≥ {_f(g['min'], 2)}")
    if g["max"] is not None:
        parts.append(f"≤ {_f(g['max'], 2)}")
    return " and ".join(parts)


def _retrieval(r: dict) -> list[str]:
    out = [f"## Retrieval ({r['n']} questions, one relevant chunk each)", ""]
    rows = []
    for mode in ("bm25", "dense", "hybrid"):
        m = r["modes"][mode]
        rows.append(
            [mode, _f(m["recall@1"]), _f(m["recall@5"]), _f(m["mrr@10"]), _f(m["ndcg@5"]), f"{m['p50_ms']:.1f} ms"]
        )
    sample = r.get("rerank_sample")
    if sample:
        m = sample["hybrid_rerank"]
        rows.append(
            [
                f"hybrid_rerank\\* (sample: every {sample['every']}th question, n = {sample['n']})",
                _f(m["recall@1"]),
                _f(m["recall@5"]),
                _f(m["mrr@10"]),
                _f(m["ndcg@5"]),
                f"{m['p50_ms']:.0f} ms",
            ]
        )
    out += _table(["Mode", "recall@1", "recall@5", "MRR@10", "nDCG@5", "p50 latency"], rows)
    if sample:
        b = sample["hybrid_same_sample"]
        out += [
            f"\\* Cross-encoder (`RERANK=1`) on a sample: {m['p50_ms'] / 1000:.1f} s per question on CPU. "
            f"Plain hybrid on the same sample: recall@1 {_f(b['recall@1'])}, recall@5 {_f(b['recall@5'])}, "
            f"MRR@10 {_f(b['mrr@10'])}, nDCG@5 {_f(b['ndcg@5'])}.",
            "",
        ]
    return out


def _router(r: dict) -> list[str]:
    out = [f"## Router ({r['n']} utterances)", ""]
    header = ["Split", "n", "Accuracy", "Macro-F1", "Advice recall", "False alarm", "Injection recall", "PII recall"]
    rows = []
    overall = {
        "n": r["n"],
        **{
            k: r["metrics"].get(k)
            for k in ("accuracy", "macro_f1", "advice_recall", "false_alarm_rate", "injection_recall", "pii_recall")
        },
    }
    for name, s in [("dev", r["splits"]["dev"]), ("blind", r["splits"]["blind"]), ("all", overall)]:
        if not s.get("n"):
            continue
        rows.append(
            [
                name,
                s["n"],
                _f(s.get("accuracy")),
                _f(s.get("macro_f1")),
                _f(s.get("advice_recall")),
                _f(s.get("false_alarm_rate")),
                _f(s.get("injection_recall")),
                _f(s.get("pii_recall")),
            ]
        )
    out += _table(header, rows)
    if r["per_class"]:
        out += _table(
            ["Intent", "Precision", "Recall", "F1", "n"],
            [[k, _f(v["precision"]), _f(v["recall"]), _f(v["f1"]), v["support"]] for k, v in r["per_class"].items()],
        )
    if r["misses"]:
        out += ["Deviations (expected → got):", ""]
        out += _table(
            ["ID", "Split", "Text", "expected", "got", "refused"],
            [
                [
                    m["id"],
                    m["split"],
                    m["text"],
                    m["expected"],
                    m["got"],
                    f"{_f(m['refused'])} (expected: {_f(m['expect_refuse'])})",
                ]
                for m in r["misses"]
            ],
        )
    return out


def _answers(r: dict) -> list[str]:
    m = r["metrics"]
    out = [f"## Answers ({r['n']} end-to-end questions)", ""]
    out += _table(
        ["Deterministic check", "Value"],
        [
            ["Citations valid", _f(m["citation_validity"])],
            ["Numbers grounded (numeric grounding)", _f(m["numeric_grounding_rate"])],
            ["No advice language", _f(m["advice_free_rate"])],
            ["Expected tools called", _f(m["expected_tools_rate"])],
            ["Repair round needed", _f(m["repair_rate"])],
            ["Safe fallback answer", _f(m["fallback_rate"])],
            ["Mean recorded cost per question", f"{_f(r.get('mean_cost_eur'), 4)} EUR"],
        ],
    )
    if r["judge"]:
        out += ["LLM judge (rubric 1–5), mean with 95 % bootstrap confidence interval:", ""]
        out += _table(
            ["Criterion", "Mean", "95 % CI", "Min", "n"],
            [
                [c, _f(s["mean"], 2), f"[{_f(s['ci95'][0], 2)}; {_f(s['ci95'][1], 2)}]", s["min"], s["n"]]
                for c, s in r["judge"].items()
            ],
        )
        weak = [x for x in r["rows"] if "judge" in x and min(v["score"] for v in x["judge"].values()) <= 3]
        if weak:
            out += ["Answers with a score ≤ 3:", ""]
            out += _table(
                ["ID", "Question", "Faith.", "Compl.", "Clarity", "Boundary", "Reason (weakest criterion)"],
                [
                    [x["id"], x["question"]]
                    + [x["judge"][c]["score"] for c in ("faithfulness", "completeness", "clarity", "boundary")]
                    + [min(x["judge"].values(), key=lambda v: v["score"])["reason"]]
                    for x in weak
                ],
            )
    return out


def _redteam(r: dict) -> list[str]:
    out = [f"## Red team ({r['n']} attacks)", ""]
    out += _table(
        ["Category", "Attacks", "Successes", "Attack success rate"],
        [
            [k, v["attacks"], v["successes"], _f(v["successes"] / v["attacks"], 2)]
            for k, v in sorted(r["by_category"].items())
        ],
    )
    wins = [x for x in r["rows"] if x["success"]]
    if wins:
        out += ["**Successful attacks:**", ""]
        out += _table(
            ["ID", "Category", "Attack", "Why"],
            [[x["id"], x["category"], x["message"], "; ".join(x["reasons"])] for x in wins],
        )
    out += ["How the attacks were defended:", ""]
    out += _table(
        ["ID", "Category", "Router intent", "Defence", "Quarantine"],
        [[x["id"], x["category"], x["intent"], x["defended_by"], x["quarantine"] or "–"] for x in r["rows"]],
    )
    return out


def _calibration(r: dict) -> list[str]:
    out = [f"## Judge calibration ({r['n']} answers)", ""]
    if r["agreement"]:
        out += _table(
            ["Criterion", "n", "Cohen's κ", "κ (linear weighted)", "exact agreement"],
            [
                [c, a["n"], _f(a["kappa"], 2), _f(a["kappa_linear"], 2), _f(a["exact_agreement"], 2)]
                for c, a in r["agreement"].items()
            ],
        )
    else:
        out += [
            "No human scores yet: fill in `human_score` in `evals/datasets/judge_calibration.jsonl` "
            "(1–5 per criterion) and run `--suite calibration` again. The judge scores are already in `latest.json`.",
            "",
        ]
    return out


def render_markdown(report: dict) -> str:
    lines = [
        "# Eval report",
        "",
        f"Generated {report['generated_at']} · mode `{report['mode']}`"
        + (" · **partial run, no gates**" if report["partial"] else ""),
        "",
    ]
    if report["gates"]:
        lines += [f"## Gates: {'passed' if report['passed'] else '**FAILED**'}", ""]
        lines += _table(
            ["Suite", "Metric", "Value", "Bound", "Result"],
            [
                [g["suite"], g["metric"], _f(g["value"]), _gate_bound(g), "✅ pass" if g["passed"] else "❌ fail"]
                for g in report["gates"]
            ],
        )
    for name, r in report["suites"].items():
        if r.get("aborted"):
            lines += [f"## {name}", "", f"**Aborted:** {r['aborted']}", ""]
            continue
        lines += {
            "retrieval": _retrieval,
            "router": _router,
            "answers": _answers,
            "redteam": _redteam,
            "calibration": _calibration,
        }[name](r)
        if r.get("errors"):
            lines += [f"**Errors ({len(r['errors'])}):**", ""]
            lines += _table(["ID", "Error"], [[e["id"], e["error"]] for e in r["errors"]])
    live = report.get("live")
    lines += ["## Cost", ""]
    lines += [
        f"Recorded LLM cost of the items run: {report['recorded_cost_eur']:.4f} EUR "
        "(price table in `config.py`, USD→EUR rate assumed)."
    ]
    if live:
        lines += [
            f"Actually spent live in this run: {live['spent_eur']:.4f} EUR in {live['calls']} API calls "
            f"(cap {live['cap_eur']:.2f} EUR)."
        ]
    else:
        lines += ["Replay mode: no API calls in this run."]
    return "\n".join(lines) + "\n"
