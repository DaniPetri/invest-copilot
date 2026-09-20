"""Evaluation report shown on /evals (GET /api/evals/latest). M7 writes reports in this shape.

Every suite carries `sample`: true means the numbers are illustrative placeholders (frontend fixtures before the
suite has run), false means measured.
"""

from typing import Literal

from pydantic import Field

from .base import Contract


class Gate(Contract):
    name: str
    metric: str
    value: float
    threshold: float
    passed: bool
    sample: bool = False


class RetrievalRow(Contract):
    mode: Literal["bm25", "dense", "hybrid", "hybrid_rerank"]
    recall_at_1: float = Field(ge=0, le=1)
    recall_at_5: float = Field(ge=0, le=1)
    mrr_at_10: float = Field(ge=0, le=1)
    ndcg_at_5: float = Field(ge=0, le=1)
    p50_ms: float = Field(ge=0)
    n_questions: int = Field(ge=1)


class RetrievalSuite(Contract):
    sample: bool = False
    rows: list[RetrievalRow]


class RouterSuite(Contract):
    sample: bool = False
    n_dev: int
    n_blind: int
    accuracy_dev: float = Field(ge=0, le=1)
    accuracy_blind: float = Field(ge=0, le=1)
    macro_f1: float = Field(ge=0, le=1)
    advice_recall: float = Field(ge=0, le=1)
    false_alarm_rate: float = Field(ge=0, le=1)


class JudgeScore(Contract):
    mean: float = Field(ge=1, le=5)
    ci_low: float = Field(ge=1, le=5)
    ci_high: float = Field(ge=1, le=5)


class AnswersSuite(Contract):
    sample: bool = False
    n: int
    citation_validity: float = Field(ge=0, le=1)
    numeric_grounding: float = Field(ge=0, le=1)
    advice_language_absent: float = Field(ge=0, le=1)
    faithfulness: JudgeScore
    completeness: JudgeScore
    clarity: JudgeScore
    boundary: JudgeScore


class RedteamRow(Contract):
    category: str
    attacks: int = Field(ge=0)
    successes: int = Field(ge=0)


class RedteamSuite(Contract):
    sample: bool = False
    rows: list[RedteamRow]


class CalibrationSuite(Contract):
    sample: bool = False
    n: int
    kappa: float | None = Field(description="Cohen's kappa between judge and human; null until the human scores exist")


class EvalReport(Contract):
    generated_at: str
    mode: Literal["live", "replay", "fixture"]
    gates: list[Gate]
    retrieval: RetrievalSuite
    router: RouterSuite
    answers: AnswersSuite
    redteam: RedteamSuite
    judge_calibration: CalibrationSuite
