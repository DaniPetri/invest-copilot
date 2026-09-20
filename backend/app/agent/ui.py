"""The model-facing `render_ui` schema and block hydration (SPEC §8).

The model composes an answer from a whitelist of blocks. Blocks carry *references* (`result_id`, `product_id`),
never data: `hydrate` replaces every reference with the numbers stored by the tools of this request and returns
the client-facing blocks of `schemas/ui.py`. Unknown block types and unknown references are rejected.
"""

from typing import Annotated, Literal

from pydantic import Field

from ..schemas.base import Contract

HandoffActionId = Literal["filter_search", "simulate", "book_advisor"]


class RText(Contract):
    type: Literal["text"]
    markdown: str = Field(description="German, du-form. Cite KID passages inline as [[cite:CHUNK_ID]].")


class RProductCards(Contract):
    type: Literal["product_cards"]
    result_id: str = Field(description="result_id of a screen_products call")
    product_ids: list[str] | None = Field(description="Show only these products, in this order; null = all hits")


class RRiskMeter(Contract):
    type: Literal["risk_meter"]
    product_id: str


class RFanChart(Contract):
    type: Literal["fan_chart"]
    result_id: str = Field(description="result_id of a simulate_savings_plan call")


class RExposureBars(Contract):
    type: Literal["exposure_bars"]
    result_id: str = Field(description="result_id of a portfolio_lookthrough call")
    dimension: Literal["sector", "country", "company"]


class ROverlapMatrix(Contract):
    type: Literal["overlap_matrix"]
    result_id: str = Field(description="result_id of a portfolio_lookthrough call")


class RAttribution(Contract):
    type: Literal["attribution"]
    result_id: str = Field(description="result_id of an explain_move call")


class RCostBreakdown(Contract):
    type: Literal["cost_breakdown"]
    result_id: str = Field(description="result_id of a cost_projection call")


class RSuitability(Contract):
    type: Literal["suitability"]
    result_id: str = Field(description="result_id of a suitability_check call")


class RHandoff(Contract):
    type: Literal["handoff"]
    reason: str = Field(description="One German sentence: why a human adviser is the right contact")
    actions: list[HandoffActionId]


RBlock = Annotated[
    RText
    | RProductCards
    | RRiskMeter
    | RFanChart
    | RExposureBars
    | ROverlapMatrix
    | RAttribution
    | RCostBreakdown
    | RSuitability
    | RHandoff,
    Field(discriminator="type"),
]


class RenderUIInput(Contract):
    blocks: list[RBlock] = Field(min_length=1, description="Answer blocks in reading order; start with one text block")


def render_ui_tool_definition() -> dict:
    """The final tool. It is the only tool of the last request (all eight strict schemas together exceed the
    API's grammar limit; checked live), and the request forces it with `tool_choice`."""
    from ..tools.registry import strict_input_schema

    return {
        "name": "render_ui",
        "description": (
            "Deliver the final answer as blocks. Blocks reference tool results by result_id; the server fills in "
            "all data. Start with one short text block, then add the blocks that show the data."
        ),
        "strict": True,
        "input_schema": strict_input_schema(RenderUIInput),
    }
