# Progress

Claude Code keeps this log. After every milestone: done · how to verify · known gaps · next step.

## M1 · Contracts and skeleton — done

**Done**
- `backend/` uv project (Python 3.12, only SPEC §4 dependencies). `app/config.py` (settings from env / repo-root `.env`, EUR price table, replay by default when no key), `app/main.py` with `GET /api/health` and the dev aid `GET /api/_debug/sse/{fixture}`.
- `backend/app/schemas/`: `products`, `portfolio`, `tools` (input/output for all 7 tools, `ToolResult`, `TOOL_MODELS`), `events` (`RouterDecision`, 11 SSE events as `{event, data}` envelopes), `ui` (11 hydrated `UIBlock`s, discriminated on `type`). All models forbid unknown fields.
- `backend/app/schemas/export.py` writes `contracts/*.schema.json` (6 files).
- `frontend/` Vite + React 19 + TS + Tailwind v4 skeleton, Onest self-hosted, `src/design/tokens.css` from design/README.md, `src/types/contracts.ts` mirror, hand-written schema validator `src/lib/schema.ts` (no ajv, per decision).
- `frontend/fixtures/sse/`: `discover.jsonl`, `depot_august.jsonl`, `advice_refusal.jsonl`. One `{event, data, delay_ms}` per line; `delay_ms` is fixture-only and is stripped before validation.
- `scripts/tasks.py` (stdlib only) + thin `Makefile`: setup, test, contracts, dev implemented; data/ingest/eval/eval-ci/record exit 2 with "not implemented yet (arrives in Mx)".

**How to verify** (from the repo root; `make X` = `uv run python scripts/tasks.py X`)
```
uv run python scripts/tasks.py test        # backend 38 passed, frontend 23 passed
uv run python scripts/tasks.py contracts   # rewrites contracts/*.schema.json; test_contracts fails if they are stale
cd frontend && npm run build
cd backend && uv run uvicorn app.main:app --port 8000
curl localhost:8000/api/health
curl -N "localhost:8000/api/_debug/sse/discover?fast=true"
```

**Known gaps / decisions**
- Fixture product IDs, names and numbers are placeholders. They are made consistent with the generated universe in M8, when the frontend moves to the real API.
- `product_cards` has two optional fields beyond SPEC §9 (`filters`, `total_matches`), needed for the "Das habe ich verstanden" chips in design/02. `attribution` carries `change_eur` and `change_pct`, `cost_breakdown` carries `total_pct_of_contributions` (design/03, design/04). Additive, defaults where optional.
- The model-facing `render_ui` schema (blocks with `result_id` references) is built in M6 (`agent/ui.py`), not here.
- Contract exporter lives at `backend/app/schemas/export.py` (run as `python -m app.schemas.export`), not `scripts/export_contracts.py` as PLAN.md said.
- `PRICE_TABLE_EUR_PER_MTOK` values are placeholders. Verify against the platform.claude.com pricing page in M6.
- SPEC §4 lists `@testing-library/react` only, so `jest-dom` and `user-event` were not added. `httpx` (needed by FastAPI's TestClient) arrives transitively via `anthropic`.
- Risk 1 spike (throwaway script, not committed): fastembed loads `paraphrase-multilingual-MiniLM-L12-v2` (384-d) and Qdrant local mode upserts and queries; the German query "Was kostet der Fonds pro Jahr?" ranks the cost sentence first (0.60 vs 0.18). First model download took ~68 s. Notes for M3: fastembed caches in `%TEMP%\fastembed_cache` by default, so pass an explicit `cache_dir` under `data/generated/`; fastembed serves a quantized ONNX build and warns that pooling changed to mean pooling (fine, but do not pin the old behaviour); HF symlink warning on Windows is harmless.
- Not done from the plan's risk list: the strict-tool-schema helper and live structured-output spike stay with M4/M6, as planned.
- Tests are slow the first time on this machine (vitest cold start ~50 s once, then < 1 s).
- Python 3.12 is provisioned by uv (`backend/.python-version`); the system Python is 3.14.

**Next step**: M2, synthetic universe (`make data`).
