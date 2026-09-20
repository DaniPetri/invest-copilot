"""Input and output models for the seven deterministic tools (SPEC §7).

Optional inputs are `X | None = None` so the registry can turn them into required-nullable
fields for strict tool schemas later.
"""

from datetime import date
from typing import Any, Literal

from pydantic import Field

from .base import Contract
from .products import AssetClass, Distribution, Exclusion, MarketEvent, Region

ToolName = Literal[
    "screen_products",
    "search_kid",
    "portfolio_lookthrough",
    "explain_move",
    "simulate_savings_plan",
    "cost_projection",
    "suitability_check",
]

Verdict = Literal["pass", "warn", "fail"]


class ToolResult(Contract):
    """A stored tool result. UI blocks reference `result_id`; the server hydrates from `payload`."""

    result_id: str
    name: ToolName
    ok: bool
    payload: dict[str, Any]
    summary: str


# ── screen_products ─────────────────────────────────────────────────────────


class ScreenFilter(Contract):
    asset_classes: list[AssetClass] | None = None
    savings_plan: bool | None = None
    regions: list[Region] | None = None
    sfdr_min: Literal[6, 8, 9] | None = None
    exclusions: list[Exclusion] | None = None
    max_sri: int | None = Field(default=None, ge=1, le=7)
    max_ter: float | None = Field(default=None, ge=0)
    distribution: Distribution | None = None


class ScreenInput(Contract):
    filter: ScreenFilter
    sort: Literal["ter", "sri", "fund_size", "name"] = "ter"
    limit: int = Field(default=10, ge=1, le=40)


class ScreenItem(Contract):
    product_id: str
    name: str
    isin: str
    asset_class: AssetClass
    region: Region
    sfdr: Literal[6, 8, 9]
    sri: int = Field(ge=1, le=7)
    ter: float
    distribution: Distribution
    savings_plan_min_eur: float | None
    why_matched: list[str]


class ScreenOutput(Contract):
    total_matches: int
    items: list[ScreenItem]


# ── search_kid ──────────────────────────────────────────────────────────────


class SearchKidInput(Contract):
    query: str
    product_ids: list[str] | None = None
    k: int = Field(default=5, ge=1, le=20)


class Chunk(Contract):
    id: str = Field(description="KID:{product_id}:p{page}:{section_slug}[:{n}]")
    product_id: str
    page: int = Field(ge=1)
    section: str
    text: str
    score: float
    flags: list[str] = Field(default_factory=list)


class SearchKidOutput(Contract):
    chunks: list[Chunk]
    quarantined_ids: list[str] = Field(default_factory=list)


# ── portfolio_lookthrough ───────────────────────────────────────────────────


class LookthroughInput(Contract):
    customer_id: str


class ExposureRow(Contract):
    key: str
    label: str
    weight: float = Field(ge=0, le=1)


class OverlapPair(Contract):
    product_a: str
    product_b: str
    overlap: float = Field(ge=0, le=1, description="Sum over companies of min(w_a, w_b)")


class LookthroughOutput(Contract):
    customer_id: str
    n_products: int
    n_companies: int
    by_company: list[ExposureRow]
    by_sector: list[ExposureRow]
    by_country: list[ExposureRow]
    overlaps: list[OverlapPair]
    hhi: float
    top10_share: float
    flags: list[str] = Field(description="e.g. single_company_over_5pct, top10_over_30pct")


# ── explain_move ────────────────────────────────────────────────────────────


class ExplainMoveInput(Contract):
    customer_id: str
    start: date
    end: date


class AttributionRow(Contract):
    product_id: str
    name: str
    pnl_eur: float
    pnl_pct: float
    contribution_pct: float = Field(description="Share of total portfolio move, in percentage points")


class ExplainMoveOutput(Contract):
    customer_id: str
    start: date
    end: date
    start_value_eur: float
    end_value_eur: float
    change_eur: float
    change_pct: float
    rows: list[AttributionRow]
    events: list[MarketEvent]


# ── simulate_savings_plan ───────────────────────────────────────────────────


class ProductWeight(Contract):
    product_id: str
    weight: float = Field(ge=0, le=1)


class SimulateInput(Contract):
    monthly_eur: float = Field(gt=0)
    years: int = Field(ge=1, le=40)
    product_ids: list[str] | None = Field(default=None, description="Equal weights")
    weights: list[ProductWeight] | None = Field(default=None, description="Explicit weights, sum to 1")
    fee_per_execution: float = Field(default=1.0, ge=0)


class SimulateOutput(Contract):
    years: list[int]
    p5: list[float]
    p25: list[float]
    p50: list[float]
    p75: list[float]
    p95: list[float]
    contributions: list[float]
    prob_below_contributions: float = Field(ge=0, le=1)
    total_contributions: float
    total_costs: float
    kest_estimate: float = Field(description="27.5 % on median gains, simplified")
    n_paths: int
    seed: int


# ── cost_projection ─────────────────────────────────────────────────────────


class CostProjectionInput(Contract):
    product_id: str
    monthly_eur: float = Field(gt=0)
    years: int = Field(ge=1, le=40)
    fee_per_execution: float = Field(default=1.0, ge=0, description="Savings plan fee per monthly execution, EUR")


class CostRow(Contract):
    label: str
    amount_eur: float = Field(ge=0)


class CostYear(Contract):
    year: int
    ter_eur: float = Field(ge=0)
    fees_eur: float = Field(ge=0)
    entry_eur: float = Field(ge=0)
    cumulative_eur: float = Field(ge=0)


class CostProjectionOutput(Contract):
    product_id: str
    total_contributions_eur: float
    by_year: list[CostYear]
    rows: list[CostRow]
    total_eur: float
    total_pct_of_contributions: float


# ── suitability_check ───────────────────────────────────────────────────────


class SuitabilityInput(Contract):
    customer_id: str
    product_id: str


class SuitabilityReason(Contract):
    rule: Literal["risk", "knowledge", "experience", "horizon", "sustainability"]
    status: Verdict
    text: str
    profile_field: str


class SuitabilityOutput(Contract):
    customer_id: str
    product_id: str
    verdict: Verdict
    reasons: list[SuitabilityReason]


TOOL_MODELS: dict[str, tuple[type[Contract], type[Contract]]] = {
    "screen_products": (ScreenInput, ScreenOutput),
    "search_kid": (SearchKidInput, SearchKidOutput),
    "portfolio_lookthrough": (LookthroughInput, LookthroughOutput),
    "explain_move": (ExplainMoveInput, ExplainMoveOutput),
    "simulate_savings_plan": (SimulateInput, SimulateOutput),
    "cost_projection": (CostProjectionInput, CostProjectionOutput),
    "suitability_check": (SuitabilityInput, SuitabilityOutput),
}
