"""search_kid: hybrid retrieval over the KID chunks (SPEC §6/§7), as a tool."""

from ..schemas.tools import SearchKidInput, SearchKidOutput
from .base import ToolContext


def search_kid(inp: SearchKidInput, ctx: ToolContext) -> SearchKidOutput:
    """Returns cited chunks. Chunks flagged as possible injection are quarantined: never returned, but their IDs are
    listed in `quarantined_ids` so the trace can report them."""
    return ctx.index.retrieve(inp.query, inp.product_ids, inp.k, mode="hybrid")


def summarize(out: SearchKidOutput, ctx: ToolContext) -> str:
    return f"{len(out.chunks)} Abschnitte gefunden, {len(out.quarantined_ids)} in Quarantäne"
