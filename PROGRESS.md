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
Hash for seed 20260920 (this machine, numpy 2.x): `5796abb5...b1175`. `test_same_seed_gives_identical_output_hash` regenerates everything, PDFs included, and compares every file.

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

**Next step**: M3, hybrid retrieval (`make ingest`, ablation table).
