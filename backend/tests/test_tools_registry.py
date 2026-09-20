"""M4 plumbing: Anthropic tool definitions (strict), result store, executor, POST /api/tools/*, search_kid, MCP."""

import json

import pytest
from fastapi.testclient import TestClient

from app.data.store import Store
from app.main import app, get_tool_context
from app.mcp_server import build_server
from app.schemas.tools import TOOL_MODELS, ScreenInput
from app.tools.base import ToolContext, ToolError
from app.tools.registry import (
    TOOLS,
    ResultStore,
    anthropic_tool_definitions,
    drop_nulls_for_defaults,
    execute,
    strict_input_schema,
)

# What the structured-outputs docs list as unsupported for strict tools (platform.claude.com, structured outputs),
# plus keys we deliberately strip.
FORBIDDEN_KEYS = {
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "minLength", "maxLength",
    "maxItems", "pattern", "default", "title", "oneOf", "allOf", "propertyNames", "$defs_external",
}  # fmt: skip
SUPPORTED_FORMATS = {"date-time", "time", "date", "duration", "email", "hostname", "uri", "ipv4", "ipv6", "uuid"}

SAMPLE_ARGS = {
    "screen_products": {"filter": {"regions": ["Europa"], "savings_plan": True}},
    "portfolio_lookthrough": {"customer_id": "markus"},
    "explain_move": {"customer_id": "markus", "start": "2026-08-01", "end": "2026-08-31"},
    "simulate_savings_plan": {"monthly_eur": 50, "years": 10, "product_ids": ["P03"]},
    "cost_projection": {"product_id": "P07", "monthly_eur": 50, "years": 10},
    "suitability_check": {"customer_id": "elif", "product_id": "P22"},
}


def walk(node, path="$"):
    if isinstance(node, dict):
        yield path, node
        for k, v in node.items():
            yield from walk(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, f"{path}[{i}]")


# ── Anthropic tool definitions ──────────────────────────────────────────────


def test_seven_strict_definitions_with_the_expected_shape():
    defs = anthropic_tool_definitions()
    assert [d["name"] for d in defs] == list(TOOL_MODELS)
    for d in defs:
        assert set(d) == {"name", "description", "strict", "input_schema"}
        assert d["strict"] is True and len(d["description"]) > 60
        assert d["input_schema"]["type"] == "object"


@pytest.mark.parametrize("name", list(TOOL_MODELS))
def test_schemas_only_use_what_strict_mode_accepts(name):
    schema = strict_input_schema(TOOLS[name].input_model)
    defs = schema.get("$defs", {})
    for path, node in walk(schema):
        if "minItems" in node:
            assert node["minItems"] in (0, 1), (name, path)
        if "format" in node:
            assert node["format"] in SUPPORTED_FORMATS, (name, path)
        if "$ref" in node:
            assert node["$ref"].startswith("#/$defs/") and node["$ref"].split("/")[-1] in defs, (name, path)
        if "properties" in node:  # every object: additionalProperties false, every property required
            assert node.get("additionalProperties") is False, (name, path)
            assert node["required"] == list(node["properties"]), (name, path)


@pytest.mark.parametrize("name", list(TOOL_MODELS))
def test_forbidden_keywords_are_absent_as_schema_keywords(name):
    """`minimum` etc. may appear inside `properties` only as a field name, never as a schema keyword."""
    schema = strict_input_schema(TOOLS[name].input_model)

    def check(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("properties", "$defs"):
                    for sub in value.values():
                        check(sub)
                else:
                    assert key not in FORBIDDEN_KEYS, key
                    check(value)
        elif isinstance(node, list):
            for item in node:
                check(item)

    check(schema)


def test_optional_fields_become_required_and_nullable():
    schema = strict_input_schema(TOOLS["simulate_savings_plan"].input_model)
    assert schema["required"] == ["monthly_eur", "years", "product_ids", "weights", "fee_per_execution"]
    for optional in ("product_ids", "weights", "fee_per_execution"):
        types = [s.get("type") for s in schema["properties"][optional]["anyOf"]]
        assert "null" in types
    assert "monthly_eur" not in json.dumps(schema["properties"]["monthly_eur"].get("anyOf", []))  # stays non-null


def test_stripped_constraints_are_described_in_words_and_still_enforced():
    schema = strict_input_schema(TOOLS["simulate_savings_plan"].input_model)
    assert "40" in schema["properties"]["years"]["description"]  # "maximum: 40" moved into the description
    with pytest.raises(ToolError) as e:  # the original constraint is validated server-side
        execute("simulate_savings_plan", {"monthly_eur": 50, "years": 41, "product_ids": ["P03"]}, None)
    assert e.value.code == "invalid" and "years" in e.value.message


def test_nested_models_are_defined_once_and_referenced():
    schema = strict_input_schema(TOOLS["screen_products"].input_model)
    assert "ScreenFilter" in schema["$defs"]
    assert schema["properties"]["filter"] == {"$ref": "#/$defs/ScreenFilter"}
    assert schema["$defs"]["ScreenFilter"]["required"] == list(schema["$defs"]["ScreenFilter"]["properties"])


# ── null handling: strict schemas send null for "not specified" ─────────────


def test_nulls_for_fields_with_defaults_are_dropped_but_real_nulls_are_kept():
    args = {"filter": {"regions": None, "max_sri": 4}, "sort": None, "limit": None}
    cleaned = drop_nulls_for_defaults(args, ScreenInput)
    assert cleaned == {
        "filter": {"regions": None, "max_sri": 4}
    }  # sort/limit fall back to defaults; filter fields stay None
    assert ScreenInput.model_validate(cleaned).limit == 10


def test_the_shape_a_strict_model_sends_is_accepted(ctx):
    strict_call = {
        "filter": {
            "asset_classes": None, "savings_plan": True, "regions": ["Europa"], "sfdr_min": None,
            "exclusions": None, "max_sri": None, "max_ter": 0.003, "distribution": None,
        },
        "sort": None,
        "limit": None,
    }  # fmt: skip
    result = execute("screen_products", strict_call, ctx)
    assert result.ok and result.payload["total_matches"] > 0 and len(result.payload["items"]) <= 10
    sim = execute(
        "simulate_savings_plan",
        {"monthly_eur": 50, "years": 5, "product_ids": ["P03"], "weights": None, "fee_per_execution": None},
        ctx,
    )
    assert sim.payload["seed"] == 20260920


# ── result store and executor ───────────────────────────────────────────────


def test_result_ids_are_sequential_per_request_store(ctx):
    a, b = ResultStore(), ResultStore()
    r1 = execute("suitability_check", SAMPLE_ARGS["suitability_check"], ctx, a)
    r2 = execute("cost_projection", SAMPLE_ARGS["cost_projection"], ctx, a)
    other = execute("suitability_check", SAMPLE_ARGS["suitability_check"], ctx, b)
    assert (r1.result_id, r2.result_id, other.result_id) == ("r1", "r2", "r1")
    assert len(a) == 2 and "r2" in a and "r3" not in a
    assert a.get("r2").payload == r2.payload and a.get("r1").name == "suitability_check"
    with pytest.raises(KeyError, match="r9"):
        a.get("r9")


@pytest.mark.parametrize("name", list(SAMPLE_ARGS))
def test_every_payload_round_trips_through_its_output_model(ctx, name):
    result = execute(name, SAMPLE_ARGS[name], ctx)
    assert result.ok and result.name == name and result.summary
    json.dumps(result.payload)  # plain JSON
    TOOLS[name].output_model.model_validate(result.payload)
    assert result.payload == json.loads(json.dumps(result.payload))


def test_summaries_are_german_and_carry_the_numbers(ctx):
    assert execute("screen_products", SAMPLE_ARGS["screen_products"], ctx).summary == "12 von 40 Produkten passen"
    assert execute("cost_projection", SAMPLE_ARGS["cost_projection"], ctx).summary.startswith("Kosten gesamt 165,38 €")
    assert execute("suitability_check", SAMPLE_ARGS["suitability_check"], ctx).summary.startswith("Ergebnis fail")
    assert "Ereignis" in execute("explain_move", SAMPLE_ARGS["explain_move"], ctx).summary


def test_executor_errors(ctx):
    with pytest.raises(ToolError) as e:
        execute("nope", {}, ctx)
    assert e.value.code == "not_found"
    with pytest.raises(ToolError) as e:
        execute("cost_projection", {"product_id": "P07", "monthly_eur": -5, "years": 10}, ctx)
    assert e.value.code == "invalid"
    with pytest.raises(ToolError) as e:
        execute("cost_projection", {"product_id": "P07", "monthly_eur": 5, "years": 10, "extra": 1}, ctx)
    assert e.value.code == "invalid" and "extra" in e.value.message
    with pytest.raises(ToolError) as e:
        execute("cost_projection", {"product_id": "P99", "monthly_eur": 5, "years": 10}, ctx)
    assert e.value.code == "not_found"


# ── search_kid (needs the retrieval index) ──────────────────────────────────


def test_search_kid_returns_chunks_and_reports_quarantine(indexed_ctx):
    res = execute(
        "search_kid",
        {"query": "Welche Risikoklasse hat der Welt Tech ETF?", "product_ids": ["P22"], "k": 3},
        indexed_ctx,
    )
    assert [c["id"] for c in res.payload["chunks"]][0] == "KID:P22:p1:risikoindikator"
    assert res.payload["quarantined_ids"] == [] and res.summary == "3 Abschnitte gefunden, 0 in Quarantäne"

    attacked = execute(
        "search_kid",
        {"query": "Welt Small Cap Wachstum ETF Sonstige Informationen Fondsvolumen", "product_ids": ["P13"], "k": 10},
        indexed_ctx,
    )
    assert "KID:P13:p2:sonstige_informationen" in attacked.payload["quarantined_ids"]
    assert all(c["flags"] == [] for c in attacked.payload["chunks"])
    assert not any("Ignoriere" in c["text"] for c in attacked.payload["chunks"])  # injection text never leaves the tool


def test_search_kid_accepts_the_strict_null_shape(indexed_ctx):
    res = execute("search_kid", {"query": "Sparplan möglich?", "product_ids": None, "k": None}, indexed_ctx)
    assert len(res.payload["chunks"]) == 5


# ── POST /api/tools/{name} ──────────────────────────────────────────────────


@pytest.fixture
def client(ctx):
    app.dependency_overrides[get_tool_context] = lambda: ctx
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_api_runs_a_tool_and_returns_a_result(client):
    res = client.post("/api/tools/cost_projection", json={"product_id": "P07", "monthly_eur": 50, "years": 10})
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"result_id", "name", "ok", "payload", "summary"}
    assert body["result_id"] == "r1" and body["ok"] is True and body["payload"]["total_eur"] == pytest.approx(165.38)


def test_api_simulation_is_instant_enough_for_the_simulator_screen(client):
    res = client.post("/api/tools/simulate_savings_plan", json={"monthly_eur": 50, "years": 20, "product_ids": ["P03"]})
    assert res.status_code == 200 and res.json()["payload"]["years"][-1] == 20


@pytest.mark.parametrize(
    ("name", "body", "status"),
    [
        ("no_such_tool", {}, 404),
        ("cost_projection", {"product_id": "P99", "monthly_eur": 5, "years": 5}, 404),
        ("suitability_check", {"customer_id": "nobody", "product_id": "P03"}, 404),
        ("cost_projection", {"product_id": "P03", "monthly_eur": 5, "years": 0}, 422),
        ("explain_move", {"customer_id": "markus", "start": "2026-08-31", "end": "2026-08-01"}, 422),
        ("simulate_savings_plan", {"monthly_eur": 50, "years": 5}, 422),
        ("screen_products", {}, 422),
    ],
)
def test_api_error_codes(client, name, body, status):
    res = client.post(f"/api/tools/{name}", json=body)
    assert res.status_code == status and res.json()["detail"]


def test_api_rejects_a_non_object_body(client):
    assert client.post("/api/tools/screen_products", json=[1, 2]).status_code == 422


def test_api_reports_missing_data_as_503(tmp_path):
    app.dependency_overrides[get_tool_context] = lambda: ToolContext(Store(tmp_path / "empty"))
    try:
        res = TestClient(app).post("/api/tools/screen_products", json={"filter": {}})
    finally:
        app.dependency_overrides.clear()
    assert res.status_code == 503 and "make data" in res.json()["detail"]


# ── MCP server ──────────────────────────────────────────────────────────────


async def test_mcp_server_lists_the_seven_tools(ctx):
    server = build_server(ctx)
    tools = await server.list_tools()
    assert [t.name for t in tools] == list(TOOL_MODELS)
    for t in tools:
        assert t.description == TOOLS[t.name].description
        assert "params" in t.inputSchema["properties"]


async def test_mcp_tool_call_returns_structured_output(ctx):
    server = build_server(ctx)
    content, structured = await server.call_tool(
        "suitability_check", {"params": {"customer_id": "elif", "product_id": "P22"}}
    )
    assert structured["verdict"] == "fail" and structured["reasons"][0]["rule"] == "risk"
    assert json.loads(content[0].text) == structured
    _, cost = await server.call_tool(
        "cost_projection", {"params": {"product_id": "P07", "monthly_eur": 50, "years": 10}}
    )
    assert cost["total_eur"] == pytest.approx(165.38)


async def test_mcp_tool_errors_are_reported_to_the_client(ctx):
    from mcp.server.fastmcp.exceptions import ToolError as McpToolError

    server = build_server(ctx)
    with pytest.raises(McpToolError, match="Unknown customer"):
        await server.call_tool("suitability_check", {"params": {"customer_id": "nobody", "product_id": "P22"}})
