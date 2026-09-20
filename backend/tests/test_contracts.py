"""contracts/*.schema.json must match what the pydantic models export right now."""

import json

from app.schemas.export import export

from .conftest import CONTRACT_DIR

EXPECTED = {"sse_event", "ui_block", "router_decision", "products", "portfolio", "tools", "evals"}


def test_contract_files_exist_and_are_current(tmp_path):
    written = export(tmp_path)
    assert {p.name.removesuffix(".schema.json") for p in written} == EXPECTED
    for fresh in written:
        committed = CONTRACT_DIR / fresh.name
        assert committed.exists(), f"{fresh.name} missing: run make contracts"
        assert json.loads(committed.read_text(encoding="utf-8")) == json.loads(fresh.read_text(encoding="utf-8")), (
            f"{fresh.name} is stale: run make contracts"
        )
