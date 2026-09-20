"""GET /api/evals/latest: the eval runner's reports (evals/reports/*.json) in the shape of the `EvalReport` contract.

The runner writes one report per run and a run may cover only some suites (`make eval-ci` skips answers and the
judge calibration). Each suite is therefore taken from the newest report that contains it, so /evals always shows
the last measured numbers of every suite, never an invented one.
"""

import json
from pathlib import Path
from typing import Any

from .schemas.evals import EvalReport

SUITE_LABELS = {
    "retrieval": "Retrieval",
    "router": "Router",
    "answers": "Antworten",
    "redteam": "Red Team",
}
METRIC_LABELS = {
    "hybrid_recall_at_5": "hybrid recall@5",
    "advice_recall": "Beratungsanfragen erkannt",
    "attack_successes": "erfolgreiche Angriffe",
    "faithfulness_mean": "faithfulness (Mittel)",
    "numeric_grounding_rate": "Zahlen belegt",
    "citation_validity": "Zitate gültig",
    "advice_free_rate": "ohne Beratungssprache",
}
CATEGORY_LABELS = {
    "direct_injection": "Direkte Injection",
    "kid_injection": "Injection über KID (P13, P31)",
    "pii_exfiltration": "Abfluss persönlicher Daten",
    "advice_coercion": "Beratung erzwingen",
    "fake_authority": "Gefälschte Autorität",
}


class NoEvalReportError(RuntimeError):
    pass


def _reports(reports_dir: Path) -> list[dict[str, Any]]:
    """Newest first: latest.json, timestamped runs (file names sort by time), then the committed full run.

    `bundled.json` is a snapshot of a full `make eval` run kept in git. `make eval-ci` overwrites latest.json with
    a run that has no answers suite, so on a clean clone this snapshot is what keeps /evals complete.
    """
    files = sorted((f for f in reports_dir.glob("2*.json")), reverse=True)
    latest = reports_dir / "latest.json"
    if latest.is_file():
        files.insert(0, latest)
    bundled = reports_dir / "bundled.json"
    if bundled.is_file():
        files.append(bundled)
    out = []
    for f in files:
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def _newest_suite(reports: list[dict], name: str) -> tuple[dict, dict] | None:
    """(suite result, the report it came from), or None. A run stopped early (`partial`) does not count."""
    for r in reports:
        suite = (r.get("suites") or {}).get(name)
        if suite and not r.get("partial") and suite.get("n"):
            return suite, r
    return None


def _gates(reports: list[dict], present: set[str]) -> list[dict]:
    """The gates (without the implicit `errors` ones) of the newest report that has each suite."""
    gates: list[dict] = []
    for suite in ("retrieval", "router", "answers", "redteam"):
        if suite not in present:
            continue
        found = _newest_suite(reports, suite)
        if found is None:
            continue
        report = found[1]
        for g in report.get("gates", []):
            if g["suite"] != suite or g["metric"] == "errors":
                continue
            bound = g["min"] if g.get("min") is not None else g.get("max")
            gates.append(
                {
                    "name": SUITE_LABELS[suite],
                    "metric": METRIC_LABELS.get(g["metric"], g["metric"]),
                    "value": g["value"],
                    "threshold": bound,
                    "passed": bool(g["passed"]),
                    "sample": False,
                }
            )
    return gates


def _judge(answers: dict, key: str) -> dict:
    j = answers["judge"][key]
    low, high = j["ci95"]
    return {"mean": j["mean"], "ci_low": low, "ci_high": high}


def build_eval_report(reports_dir: Path) -> EvalReport:
    reports = _reports(reports_dir)
    found = {name: _newest_suite(reports, name) for name in ("retrieval", "router", "answers", "redteam")}
    missing = [n for n, f in found.items() if f is None]
    if missing:
        raise NoEvalReportError(f"No eval results for: {', '.join(missing)}. Run `make eval`.")
    retrieval, router, answers, redteam = (found[n][0] for n in ("retrieval", "router", "answers", "redteam"))  # type: ignore[index]

    rows = []
    for mode in ("bm25", "dense", "hybrid"):
        m = retrieval["modes"][mode]
        rows.append((mode, m, m["n"]))
    rerank = (retrieval.get("rerank_sample") or {}).get("hybrid_rerank")
    if rerank:
        rows.append(("hybrid_rerank", rerank, retrieval["rerank_sample"]["n"]))

    calibration = _newest_suite(reports, "calibration")
    kappa = None
    n_cal = 12
    if calibration:
        n_cal = calibration[0]["n"]
        kappa = (calibration[0].get("agreement") or {}).get("kappa")

    used = [f[1] for f in found.values() if f]  # the report each suite came from
    newest = max(used, key=lambda r: r["generated_at"])
    rm = router["metrics"]
    am = answers["metrics"]
    report = {
        "generated_at": newest["generated_at"],
        "mode": newest["mode"] if newest.get("mode") in ("live", "replay") else "replay",
        "gates": _gates(reports, {"retrieval", "router", "answers", "redteam"}),
        "retrieval": {
            "sample": False,
            "rows": [
                {
                    "mode": mode,
                    "recall_at_1": m["recall@1"],
                    "recall_at_5": m["recall@5"],
                    "mrr_at_10": m["mrr@10"],
                    "ndcg_at_5": m["ndcg@5"],
                    "p50_ms": m["p50_ms"],
                    "n_questions": n,
                }
                for mode, m, n in rows
            ],
        },
        "router": {
            "sample": False,
            "n_dev": router["splits"]["dev"]["n"],
            "n_blind": router["splits"]["blind"]["n"],
            "accuracy_dev": router["splits"]["dev"]["accuracy"],
            "accuracy_blind": router["splits"]["blind"]["accuracy"],
            "macro_f1": rm["macro_f1"],
            "advice_recall": rm["advice_recall"],
            "false_alarm_rate": rm["false_alarm_rate"],
        },
        "answers": {
            "sample": False,
            "n": answers["n"],
            "citation_validity": am["citation_validity"],
            "numeric_grounding": am["numeric_grounding_rate"],
            "advice_language_absent": am["advice_free_rate"],
            **{k: _judge(answers, k) for k in ("faithfulness", "completeness", "clarity", "boundary")},
        },
        "redteam": {
            "sample": False,
            "rows": [
                {"category": CATEGORY_LABELS.get(c, c), "attacks": v["attacks"], "successes": v["successes"]}
                for c, v in redteam["by_category"].items()
            ],
        },
        "judge_calibration": {"sample": False, "n": n_cal, "kappa": kappa},
    }
    return EvalReport.model_validate(report)
