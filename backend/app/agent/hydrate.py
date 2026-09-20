"""Hydration (SPEC §8): the model's reference blocks become client blocks filled from stored tool results.

The model never supplies data. A block says "product cards of result r1"; this module reads r1 and builds the block
that the frontend renders. Unknown references, results of the wrong kind and unknown block types are rejected; all
problems are collected and raised together so one repair round can fix them.
"""

from typing import Any

from ..data.store import Store
from ..fmt import de_pct
from ..guardrails.citations import cited_ids
from ..schemas.tools import (
    AttributionRow,
    CostRow,
    ExposureRow,
    ScreenItem,
    SuitabilityReason,
    ToolResult,
)
from ..schemas.ui import (
    AttributionBlock,
    CitationItem,
    CitationsBlock,
    CostBreakdownBlock,
    ExposureBarsBlock,
    FanChartBlock,
    FilterChip,
    HandoffAction,
    HandoffBlock,
    OverlapMatrixBlock,
    OverlapProduct,
    ProductCardsBlock,
    RiskMeterBlock,
    SuitabilityBlock,
    TextBlock,
    UIBlock,
)
from ..tools.registry import ResultStore
from .prompts import HANDOFF_LABELS
from .ui import RenderUIInput

EXPECTED_TOOL = {
    "product_cards": "screen_products",
    "fan_chart": "simulate_savings_plan",
    "exposure_bars": "portfolio_lookthrough",
    "overlap_matrix": "portfolio_lookthrough",
    "attribution": "explain_move",
    "cost_breakdown": "cost_projection",
    "suitability": "suitability_check",
}
DIMENSION_KEY = {"sector": "by_sector", "country": "by_country", "company": "by_company"}
EXPOSURE_ROWS = 10
SNIPPET_CHARS = 200


class HydrationError(Exception):
    """The blocks reference something that does not exist or has the wrong kind. `problems` go back to the model."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def parse_render_input(raw: dict[str, Any]) -> RenderUIInput:
    """Validate the model's `render_ui` input. Unknown block types or fields raise pydantic.ValidationError."""
    return RenderUIInput.model_validate(raw)


def screen_filter_chips(args: dict[str, Any]) -> list[FilterChip]:
    """'Das habe ich verstanden' chips, built from the arguments the screener actually ran with."""
    f = args.get("filter") or {}
    chips: list[FilterChip] = []
    if f.get("savings_plan"):
        chips.append(FilterChip(key="savings_plan", label="Sparplan-fähig"))
    for ac in f.get("asset_classes") or []:
        label = {"equity_etf": "Nur ETFs", "equity_fund": "Aktienfonds", "bond_fund": "Anleihenfonds"}.get(ac, ac)
        chips.append(FilterChip(key="asset_class", label=label))
    for region in f.get("regions") or []:
        chips.append(FilterChip(key="region", label=f"Region: {region}"))
    if f.get("sfdr_min"):
        chips.append(FilterChip(key="sfdr_min", label=f"Nachhaltig (mindestens Art. {f['sfdr_min']})"))
    for ex in f.get("exclusions") or []:
        chips.append(FilterChip(key="exclusions", label=f"Ohne {ex}"))
    if f.get("max_sri"):
        chips.append(FilterChip(key="max_sri", label=f"Risiko höchstens {f['max_sri']} von 7"))
    if f.get("max_ter") is not None:
        chips.append(FilterChip(key="max_ter", label=f"Kosten höchstens {de_pct(f['max_ter'])} p. a."))
    if f.get("distribution"):
        chips.append(FilterChip(key="distribution", label=str(f["distribution"]).capitalize()))
    return chips


def hydrate(
    blocks: list[Any],
    results: ResultStore,
    args_by_result: dict[str, dict[str, Any]],
    store: Store,
) -> list[UIBlock]:
    """Client blocks for the model's reference blocks, plus a citations block for every KID chunk cited in text."""
    problems: list[str] = []
    out: list[UIBlock] = []

    def result_for(block: Any) -> ToolResult | None:
        rid = block.result_id
        if rid not in results:
            available = [r.result_id for r in results.all()]
            problems.append(f"{block.type}: unknown result_id {rid!r} (available: {available})")
            return None
        res = results.get(rid)
        want = EXPECTED_TOOL[block.type]
        if res.name != want:
            problems.append(f"{block.type} needs a {want} result, but {rid} is from {res.name}")
            return None
        return res

    for block in blocks:
        t = block.type
        if t == "text":
            out.append(TextBlock(markdown=block.markdown, citations=cited_ids(block.markdown)))
        elif t == "handoff":
            actions = [HandoffAction(id=a, label=HANDOFF_LABELS[a]) for a in dict.fromkeys(block.actions)]
            out.append(HandoffBlock(reason=block.reason, actions=actions))
        elif t == "risk_meter":
            try:
                out.append(RiskMeterBlock(sri=store.product(block.product_id).sri))
            except KeyError:
                problems.append(f"risk_meter: unknown product_id {block.product_id!r}")
        elif (res := result_for(block)) is None:
            continue
        elif t == "product_cards":
            items = [ScreenItem.model_validate(i) for i in res.payload["items"]]
            if block.product_ids is not None:
                by_id = {i.product_id: i for i in items}
                unknown = [p for p in block.product_ids if p not in by_id]
                if unknown:
                    problems.append(f"product_cards: {unknown} are not in {res.result_id}")
                    continue
                items = [by_id[p] for p in block.product_ids]
            out.append(
                ProductCardsBlock(
                    items=items,
                    filters=screen_filter_chips(args_by_result.get(res.result_id, {})),
                    total_matches=res.payload["total_matches"],
                )
            )
        elif t == "fan_chart":
            p = res.payload
            out.append(FanChartBlock(**{k: p[k] for k in ("years", "p5", "p25", "p50", "p75", "p95", "contributions")}))
        elif t == "exposure_bars":
            rows = res.payload[DIMENSION_KEY[block.dimension]][:EXPOSURE_ROWS]
            out.append(ExposureBarsBlock(dimension=block.dimension, rows=[ExposureRow.model_validate(r) for r in rows]))
        elif t == "overlap_matrix":
            ids = sorted({pid for o in res.payload["overlaps"] for pid in (o["product_a"], o["product_b"])})
            if len(ids) < 2:
                problems.append(f"overlap_matrix: {res.result_id} has fewer than two products to compare")
                continue
            pos = {pid: i for i, pid in enumerate(ids)}
            matrix = [[1.0 if i == j else 0.0 for j in range(len(ids))] for i in range(len(ids))]
            for o in res.payload["overlaps"]:
                a, b = pos[o["product_a"]], pos[o["product_b"]]
                matrix[a][b] = matrix[b][a] = o["overlap"]
            products = [OverlapProduct(product_id=pid, name=store.product(pid).name) for pid in ids]
            out.append(OverlapMatrixBlock(products=products, matrix=matrix))
        elif t == "attribution":
            p = res.payload
            out.append(
                AttributionBlock(
                    rows=[AttributionRow.model_validate(r) for r in p["rows"]],
                    events=p["events"],
                    change_eur=p["change_eur"],
                    change_pct=p["change_pct"],
                )
            )
        elif t == "cost_breakdown":
            p = res.payload
            out.append(
                CostBreakdownBlock(
                    rows=[CostRow.model_validate(r) for r in p["rows"]],
                    total=p["total_eur"],
                    total_pct_of_contributions=p["total_pct_of_contributions"],
                )
            )
        elif t == "suitability":
            p = res.payload
            reasons = [SuitabilityReason.model_validate(r) for r in p["reasons"]]
            out.append(SuitabilityBlock(verdict=p["verdict"], reasons=reasons))
        else:  # unreachable while RBlock and this chain agree; the backstop for "reject unknown block types"
            problems.append(f"unknown block type {t!r}")

    if problems:
        raise HydrationError(problems)
    if citations := citation_items(out, results, store):
        out.append(CitationsBlock(items=citations))
    return out


def citation_items(blocks: list[UIBlock], results: ResultStore, store: Store) -> list[CitationItem]:
    """One item per retrieved KID chunk cited in a text block. Unknown IDs are skipped here; the citation guardrail
    fails the answer for them."""
    chunks: dict[str, dict[str, Any]] = {}
    for res in results.all():
        if res.name == "search_kid":
            for c in res.payload["chunks"]:
                chunks[c["id"]] = c
    items: list[CitationItem] = []
    for cid in dict.fromkeys(c for b in blocks if b.type == "text" for c in b.citations):
        if c := chunks.get(cid):
            text = " ".join(c["text"].split())
            snippet = text if len(text) <= SNIPPET_CHARS else text[: SNIPPET_CHARS - 1].rstrip() + "…"
            name = store.product(c["product_id"]).name
            items.append(
                CitationItem(chunk_id=cid, product_name=name, page=c["page"], section=c["section"], snippet=snippet)
            )
    return items
