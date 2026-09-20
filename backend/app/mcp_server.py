"""MCP server (stdio) exposing the deterministic tools to Claude Desktop, Claude Code or any MCP client.

    uv run python -m app.mcp_server

Each tool takes one argument, `params`, shaped like the tool's input model, and returns its output model.
Claude Desktop entry (claude_desktop_config.json), command `uv`, args:
    ["run", "--project", "backend", "python", "-m", "app.mcp_server"]
"""

from mcp.server.fastmcp import FastMCP

from .data.store import get_store
from .schemas.tools import (
    CostProjectionInput,
    CostProjectionOutput,
    ExplainMoveInput,
    ExplainMoveOutput,
    LookthroughInput,
    LookthroughOutput,
    ScreenInput,
    ScreenOutput,
    SearchKidInput,
    SearchKidOutput,
    SimulateInput,
    SimulateOutput,
    SuitabilityInput,
    SuitabilityOutput,
)
from .tools.base import ToolContext, ToolError
from .tools.registry import TOOLS, ResultStore, execute


def build_server(ctx: ToolContext | None = None) -> FastMCP:
    """One MCP server with the seven tools. `ctx` defaults to the generated data in data/generated."""
    server = FastMCP("invest-copilot")
    state: dict[str, ToolContext] = {}

    def context() -> ToolContext:
        if ctx is not None:
            return ctx
        return state.setdefault("ctx", ToolContext(get_store()))

    def call(name: str, params) -> dict:
        try:
            return execute(name, params.model_dump(mode="json"), context(), ResultStore()).payload
        except ToolError as e:
            raise ValueError(e.message) from None  # surfaces to the client as a tool error

    def register(name: str, fn) -> None:
        server.add_tool(fn, name=name, description=TOOLS[name].description)

    def screen_products(params: ScreenInput) -> ScreenOutput:
        return ScreenOutput.model_validate(call("screen_products", params))

    def search_kid(params: SearchKidInput) -> SearchKidOutput:
        return SearchKidOutput.model_validate(call("search_kid", params))

    def portfolio_lookthrough(params: LookthroughInput) -> LookthroughOutput:
        return LookthroughOutput.model_validate(call("portfolio_lookthrough", params))

    def explain_move(params: ExplainMoveInput) -> ExplainMoveOutput:
        return ExplainMoveOutput.model_validate(call("explain_move", params))

    def simulate_savings_plan(params: SimulateInput) -> SimulateOutput:
        return SimulateOutput.model_validate(call("simulate_savings_plan", params))

    def cost_projection(params: CostProjectionInput) -> CostProjectionOutput:
        return CostProjectionOutput.model_validate(call("cost_projection", params))

    def suitability_check(params: SuitabilityInput) -> SuitabilityOutput:
        return SuitabilityOutput.model_validate(call("suitability_check", params))

    for fn in (
        screen_products,
        search_kid,
        portfolio_lookthrough,
        explain_move,
        simulate_savings_plan,
        cost_projection,
        suitability_check,
    ):
        register(fn.__name__, fn)
    return server


mcp = build_server()

if __name__ == "__main__":
    mcp.run()  # stdio
