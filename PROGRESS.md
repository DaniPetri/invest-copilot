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
- `PRICE_TABLE_EUR_PER_MTOK` values were placeholders in M1; checked against the pricing page in M6 (see M6, "USD to EUR rate" below).
- SPEC §4 lists `@testing-library/react` only, so `jest-dom` and `user-event` were not added. `httpx` (needed by FastAPI's TestClient) arrives transitively via `anthropic`.
- Risk 1 spike (throwaway script, not committed): fastembed loads `paraphrase-multilingual-MiniLM-L12-v2` (384-d) and Qdrant local mode upserts and queries; the German query "Was kostet der Fonds pro Jahr?" ranks the cost sentence first (0.60 vs 0.18). First model download took ~68 s. Notes for M3: fastembed caches in `%TEMP%\fastembed_cache` by default, so pass an explicit `cache_dir` under `data/generated/`; fastembed serves a quantized ONNX build and warns that pooling changed to mean pooling (fine, but do not pin the old behaviour); HF symlink warning on Windows is harmless.
- Not done from the plan's risk list: the strict-tool-schema helper and live structured-output spike stay with M4/M6, as planned.
- Tests are slow the first time on this machine (vitest cold start ~50 s once, then < 1 s).
- Python 3.12 is provisioned by uv (`backend/.python-version`); the system Python is 3.14.

## M2 · Synthetic universe — done

**Done**
- `backend/app/data/generate.py`: seed 20260920, one `generate(out)` call builds everything (about 2 s). 150 companies (15 countries, 11 sectors, 10 tech mega-caps), 64 synthetic bond and money-market issuers, 40 products (24 ETFs, 8 active, 4 bond, 2 mixed, 2 money market) with `XD` ISINs and valid check digits, factor-model prices for 1,304 business days (2021-09-01 to 2026-08-31) with the 12 events injected, SRI from the PRIIPs volatility bands, 3 personas, retrieval ground truth, `manifest.json` (sha256 per file plus one overall hash).
- `backend/app/data/kid_pdf.py`: two-page German KID via reportlab (`invariant=1`, so PDFs are byte-identical per seed). It is also the single source of the section texts and the ground-truth facts. Exports `SECTIONS` (page, heading, slug) and `chunk_id()` for M3.
- `backend/app/data/store.py`: lazy cached loaders (`get_store()`), `DataMissingError` says "Run `make data` first".
- Planted injections in P13 and P31 ("Sonstige Informationen", 5 pt grey), ground truth in `injections.json`.
- `kid_facts.jsonl` (360 facts, 9 per product) and `retrieval.jsonl` (1,080 questions, 3 phrasings per fact, each with `expected_chunk_id`).
- Contract change, done together: `Company.exclusion_flags` (schema, `contracts.ts`, `contracts/products.schema.json`); both suites re-run.
- `make data` is wired in `scripts/tasks.py`. Fixtures `discover.jsonl` and `depot_august.jsonl` now use real ISINs and the real event `E12` from the universe.

**How to verify**
```
uv run python scripts/tasks.py data     # ~2 s, prints the product table and the content hash
uv run python scripts/tasks.py test     # backend 94 passed, frontend 23 passed
```
Hash for seed 20260920 (this machine, numpy 2.x): `32f83b87...72e82` (changed once after M4, see "Data change: August 2026" below; it was `5796abb5...` before). `test_same_seed_gives_identical_output_hash` regenerates everything, PDFs included, and compares every file.

**Universe facts M3–M6 rely on**
- Product IDs: P01–P24 ETFs, P25–P32 active equity, P33–P36 bond, P37–P38 mixed, P39–P40 money market. P03 `Welt ETF` (savings plan from 25 EUR), P22 `Welt Tech ETF` (SRI 5, the SRI-5 ETF for Elif), P32 (SRI 6), P13 and P31 carry the injections.
- SRI spread 1–6 (P39/P40 = 1 … P32 = 6). Equity ETFs are 4 except P22 = 5; vol 14–19 %.
- Markus: P03, P22, P11. P03 and P22 have the same top-10 holdings; his combined look-through trips both flags (one company > 5 %, top 10 > 30 %). Attribution ground truth: E12 (2026-08-12, Technologie -6 %).
- Anna: P03 and P07 savings plans. Elif: P04, P09, P34, P39, prefers distributions, risk class 2, 3,500 EUR cash.
- Holdings ids: `C###` companies, `B###` bond issuers, `M###` money-market issuers; mixed funds hold C and B. Bond holdings use sectors "Staatsanleihen", "Unternehmensanleihen", "Geldmarkt" (look-through by sector will show them).
- Prices: `prices_products.csv` (NAV, start 100, net of TER) and `prices_assets.csv`. Realised: equities 7–10 % p. a., bonds ~3.8 %, money market ~2.3 %.

**Notes for M3 (retrieval)**
- pypdf text of every page starts with 4 header/footer lines ("Basisinformationsblatt", "<name> | <isin>", "Beispieldaten · keine Anlageberatung", "Seite n von 2") before the first heading; drop them in `parse.py`. Headings are exact lines equal to the `SECTIONS` headings.
- No fact lives in "Sonstige Informationen" (the injected section), and every fact section is <= 900 chars, so ground-truth chunk IDs need no `:n` suffix.
- Every question names the product; sibling products with near-identical names (P03 vs P01, P09 vs P31) make dense retrieval non-trivial. Retrieval is easier than real user questions, so keep the answers-eval questions less templated.
- Cache the fastembed model under `data/generated/` (see M1 notes).

**Known gaps / decisions**
- Bootstrap scenarios use an iid daily bootstrap (2,000 paths, 1st/10th/50th/90th percentile), not the official PRIIPs method.
- "Kosten im Zeitverlauf" uses a simple formula (entry + (TER + transaction cost) x years), not a full RIY calculation.
- The market and sector factors are demeaned so realised drift is a constant (`MARKET_DRIFT`), not seed luck. SRI 6 exists only because small technology "growth" names have high beta and idiosyncratic volatility (`GROWTH_TECH_CAP_EUR_M`); P32 sits at 31.0 % vs the 30 % line.
- Real-looking sovereign names are avoided; bond issuers are fictional states. Company names are invented stems and could still coincide with real firms by chance (the README disclaimer covers it).
- Fixture numbers in `depot_august.jsonl` (P&L, percentages) are still placeholders; `explain_move` (M4) produces the real ones, and the fixtures are refreshed in M8.
- The ruff config allows long lines in `app/data/generate.py` only (one table row per line for products and events).

## M3 · Retrieval — done

**Done**
- `backend/app/rag/`: `parse.py` (pypdf per page, split on the `SECTIONS` headings, header/footer dropped, product name read from the header line), `chunk.py` (one chunk per section, windows of <= 900 chars with 150 overlap and a 1-based `:n` suffix only for long sections; none of the 400 real chunks needs one), `injection.py` (strong/weak regex heuristics, `possible_injection`), `index.py` (fastembed `paraphrase-multilingual-MiniLM-L12-v2` into Qdrant local mode, plus a BM25 pickle with the chunk list), `search.py` (`bm25`, `dense`, `hybrid` = RRF k=60 over the top 50 of each, `hybrid_rerank` behind `RERANK=1`, product filter, quarantine).
- API: `search_kid(query, product_ids=None, k=5, mode="hybrid") -> list[Chunk]` (SPEC §6). `get_index().retrieve(...)` returns `SearchKidOutput` (chunks plus `quarantined_ids`) and is what the agent and the trace will use; `include_quarantined=True` returns flagged chunks too.
- Quarantine: flagged chunks never appear in results; those that would have ranked in the top k are listed in `quarantined_ids`. The scanner flags exactly the 2 planted chunks (P13, P31) of 400 and none of the other 398.
- BM25 tokenisation: lowercase, umlaut and accent folding, small German stopword list, plus a truncation stemmer (`STEM_LEN = 6`) so Ertrag/Erträge/Ertragsverwendung and Einstieg/Einstiegskosten match. First version without the stemmer: hybrid recall@5 0.896; with it 0.920.
- `evals/metrics.py` (recall@k, reciprocal rank, nDCG@k, hand-computed tests in `backend/tests/test_eval_metrics.py`; M7 extends this file) and `evals/retrieval_quick.py` (ablation table, exits 1 below the 0.85 gate).
- `make ingest` is wired in `scripts/tasks.py`. `backend/pyproject.toml` pytest `pythonpath` now includes `..` so the repo-level `evals` package imports.

**Ablation** (1,080 questions from `retrieval.jsonl`, one relevant chunk each, this machine, CPU)

| mode | recall@1 | recall@5 | MRR@10 | nDCG@5 | p50 latency |
|---|---|---|---|---|---|
| bm25 | 0.560 | 0.804 | 0.659 | 0.681 | 0.3 ms |
| dense | 0.559 | 0.808 | 0.664 | 0.692 | 6.7 ms |
| hybrid | 0.601 | **0.920** | 0.727 | 0.769 | 7.5 ms |
| hybrid_rerank* | 0.844 | 0.989 | 0.912 | 0.930 | 1,227 ms |

\* `RERANK=1`, sample of 270 questions (every 4th; a full run takes ~22 min on CPU). Plain hybrid on the same sample: recall@1 0.589, recall@5 0.911, MRR@10 0.715, nDCG@5 0.758, 7.3 ms. The cross-encoder lifts recall@1 by 26 points for about 160x the latency. Reproduce: `RERANK=1 uv run python ../evals/retrieval_quick.py --every 4 --modes hybrid hybrid_rerank` from `backend/`.

**How to verify**
```
uv run python scripts/tasks.py data && uv run python scripts/tasks.py ingest   # ingest ~10 s
cd backend && uv run python ../evals/retrieval_quick.py --example "Welche Risikoklasse hat der Welt Tech ETF?"
cd backend && uv run pytest tests/test_retrieval.py -q                          # 46 tests incl. the recall gate
uv run python scripts/tasks.py test                                             # backend 140 passed, frontend 23 passed
```

**Known gaps / decisions**
- `make data` wipes `data/generated/`, including the index: run `make ingest` after every `make data`.
- The model cache is `~/.cache/invest-copilot/fastembed` (setting `MODEL_CACHE_DIR`), not inside the repo: a repo-relative cache overflowed Windows' 260-character path limit in this checkout (`Could not load model ... from any source`). CI and Docker should cache or mount that folder.
- The 1,080 questions are templated and always name the product, so absolute numbers are optimistic for real user questions. Most remaining misses are section-choice errors within the right product (e.g. "Was zahle ich beim Einstieg" landing on `produkt` instead of `kosten`). I stopped tuning at the stemmer to avoid overfitting to the templates.
- The reranker (`jinaai/jina-reranker-v2-base-multilingual`, 1.1 GB) reranks the fused top 20. Unit-tested with a fake reranker; the real one ran on a 270-question sample for the ablation row above (1.3 GB model cache, ~1.2 s per query on CPU).
- `QdrantClient` local mode allows one client per folder and process; `search.py` shares clients and closes them at exit (`close_all_clients`). `pickle` is only used for our own index file.
- fastembed warns that the MiniLM model now uses mean pooling (harmless; the index and queries use the same model).

**Notes for M4/M6**
- The `search_kid` tool wraps `get_index().retrieve(...)`; put `quarantined_ids` into the `retrieval` SSE event and the trace. `Chunk.text` is raw section text; the orchestrator wraps it in `<document id=...>` tags.
- Chunk IDs in citations are section IDs, e.g. `KID:P22:p1:risikoindikator`.

## M4 · Tools and MCP — done

**Done**
- `backend/app/tools/`: `screener.py`, `suitability.py`, `costs.py`, `lookthrough.py`, `attribution.py`, `montecarlo.py`, `search.py` (wraps M3 retrieval), `base.py` (`ToolContext`, `ToolError` with `not_found` / `invalid`), `registry.py`.
- `registry.py`: `TOOLS` (one `Tool` per contract, asserted equal to `TOOL_MODELS`), `anthropic_tool_definitions()` (all `strict: true`), `ResultStore` (request-scoped `r1`, `r2`, ...), `execute(name, args, ctx, results)` returning a `ToolResult` (payload + German summary).
- Strict schemas: built with the Anthropic SDK's own `transform_schema` (strips `minimum`/`maximum`/`exclusiveMinimum` etc. into the field description, forces `additionalProperties: false`), then every property is made required and nullable. Checked against the structured-outputs docs (platform.claude.com): no `minLength`/`maxLength`/`maxItems`/`pattern`/`default`/`oneOf`/`allOf`, `minItems` only 0 or 1, `format` from the supported list, only internal `$ref`. Nulls sent for "not specified" are dropped where the field has a default; the stripped constraints are still enforced by validating with the original pydantic model.
- `POST /api/tools/{name}` in `main.py` (404 unknown tool or ID, 422 invalid input, 503 missing data or index). `backend/app/mcp_server.py` (FastMCP, stdio, `python -m app.mcp_server`); each tool takes one argument `params`.
- Contract change, done together: `CostProjectionInput.fee_per_execution` (default 1.0); `contracts/tools.schema.json` regenerated. Also `app/fmt.py` (German number formats, moved out of `kid_pdf.py`) and `Prices.index_on_or_before`.

**Tests**: 270 backend (was 140) + 23 frontend, all green; `ruff` clean. New: `test_tools_products.py`, `test_tools_portfolio.py`, `test_tools_montecarlo.py`, `test_tools_registry.py` (API, MCP, strict schema walk, search tool). Hypothesis properties: percentiles monotonic per year, exposures sum to 100 % (company, sector, country), overlap symmetric and in [0, 1], costs non-negative and adding up, simulation deterministic, every screener hit satisfies every active filter, attribution contributions add up. Hypothesis found one real edge (a Saturday-to-Sunday window has no trading day): the tool rejects it with `invalid`, covered by a test.

**How to verify**
```
uv run python scripts/tasks.py test
cd backend && uv run pytest tests/test_tools_montecarlo.py -q --durations=3   # 5,000 paths x 30 years ~ 60 ms
curl -X POST localhost:8000/api/tools/suitability_check -H "content-type: application/json" -d '{"customer_id":"elif","product_id":"P22"}'
uv run python -m app.mcp_server        # stdio MCP server (needs data/generated and, for search_kid, `make ingest`)
```

**Worked examples** (data/generated, seed 20260920)
- Markus look-through: 3 products, 60 positions, top company 5.1 %, top-10 44.4 %, Technologie 59.7 %, US 33.7 %; flags `single_company_over_5pct` and `top10_over_30pct`; overlaps P03/P22 46.6 %, P03/P11 38.9 %, P11/P22 16.2 %.
- 50 EUR/month, 20 years, P03: paid in 12,000 EUR; p5 / p50 / p95 = 14,182 / 28,897 / 67,063 EUR; explicit costs 240 EUR; 2.2 % of paths end below the payments; KESt estimate 4,646.61 EUR.
- Elif vs P22 (SRI 5 ETF): `fail`, because of risk (class 2 of 5 fits up to SRI 3); knowledge, experience, horizon and sustainability pass.
- Cost check against design/03: 50 EUR/month, 10 years, P07: 165.38 EUR = 2.8 % of 6,000 EUR (design shows 165 EUR, 2.8 %).

**Finding, resolved right after M4 (see "Data change: August 2026" below):** the simulated market had risen about 9 % in August 2026, so "Warum ist mein Depot im August gefallen?" had a false premise. Fixed with option 1, an explicit scenario constraint in the generator.

**Known gaps / decisions**
- Strict schemas are not yet validated by a live API call (planned spike at the start of M6, with the structured-output parameters).
- Monte Carlo: the SPEC asks for a stationary block bootstrap with 20-day blocks on daily returns; a literal daily version cannot meet 300 ms for 5,000 paths x 30 years (about 38 M draws). Implemented at the plan's monthly step instead: a month is a 21-day window, and the next month continues after it with probability 0.95^21 (34 %), else restarts at a random day (circular history). `month_indices` is tested for exactly that continuation rate. Fund costs (TER) stay in the returns; `total_costs` are explicit fees and entry costs only.
- `cost_projection` assumes no market return (balance = payments so far; TER on `start + 6.5 x monthly`); that reproduces the design example.
- Suitability thresholds are my choices, kept in `suitability.py` and unit-tested: risk class 1-5 fits SRI up to 2/3/4/5/7, one step above is `warn`, more is `fail`; knowledge and experience deficits of 1 level warn, 2 fail (synthetic replication or SRI >= 6 needs advanced knowledge, active and mixed funds need some experience); horizon below the recommended holding period warns, below half fails; wanting Art. 9 but getting Art. 6 fails, other gaps warn.
- `screen_products`: empty lists and `savings_plan=false` mean "no filter"; all listed exclusions must be present. `n_companies` in the look-through counts every holding ID (companies and bond issuers).
- MCP tools take a single `params` argument (FastMCP wraps a model parameter that way).
- The docs list no cap on optional parameters for strict tools; making every field required-and-nullable was a precaution.

## Data change: August 2026 is a decline (scenario constraint) — done

**Why**: the demo story (SPEC demo, `depot_august` fixture, design/04) is "Warum ist mein Depot im August gefallen?", but with the plain random path the market rose about 9 % that month.
**What**: `backend/app/data/generate.py` pins the market factor's total over 2026-08-01..2026-08-31 to -3.0 % (`PIN_WINDOW`, `PIN_MARKET_TOTAL`, `pin_market_window`) and spreads the opposite adjustment over all other days, so the long-run drift is unchanged. Nothing else in the generator changed; the E12 chip shock (-6 % over two days, Technologie) is still injected as before.
**Result** (Markus, Aug 1-31): -316.98 EUR (-2.76 %), matched event E12; P03 -154.67, P22 -120.88, P11 -41.43 EUR (all three fall). Over the event window Aug 11-13 the depot is -3.52 %, with P22 the biggest drag (design/04 shows -3.4 % on 12 Aug). Equal-weight companies -2.1 % in August. SRI spread (1 to 6), volatilities and realised returns (equities 7-10 % p. a.) are unchanged.
**Re-verified**: M2 tests (event visibility, determinism, hash), M3 tests and the ablation (identical: hybrid recall@5 0.920, recall@1 0.601; only numbers inside KID tables moved, so retrieval ranks the same), M4 tests; 270 backend and 23 frontend tests green. New tests: `pin_market_window` (sets the total, keeps the drift), August 2026 is a decline for the market and for Markus's three products, and `explain_move` for Markus in August shows a loss with all rows negative.
**Fixture**: `depot_august.jsonl` now carries the real `explain_move` numbers and summary instead of placeholders (the `discover` fixture already used real IDs from M2; its numbers come from `screen_products`).
**Note**: regenerate and re-index after pulling this change: `make data && make ingest`.

## M5 · Frontend in fixture mode — done

**Done**
- **App shell** (`components/AppLayout.tsx`): below 1100 px the app fills the screen like a phone app; from 1100 px a 390 px phone frame with the "Unter der Haube" panel beside it (design/11), brand bar, `Demo | Auswertung`. On narrow screens the panel opens as a bottom sheet from the "Unter der Haube: strukturierte Ausgabe" button. Bottom navigation: Übersicht, Chat, Depot, Simulator, Evals. Persona switcher (Anna, Markus, Elif) on the Übersicht, remembered in `localStorage`.
- **`lib/sse.ts`**: POST + `ReadableStream` parser (`SSEParser`, `readSSE`, `toEvent`, `postSSE`). Handles chunks split anywhere (also inside UTF-8 characters), CRLF/CR, multi-line data, comments, unterminated last event; malformed JSON, unknown events, HTTP errors, network drops and aborts become `error` events or end quietly, never a throw. `lib/api.ts`: one client, every call answered from fixtures when `VITE_USE_FIXTURES=1`.
- **Blocks** (`src/blocks/`, one component per type, `registry.tsx` skips unknown types): text, product_cards, risk_meter, fan_chart, exposure_bars, overlap_matrix, attribution, cost_breakdown, suitability, handoff, citations. Recharts for fan chart, attribution and exposure bars. AI surfaces are purple with the KI label and "BIB P07 · S. 2" chips; deterministic results are neutral cards.
- **Screens**: `/` (value, 3-month curve, positions, ask input), `/chat` (streaming text, blocks, source chips, history newest first), `/depot` (value chart with event markers, tapping one calls `explain_move` and shows the attribution, "Erklären lassen" hands the question to the chat, Depot-Röntgen with overlap matrix and Länder/Branchen/Top-Titel), `/produkt/:id` (KID summary, SRI scale, cost calculator as a direct tool call, suitability for the current persona), `/simulator` (rate, duration, mix; every change is a direct simulation call), `/evals`.
- **Trace panel**: numbered steps built live from the events (router decision, tool calls with arguments, retrieval hits with scores and quarantine flags, answer, guardrail checks, tokens and cost), timing bars, Ablauf/JSON tabs, "Replay-Modus" badge.
- **Contracts, changed together** (CLAUDE.md rule): new `PortfolioView`, `PortfolioPosition`, `EventMarker`, `SeriesPoint` (`schemas/portfolio.py`) and `EvalReport` (`schemas/evals.py`), exported to `contracts/`, mirrored in `contracts.ts`, and used by the fixtures. `app/portfolio_view.py` builds the view from the real tools (it becomes `GET /api/customers/{id}/portfolio` in M8).
- **Fixtures** (`scripts/build_frontend_fixtures.py`, `make fixtures`, no hand-typed numbers): `fixtures/api/{customers,products,portfolios,tools,evals}.json` (tools.json is 417 KB: 48 simulations, 160 cost projections, 120 suitability checks, 9 event explanations, 3 look-throughs) and two new SSE streams (`simulate`, `roentgen`) next to the three from M1. Together the five streams contain all 11 block types.
- Design fidelity: the app was run in fixture mode and screenshotted with headless Chrome at 390x844 and 1440x900 (DevTools protocol, exact viewport) and compared with design 01, 02, 03, 04, 06 and 11: blue band with the first card overlapping it by 40 px, Onest, 20 px cards, purple for everything AI. Two polish rounds came out of that (wrapping labels, a duplicated cost heading, a missing "heute" tick).

**How to verify**
```
uv run python scripts/tasks.py test            # backend 291 passed, frontend 145 passed
cd frontend && npm run build
cd frontend && npm run dev                     # fixture mode is the default in dev (frontend/.env.development: VITE_USE_FIXTURES=1)
```
Open http://localhost:5173, click "Beispiel abspielen", and watch the trace panel fill on the right (at >= 1100 px wide). Rebuild fixtures after `make data && make ingest` with `make fixtures`.

**Tests added**: SSE parser (22), block registry (every block of every fixture stream renders, unknown types are ignored, per-block content), session reducer (9), trace steps (8), formatting, event windows, fixture coverage for every button the UI offers (lib, 23), all API fixtures validated against the exported schemas with the hand-written validator (contracts, 6 new), and App tests: the chat screen rendering a full fixture stream with the trace next to it, the advice hand-off, the August story with real numbers, `?q=` sent once, and a smoke test of every screen. Backend: `test_portfolio_view`-style tests and fixture tests (21 new).

**Known gaps / decisions**
- Fixture mode maps every question to one of five recorded conversations by keyword (`pickChatFixture`), so an unrelated question still gets one of those answers. It is a replay, and the trace panel says "Replay-Modus". The recordings are for fixed personas (August and Röntgen: Markus, simulate: Anna) whatever persona is active.
- "Das habe ich verstanden" chips are static. Toggling a filter would need a new search, which fixture mode cannot do; the copy no longer promises it.
- `/evals`: only the retrieval numbers are measured (the M3 ablation; the reranker row is the 270-question sample). Router, answers, red team and judge are illustrative and shown as "Beispielwert" until M7; the screen says so in a banner and per row.
- Links to KID PDFs (`/api/kid/P07.pdf#page=2`) need the backend and 404 in fixture mode. `GET /api/customers`, `/api/customers/{id}/portfolio`, `/api/products(/{id})`, `/api/kid/{id}.pdf` and `/api/evals/latest` are not implemented yet: M8 (the fixture shapes are the contract).
- Not built: design 07 (profile dialog), 08 (Invest-Coach), 09 as its own sheet (its layout is used for the hand-off block) and the Venn of design/05 (an overlap matrix shows the same numbers). The top bar has no "So funktioniert's" page.
- Product page "Größte Positionen" lists the top 10 holdings kept in the fixture (weights do not sum to 1 there); the full list comes from the API later.
- The KID "Quelle: S. n" badges link to the page; there is no in-app PDF viewer.
- Production bundle: 736 KB (218 KB gzipped), plus the fixtures as a separate 383 KB chunk that only loads in fixture mode; no route-level code splitting yet.
- No linter is configured for the frontend (SPEC lists none); `tsc -b` runs as part of `npm run build`.

**Next step**: M6, the agent. Start with the live spike from the plan (strict tool schemas and structured outputs against the real API, docs first), then `llm.py`, router, orchestrator, guardrails, tracing and `POST /api/chat`. The SSE event shapes the frontend already consumes are the contract.

## M6 · Agent — done

**Done**
- `agent/llm.py`: `LLMClient` protocol, `AnthropicClient` (streaming + `get_final_message()`), `RecordingClient`, `ReplayClient`, `make_llm_client()` (`LLM_MODE=live|record|replay`, replay when there is no key). Cassette key = sha256 of the normalised request (only API fields, sorted keys, `toolu_` ids replaced by their order). A miss names the hash and, when a recording of the same conversation exists, which request part differs (`differs in: system`). Recording is idempotent (an existing cassette is served); `RECORD_REFRESH=1` re-records.
- `agent/router.py`: Haiku with `output_config` structured output into `RouterDecision`, plus the policy table in code (`advice_request` intent or flag → refuse, `out_of_scope` → redirect, else orchestrate). Router outage falls back to a regex safety net and says so in the guardrail event.
- `agent/orchestrator.py`: PII redaction, router, policy, tool loop (at most 6 rounds), final strict `render_ui`, hydration, guardrails, one repair round, safe fallback. Every event is validated against the SSE contract before it is emitted and stored. `agent/hydrate.py` fills reference blocks from stored results (wrong-kind results, unknown IDs and unknown block types are rejected, all problems reported together). `agent/ui.py` holds the model-facing schema, `agent/prompts.py` the prompts and the fixed German answers.
- `guardrails/`: `pii` (IBAN, e-mail, phone; ISINs and dates are not touched), `advice`, `citations`, `numbers` (German formats, fraction↔percent, rounding, list counts, dates, user's own numbers), `pipeline` (emits `pii`, `router_flags`, `quarantine`, `citations`, `numeric_grounding`, `advice_language`, `ai_label`, and `repair`/`fallback` when they happen).
- `tracing/`: SQLite store (`data/traces.sqlite`, gitignored, only the redacted message is stored), `TraceRecorder`, per-call `usage` and `done` cost from `PRICE_TABLE_EUR_PER_MTOK`.
- API: `POST /api/chat` (sse-starlette), `GET /api/traces/{id}`. Contracts changed together (`ChatRequest`, `TraceRecord` in `schemas/events.py`, `contracts.ts`, `contracts/api.schema.json`); a client that disconnects leaves a trace with status `cancelled`.
- Price table checked against platform.claude.com (Haiku 4.5 $1/$5, Sonnet 5 $2/$10, Opus 5 $5/$25 per MTok) at an assumed 0.92 EUR/USD. The old Sonnet 5 placeholder was Sonnet 4.6 pricing.

**Live spike findings (they shaped the design)**
1. Eight strict schemas in one request fail: `The compiled grammar is too large`. Each tool plus `render_ui` works, and all seven tools alone work. So the final step is its own request that offers only `render_ui` (strict) and forces it with `tool_choice`. The API accepts history `tool_use` blocks for tools missing from that request.
2. `transform_schema` turns `const` into a description, so `Literal["text"]` would not be enforced. `strict_input_schema` now converts `const` to a one-value `enum` first (tested).
3. `thinking` is off for router and orchestrator: the default adaptive thinking spent 584 hidden output tokens on a one-word turn (1.6 s vs 7.4 s without).
4. Haiku 4.5 structured output and Sonnet 5 forced `tool_choice` both work.

**How to verify**
```
uv run python scripts/tasks.py test        # backend 402 passed, frontend 145 passed
cd backend && uv run pytest tests/test_agent.py tests/test_guardrails.py tests/test_llm_clients.py tests/test_chat_api.py -q
cd backend && LLM_MODE=live uv run uvicorn app.main:app --port 8000     # needs ANTHROPIC_API_KEY in .env
curl -N -X POST localhost:8000/api/chat -H "content-type: application/json" -d '{"customer_id":"markus","message":"Warum ist mein Depot im August gefallen?"}'
curl localhost:8000/api/traces/<trace_id>
```
New tests (111): scripted fake LLM (`tests/fakes.py`, no network) for event order, hydration, hallucinated number flagged (and repaired in `fail` mode), citation to an unretrieved chunk fails and repairs, second failure gives the fallback, P13 and P31 injection text never in any request to the model (and flagged in `retrieval` + `quarantine`), advice request gives a handoff with no tool call and one LLM call, PII redacted before every LLM call and never stored, unknown block rejected, wrong result kind rejected, tool round cap, cost from the price table, replay hit/miss, hash normalisation, `LLM_MODE` selection, SSE over HTTP, traces, cancellation. I broke quarantine, the number guard and the advice check on purpose: the matching tests failed each time.

**Live runs** (real API, `LLM_MODE=live`, Anna unless noted; latency and cost are per question)
- "Ich will monatlich 50 € nachhaltig in Europa anlegen, ohne Waffen": `screen_products` with savings plan, Europa, SFDR ≥ 8, Waffen excluded; 5 of 40 match (P07, P11, P16, P12, P34); 8.6 s, 0.031 EUR; all checks pass.
- "Ich will monatlich 50 € in Europa anlegen, aber mit Waffen. ": no exclusion filter, 12 of 40 match; the text says openly that the screener cannot target "with weapons"; 14.4 s, 0.036 EUR; all checks pass. Full event stream was shown in the session.
- Markus, "Warum ist mein Depot im August gefallen?": `explain_move` 2026-08-01..31 → -316,98 € (-2,76 %), P03 -154,67 / P22 -120,88 / P11 -41,43, event E12; the same numbers as M4; 8.2 s, 0.028 EUR.
- Extra: advice request refused in 1.2 s with no tool call; P13 question: the planted chunk was quarantined and `Ignoriere`/`SYSTEMHINWEIS` appear nowhere in the stream; IBAN and e-mail redacted before the model.
- Record → replay with real responses: recorded the Markus question live (4 cassettes), replayed it with no key: identical `ui`, event sequence and usage.

**Known gaps / decisions**
- **USD to EUR rate (unverified, flagged):** `USD_TO_EUR = 0.92` is a hardcoded module constant in `backend/app/config.py` (line 12). It is not an environment setting and it is not a live exchange rate; 0.92 is my assumption, not a sourced figure. The USD list prices it multiplies are verified (pricing page, 2026-09-20). It feeds only `PRICE_TABLE_EUR_PER_MTOK` and therefore `cost_eur()`, i.e. the `cost_eur` in `usage` and `done` events and in stored traces. Nothing else depends on it: KID costs, `cost_projection` and all other figures shown to users come from the synthetic data and are in EUR already. Treat displayed LLM costs as approximate. To change it, edit the constant (or a table entry) and the tests that pin 1.84 / 9.20 / 0.92 / 4.60 EUR per MTok in `tests/test_agent.py`.
- `text_delta` is emitted after the guardrails ran, in 4-word pieces (12 ms apart): unchecked text never reaches the client, but it is not token-live from the model. Tool events stream live.
- `NUMBERS_GUARD` defaults to `flag` (plan risk 7): ungrounded numbers are reported, not repaired. Seven live answers had no false positive and no ungrounded number, but that is a small sample; M7's answers eval decides whether `fail` becomes the default. Known limit: matching is by value, so a bare integer equal to any source number (e.g. 12 as day of a date) counts as grounded.
- Cassette files are named by the first 32 hex characters of the sha256 (full hash inside the file), not all 64: with a long checkout or scratch path the 64-character name overflowed Windows' 260-character limit (found while recording).
- The screener cannot express "does not exclude X", so "mit Waffen" lists all Europe savings-plan products, including ones that exclude weapons. The model says so, but a filter would fix it properly (candidate for a contract change).
- The P13 answer said the KID has no "Sonstige Informationen" section (it was withheld) while also saying a suspicious section was withheld. Accurate enough not to leak, but the wording is the model's; the withheld-note in the tool result could be more precise.
- Latency 8-14 s per question (3-4 sequential LLM calls; the first router call is slowest); cost about 0.03 EUR. Tools run synchronously inside the event loop (milliseconds, except the first `search_kid`, which loads the embedding model).
- Not connected to the frontend yet: it still uses fixtures. New guardrail names (`router_flags`, `router_fallback`, `repair`, `fallback`) and the `quarantined` chunk flag will show up in the trace panel in M8.
- No cassettes are committed yet (M8 records the demo questions). `data/traces.sqlite` is gitignored. Injection heuristics, advice regexes and the input safety net are pattern lists: M7's red-team suite is where they get attacked.
- `spec-reviewer` has not been run; PLAN.md schedules it for M5, M6 and M8 together in M8.

**Next step**: M7, evals: `evals/{datasets, metrics.py, judge.py, run.py, thresholds.yaml}`, the router and red-team suites in replay mode for `make eval-ci`, and the answers eval (which also settles the `NUMBERS_GUARD` default). Start with `/clear` after this commit.

