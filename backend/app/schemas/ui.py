"""Hydrated UI blocks (SPEC §9): what the client receives in the `ui` event.

The model-facing `render_ui` schema, where blocks reference `result_id`s and chunk IDs, is built in
M6 (agent/ui.py); hydration turns those references into these blocks.
"""

from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

from .base import Contract
from .products import MarketEvent
from .tools import (
    AttributionRow,
    CostRow,
    ExposureRow,
    ScreenItem,
    SuitabilityReason,
    Verdict,
)


class FilterChip(Contract):
    key: str
    label: str
    active: bool = True


class CitationItem(Contract):
    chunk_id: str
    product_name: str
    page: int = Field(ge=1)
    section: str
    snippet: str


class OverlapProduct(Contract):
    product_id: str
    name: str


class HandoffAction(Contract):
    id: str
    label: str


class TextBlock(Contract):
    type: Literal["text"] = "text"
    markdown: str
    citations: list[str] = Field(default_factory=list, description="Chunk IDs cited in the text")


class ProductCardsBlock(Contract):
    type: Literal["product_cards"] = "product_cards"
    items: list[ScreenItem]
    filters: list[FilterChip] = Field(default_factory=list, description="'Das habe ich verstanden' chips")
    total_matches: int | None = None


class RiskMeterBlock(Contract):
    type: Literal["risk_meter"] = "risk_meter"
    sri: int = Field(ge=1, le=7)


class FanChartBlock(Contract):
    type: Literal["fan_chart"] = "fan_chart"
    years: list[int]
    p5: list[float]
    p25: list[float]
    p50: list[float]
    p75: list[float]
    p95: list[float]
    contributions: list[float]


class ExposureBarsBlock(Contract):
    type: Literal["exposure_bars"] = "exposure_bars"
    dimension: Literal["sector", "country", "company"]
    rows: list[ExposureRow]


class OverlapMatrixBlock(Contract):
    type: Literal["overlap_matrix"] = "overlap_matrix"
    products: list[OverlapProduct]
    matrix: list[list[float]]


class AttributionBlock(Contract):
    type: Literal["attribution"] = "attribution"
    rows: list[AttributionRow]
    events: list[MarketEvent]
    change_eur: float
    change_pct: float


class CostBreakdownBlock(Contract):
    type: Literal["cost_breakdown"] = "cost_breakdown"
    rows: list[CostRow]
    total: float
    total_pct_of_contributions: float | None = None


class SuitabilityBlock(Contract):
    type: Literal["suitability"] = "suitability"
    verdict: Verdict
    reasons: list[SuitabilityReason]


class HandoffBlock(Contract):
    type: Literal["handoff"] = "handoff"
    reason: str
    actions: list[HandoffAction]


class CitationsBlock(Contract):
    type: Literal["citations"] = "citations"
    items: list[CitationItem]


UIBlock = Annotated[
    TextBlock
    | ProductCardsBlock
    | RiskMeterBlock
    | FanChartBlock
    | ExposureBarsBlock
    | OverlapMatrixBlock
    | AttributionBlock
    | CostBreakdownBlock
    | SuitabilityBlock
    | HandoffBlock
    | CitationsBlock,
    Field(discriminator="type"),
]

UIBlockAdapter: TypeAdapter[UIBlock] = TypeAdapter(UIBlock)
