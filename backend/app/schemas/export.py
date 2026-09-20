"""Export JSON Schema from the pydantic models to contracts/ (`make contracts`).

Files:
  sse_event.schema.json      root = discriminated union of SSE envelopes
  ui_block.schema.json       root = discriminated union of UI blocks
  router_decision.schema.json
  products.schema.json       $defs: Product, Company, MarketEvent
  portfolio.schema.json      $defs: Customer
  tools.schema.json          $defs: <ToolName>Input / <ToolName>Output for every tool
"""

import json
import sys
from pathlib import Path

from pydantic import TypeAdapter
from pydantic.json_schema import models_json_schema

from ..config import REPO_ROOT
from .events import RouterDecision, SSEEvent
from .portfolio import Customer
from .products import Company, MarketEvent, Product
from .tools import TOOL_MODELS
from .ui import UIBlock

DRAFT = "https://json-schema.org/draft/2020-12/schema"


def _write(out: Path, name: str, schema: dict) -> Path:
    path = out / f"{name}.schema.json"
    doc = {"$schema": DRAFT, **schema}
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _defs(models: list[type]) -> dict:
    _, schema = models_json_schema([(m, "validation") for m in models], title="defs")
    return {"title": schema.get("title", "defs"), "$defs": schema["$defs"]}


def export(out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    tool_models = [m for pair in TOOL_MODELS.values() for m in pair]
    return [
        _write(out, "sse_event", TypeAdapter(SSEEvent).json_schema()),
        _write(out, "ui_block", TypeAdapter(UIBlock).json_schema()),
        _write(out, "router_decision", RouterDecision.model_json_schema()),
        _write(out, "products", _defs([Product, Company, MarketEvent])),
        _write(out, "portfolio", _defs([Customer])),
        _write(out, "tools", _defs(tool_models)),
    ]


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT / "contracts"
    for p in export(target):
        print(f"wrote {p.relative_to(REPO_ROOT) if p.is_relative_to(REPO_ROOT) else p}")
