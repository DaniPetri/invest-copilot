# Invest Copilot — build plan

Source of truth: SPEC.md (§13 milestones). Rules: CLAUDE.md. Visual target: design/. Log: PROGRESS.md.
Every milestone ends: tests green → PROGRESS.md → conventional commit → push.
Windows note: every `make X` below is also `uv run python scripts/tasks.py X`. Verify commands are written in that form so they work without `make`.

---

## 1. Milestones

### M1 · Contracts and skeleton
**Files**
- `backend/pyproject.toml` (uv, Python 3.12, only SPEC §4 deps), `backend/app/config.py` (models, price table EUR/1M tokens, `LLM_MODE`, `RERANK`, paths)
- `backend/app/schemas/`: `products.py` (Product, Holding, Company, PriceSeries, MarketEvent), `portfolio.py` (Customer, Profile, Position, Transaction), `tools.py` (input/output model per tool in SPEC §7, `ToolResultEnvelope{result_id,name,payload}`), `events.py` (one model per SSE event, `RouterDecision`), `ui.py` (`UIBlock` discriminated union on `type`, 11 blocks)
- `backend/app/main.py`: FastAPI app, `GET /api/health`
- `scripts/tasks.py` (setup, data, ingest, dev, test, eval, eval-ci, contracts, record), thin `Makefile`
- `scripts/export_contracts.py` → `contracts/*.schema.json`
- `frontend/`: Vite + React 19 + TS + Tailwind v4 skeleton, `src/types/contracts.ts`, `src/design/tokens.css` (from design/README.md), `@fontsource/onest`
- `frontend/fixtures/sse/{discover,depot_august,advice_refusal}.jsonl` (German, realistic, one JSON object per line: `{event, data}`)
- Root: `.gitignore` check, `.env.example` check

**Tests**
- `backend/tests/test_schemas.py`: every event/block round-trips; unknown block type is rejected
- `backend/tests/test_fixtures.py`: each fixture line validates against the pydantic model
- `frontend/src/types/contracts.test.ts`: validates the same fixtures against `contracts/*.schema.json` (hand-written structural validator; ajv is not used, per decision)
- `backend/tests/test_health.py`

**Done when**
```
uv run python scripts/tasks.py test
uv run python scripts/tasks.py contracts && ls contracts/*.schema.json
cd frontend && npm run build
```

### M2 · Synthetic universe
**Files** `backend/app/data/generate.py` (companies, products, ISIN check digit, factor-model prices, 12 events, SRI, customers, transactions), `kid_pdf.py` (reportlab, 2 pages), `store.py` (loaders, cached), `data/generated/` outputs: `companies.json products.json prices.parquet-free CSV/JSON events.json customers.json kid/*.pdf kid_facts.jsonl retrieval.jsonl`.
Functions: `make_companies(rng)`, `make_products(rng, companies)`, `isin_check_digit()`, `simulate_factors(rng, events)`, `nav_from_holdings()`, `sri_from_vol()`, `make_customers()`, `render_kid(product)`, `make_kid_facts()`, `make_retrieval_questions()` (3 phrasings per fact).
**Tests** weights sum to 1 · ISIN check digits valid and prefix `XD` · SRI band edges · each event visible in the affected sector's returns · same seed → same output hash · every PDF has 2 pages and contains its TER string · P13 and P31 contain the injection text, no other PDF does · ≥ 160 retrieval questions.
**Done when**
```
uv run python scripts/tasks.py data     # < 2 min
uv run python scripts/tasks.py test
```

### M3 · Retrieval
**Files** `rag/parse.py`, `rag/chunk.py`, `rag/index.py` (`make ingest`), `rag/search.py`, `rag/injection.py`, `evals/retrieval_quick.py` (ablation table).
**Tests** chunk IDs stable across runs · product filter · P13/P31 chunks flagged, others not · all four modes return ranked chunks · hybrid recall@5 ≥ 0.85 on `retrieval.jsonl`.
**Done when**
```
uv run python scripts/tasks.py ingest
cd backend && uv run python ../evals/retrieval_quick.py    # prints the ablation table, exits 1 below the gate
cd backend && uv run pytest tests/test_retrieval.py -q
```

### M4 · Tools and MCP
**Files** `tools/{screener,suitability,costs,lookthrough,attribution,montecarlo}.py`, `tools/registry.py` (Anthropic tool defs, `strict:true`, `additionalProperties:false`, request-scoped `ResultStore`), `POST /api/tools/{name}` in `main.py`, `mcp_server.py` (FastMCP).
**Tests** unit per tool · hypothesis: percentiles monotonic per year, exposures sum to 1, overlap symmetric and ≤ 1, costs ≥ 0, simulation deterministic per seed · Monte Carlo < 300 ms for 5,000 paths (30-year case measured separately, see risk 5) · attribution finds the ground-truth event for Markus in Aug 2026 · MCP lists 7 tools.
**Done when**
```
cd backend && uv run pytest tests/test_tools*.py tests/test_mcp.py -q
curl -s -X POST localhost:8000/api/tools/portfolio_lookthrough -H "content-type: application/json" -d '{"customer_id":"markus"}'
```

### M5 · Frontend in fixture mode
**Files** `frontend/src/{App.tsx, screens/*, blocks/*, blocks/registry.tsx, components/*, lib/sse.ts, lib/api.ts, lib/format.ts}`, `frontend/fixtures/api/*.json` (customers, products, portfolio, tool results, evals report, created from `contracts/`).
**Tests** SSE parser (split mid-line, multi-line data, error event) · registry renders every fixture block and ignores unknown types · chat screen renders a full fixture stream · German number formatting.
**Done when**
```
cd frontend && npm test -- --run && npm run build
VITE_USE_FIXTURES=1 npm run dev     # all 6 screens + trace panel work with no backend
```

### M6 · Agent
**Files** `agent/llm.py`, `agent/router.py`, `agent/orchestrator.py`, `agent/prompts.py`, `agent/ui.py`, `guardrails/{pii,advice,citations,numbers,pipeline}.py`, `tracing/{store,events}.py`, `POST /api/chat`, `GET /api/traces/{id}`, `backend/tests/fakes.py` (scripted fake LLM).
**Tests (no network)** event order · hallucinated number flagged · citation to non-retrieved chunk fails and triggers repair · P13 injection never reaches model context · advice request → handoff, zero tool calls · PII redacted before the LLM call · unknown UI block rejected · cost accounting from the price table · replay client hit/miss.
**Done when**
```
cd backend && uv run pytest -q
LLM_MODE=live curl -N -X POST localhost:8000/api/chat -H "content-type: application/json" -d '{"customer_id":"markus","message":"Warum ist mein Depot im August gefallen?"}'
```

### M7 · Evals
**Files** `evals/{datasets/*.jsonl, metrics.py, judge.py, run.py, thresholds.yaml, CHANGELOG.md, reports/}` + `evals/tests/`.
**Tests** metrics against hand-computed examples (accuracy, macro-F1, recall@k, MRR, nDCG, bootstrap CI, Cohen's κ) · dataset shape and counts (80 router = 60/20, 12 advice, 8 injection, 6 OOS; 30 answers; 20 redteam; 12 calibration) · run.py exits 1 when a gate fails (forced by a fixture threshold).
**Done when**
```
uv run pytest evals -q
uv run python -m evals.run --suite retrieval --mode replay ; cat evals/reports/latest.md
uv run python scripts/tasks.py eval-ci
```

### M8 · Integration
`make contracts`; frontend defaults to the real API (`VITE_USE_FIXTURES=0`), fix any mismatches; `scripts/demo_questions.yaml` (8 questions); `make record`; spec-reviewer on M5, M6, M8.
**Done when**
```
# with ANTHROPIC_API_KEY unset:
uv run python scripts/tasks.py dev      # then run scripts/smoke_demo.py: all 8 questions return a done event
uv run python scripts/tasks.py test && uv run python scripts/tasks.py eval-ci
```

### M9 · Ship
Docker (`docker-compose.yml`, Dockerfiles), `.devcontainer/`, `.github/workflows/ci.yml`, README, CI green, repo public, tag v0.1.0.
**Done when** `gh run watch` is green; `git tag v0.1.0`; `docker compose up` serves :5173; a clean clone runs `setup && data && dev` in replay mode.

---

## 2. Build order (single session, sequential)

One session does everything, in this order. Each milestone starts only when the previous one is pushed.

1. **M1** Contracts and skeleton
2. **M2** Synthetic universe
3. **M3** Retrieval
4. **M4** Tools and MCP
5. **M5** Frontend in fixture mode
6. **M6** Agent
7. **M7** Evals
8. **M8** Integration
9. **M9** Ship

Why this order: contracts first because everything else builds on them; data before retrieval and tools; the frontend (M5) works on fixtures, so it needs only M1; the agent (M6) needs retrieval and tools; evals (M7) need the agent to run the answers and red-team suites; integration and shipping come last.

Rules between milestones
- Contract changes (`backend/app/schemas`, `frontend/src/types/contracts.ts`, `frontend/fixtures/sse`) happen together, followed by `make contracts` and both test suites.
- End of every milestone: tests green → update PROGRESS.md (done · how to verify · known gaps · next step) → conventional commit → push.
- When the context gets long, or at a natural break (suggested after M2, M4, M6 and M8): update PROGRESS.md, then tell you to run `/clear`. After the clear, resume with: "Read PROGRESS.md and PLAN.md and continue with the next step."
- New dependencies beyond SPEC §4: ask before adding.

---

## 3. Cut list (drop in this order when behind)

1. `/evals` polish, judge calibration set (12 items), `hybrid_rerank` mode (`RERANK=1` optional in SPEC anyway).
2. Optional screens: profile dialog (07), Invest-Coach `learn` UI (08), animation staggering.
3. Docker + devcontainer (keep CI).
4. `explain_move` UI marker interaction on `/depot` → fall back to a static list of events.
5. Answers eval LLM judge (keep deterministic checks: citation validity, numeric grounding, advice language).
6. MCP server (keep `/api/tools/*`).
7. Router eval blind split (keep dev).
Never cut: numbers-from-code, guardrails on planted cases, replay mode, retrieval ablation, red-team gate, KI labels and footer, disclaimer.

---

## 4. Top technical risks and early de-risking

| # | Risk | De-risk (by when) |
|---|---|---|
| 1 | **Qdrant local mode + fastembed on Windows**: model download size/time, file locking of `data/generated/qdrant`, `TextCrossEncoder` availability | M1: add a 20-line spike test that embeds a German sentence and upserts/queries a local collection. Pin versions in `uv.lock`. Cache the model dir. Keep BM25-only as a fallback so the ablation still prints. Close the client explicitly in tests (one client per path) |
| 2 | **Structured outputs / strict tools parameters** (`output_config`, `strict`) may not match the SDK | Before M6, fetch the docs from platform.claude.com, write a 30-line live spike with Haiku and one strict tool, and pin the SDK version. Encode the working shapes in `agent/llm.py` with a regression test using the fake LLM. Never guess a parameter |
| 3 | **SSE over POST**: `EventSource` cannot POST; chunk boundaries split lines; `sse-starlette` buffers or adds pings | M5 starts with `lib/sse.ts` and its split-chunk unit tests. In M1, add `GET /api/_debug/sse` (dev only) emitting a fixture, and check with curl `-N`. Fixture mode shares the same parser |
| 4 | **Strict tool schemas from pydantic**: `$defs`, `anyOf` nulls, `default`, `additionalProperties:false` and unsupported keywords are rejected in strict mode | M4: a `to_strict_schema()` helper that inlines `$ref`, forces `additionalProperties:false`, marks all fields required (nullable instead of optional), plus a test that walks every schema for forbidden keywords. Verified live in the spike of risk 2 |
| 5 | **Monte Carlo speed**: 5,000 paths × 30 years × 252 days ≈ 38 M draws; block bootstrap must be vectorised (< 300 ms) | Build in M4 with month-level accumulation: sample block starts as one int array, cumulative-sum via `np.add.reduceat`/reshape, compute yearly percentiles with one `np.percentile` call. Benchmark test asserts the spec'd 300 ms on the default case (≤ 20 years) and records the 30-year time. If over, resample block-monthly instead of daily and document it |
| 6 | **Cassette determinism**: hashing the normalised request breaks whenever the prompt text or tool ordering changes | Normalise (sorted keys, drop volatile ids/timestamps), cassette-miss raises a clear error naming the hash and request diff, and `make record` is idempotent. Lock prompt text before recording in M8; re-record after any prompt change |
| 7 | **Numeric grounding false positives** (German formats `1.234,56`, percentages, years, dates) | Build `guardrails/numbers.py` test table first: formats, rounding tolerance, whitelist for years, page numbers, "1–7" SRI scale. Start the guard in `flag` mode, not `fail`, until answers-eval shows the false-positive rate |

## 5. Assumptions (no blocking contradictions found)

- Design 11 and 12 show extra controls (engine toggle Claude/Regeln, prompt version v1/v2, "Ablauf" step titles). SPEC §10 does not list them, so the trace panel follows SPEC: live event list with numbered steps like design/11, plus the "Replay-Modus" badge. The engine/prompt toggles are out of scope.
- design/12 shows a router-style table. `/evals` renders the four suites from SPEC §11 in the same table style.
- SPEC §4 names the embedding model with a `sentence-transformers/` prefix but does not list `sentence-transformers` as a dependency. Use it through fastembed only.
- Live mode needs `ANTHROPIC_API_KEY`; recording cassettes (M8) needs it once. Everything else runs without a key.
