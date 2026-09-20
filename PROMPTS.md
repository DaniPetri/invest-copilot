# Invest Copilot — the prompts
Run them in order. Times are from the moment you send P1. Terminal A is the main session; B and C are parallel sessions in git worktrees.

## P0 · Pre-flight: repo and first session
**When:** Before the clock (10 min) · **Terminal:** Your normal terminal · **Mode:** —

In your terminal first:

```bash
# unzip invest-copilot-starter-kit.zip → you get a folder invest-copilot/
# (it contains hidden files like .claude/ and .gitignore; Finder hides them, that's fine)
cd invest-copilot
git init -b main
git add -A && git commit -m "chore: starter kit"
gh repo create invest-copilot --private --source=. --push
cp .env.example .env        # open .env and paste your API key
claude                      # this is Terminal A
```

**You should see:** Claude Code opens in the repo. Type /context once: CLAUDE.md must be listed as loaded. Type /model and pick the strongest model for P1–P2 and P8.

## P1 · Plan the build
**When:** 0:00–0:07 · **Terminal:** A · **Mode:** Plan mode: press Shift+Tab until the status bar shows 'plan mode on'

Prompt:

```text
Read @SPEC.md, @CLAUDE.md and @design/README.md, and look at every image in design/ (not design/private/).

Write PLAN.md with:
1. Milestones M1–M9 from SPEC §13, each broken into concrete files, functions and tests, with its "Done when" check written as a runnable command.
2. The parallel plan: Terminal A (main: M1–M4, M6, M8–M9), Terminal B (worktree "frontend": M5, then Docker, devcontainer, CI and a README draft), Terminal C (worktree "evals": M7). List exactly which files each terminal owns so two sessions never edit the same file.
3. A cut list in priority order in case we fall behind.
4. The 5 biggest technical risks (for example Qdrant local mode, the structured-outputs parameters, SSE parsing over POST, strict tool schemas from pydantic) and how you will de-risk each one early.

Ask me at most 3 questions, and only if something in SPEC.md is contradictory. Don't write code yet.
```

**You should see:** A PLAN.md proposal. Read the file-ownership list and the cut list, then approve the plan. Approving leaves plan mode.

## P2 · Contracts and skeleton (M1)
**When:** 0:07–0:18 · **Terminal:** A · **Mode:** Auto mode (default)

Prompt:

```text
Implement M1 from PLAN.md. Contracts first, because two other sessions will build against them:
- backend/app/schemas: every pydantic model from SPEC §7–§9 (tool inputs and outputs, RouterDecision, every SSE event, the UIBlock discriminated union).
- scripts/tasks.py plus a thin Makefile (setup, data, ingest, dev, test, eval, eval-ci, contracts, record); a uv project in backend/ with the SPEC §4 dependencies; a FastAPI app with GET /api/health.
- `make contracts` exports JSON Schema to contracts/*.schema.json.
- frontend/: Vite + React 19 + TypeScript + Tailwind v4 skeleton; src/types/contracts.ts mirroring the schemas; @fontsource/onest; the tokens from design/README.md in src/design/tokens.css.
- frontend/fixtures/sse/: three realistic German event streams (a discover question ending in product_cards + citations; "Warum ist mein Depot im August gefallen?" ending in attribution; "Welche Aktie soll ich kaufen?" ending in handoff). They must validate against the schemas in a backend test AND a frontend test.
Run `make test` and show the output. Update PROGRESS.md, commit "feat(m1): contracts and skeleton", and push to origin main.
```

**You should see:** Green tests on both sides, the schemas in contracts/, a pushed commit. The push matters: worktrees branch from the remote.

## P3 · Synthetic universe and KID PDFs (M2)
**When:** 0:18–0:35 · **Terminal:** A · **Mode:** Auto mode

Prompt:

```text
Implement M2: backend/app/data/generate.py, kid_pdf.py and store.py exactly as in SPEC §5 (seed 20260920):
150 companies; 40 products with XD ISINs that have valid check digits; factor-model prices with the 12 injected market events; SRI from the PRIIPs volatility bands; the 3 personas with deliberate overlaps; 40 two-page German KID PDFs with performance scenarios and cost tables; the planted injections in P13 and P31; kid_facts.jsonl and retrieval.jsonl (at least 160 questions, 3 phrasings per fact).

Tests: holding weights sum to 1; ISIN check digits are valid; SRI bands are correct; each event is visible in the affected sector's returns; the same seed gives an identical output hash; every PDF has 2 pages and contains its TER string.

Run `make data` (must finish in under 2 minutes) and `make test`. Show me the product table (id, name, SRI, TER, SFDR), the extracted text of one KID, and 3 retrieval questions. Update PROGRESS.md, commit, push.
```

**You should see:** A product table with a spread of SRI values from 1 to 6, readable German KID text, tests green.

## P4 · Frontend in fixture mode (M5)
**When:** 0:18–1:00 · **Terminal:** B (new terminal) · **Mode:** Auto mode

In your terminal first:

```bash
cd invest-copilot
git pull
claude --worktree frontend
```

Prompt:

```text
You own frontend/ only. The backend isn't ready yet, so work in fixture mode (VITE_USE_FIXTURES=1) against frontend/fixtures/sse plus small JSON fixtures for customers, products and portfolio that you create from the schemas in contracts/.

Build M5 per SPEC §10 and design/README.md. Match the images in design/ closely: blue header band with the first card overlapping it, Onest, purple for everything AI, 20 px cards.
1. App shell: phone frame (390 px) plus the "Unter der Haube" trace panel at ≥1100 px (design/11-trace-panel.png); persona switcher; bottom navigation (Übersicht, Chat, Depot, Simulator, Evals).
2. lib/sse.ts: POST + ReadableStream SSE parser with unit tests (chunks split mid-line, multi-line data, error events). lib/api.ts with a fixture fallback.
3. One React component per UIBlock type in src/blocks/, rendered through a registry that ignores unknown types. Recharts for fan_chart, attribution and exposure bars.
4. Screens: /, /chat (streaming text, blocks, source chips), /depot (chart with event markers), /produkt/:id, /simulator, /evals.
5. Trace panel: live events with timing bars, router decision, tool calls with arguments, retrieval hits with scores and quarantine flags, guardrail checks, tokens, cost and a "Replay-Modus" badge.
German copy (du-Form), KI labels, footer "KI-generiert · Beispieldaten · keine Anlageberatung", 44 px touch targets, focus rings, reduced motion.

Tests: the SSE parser; the registry renders every fixture block; the chat screen renders a full fixture stream. Run `npm test -- --run` and `npm run build`, show the output, update the frontend section of PROGRESS.md, and commit on this branch.
```

**You should see:** `npm run dev` in frontend/ shows the George-style app working entirely on fixtures, including the trace panel.

## P5 · Hybrid retrieval with ablation (M3)
**When:** 0:35–0:52 · **Terminal:** A · **Mode:** Auto mode

Prompt:

```text
Implement M3 per SPEC §6:
- parse.py (pypdf, per page, split by section headings)
- chunk.py (IDs KID:{pid}:p{page}:{section})
- index.py (fastembed multilingual model into Qdrant local mode plus a BM25 pickle; `make ingest`)
- search.py (bm25, dense, hybrid with RRF k=60, hybrid_rerank behind RERANK=1)
- injection.py (heuristics plus quarantine)

Add evals/retrieval_quick.py: run data/generated/retrieval.jsonl in every mode and print an ablation table with recall@1, recall@5, MRR@10, nDCG@5 and p50 latency.

Tests: chunk IDs are stable; product filters work; the P13 and P31 injection chunks are flagged; hybrid recall@5 ≥ 0.85. If it misses, improve chunking or tokenisation. Do not lower the bar.

Show the ablation table and one example query with its top 3 chunks. Update PROGRESS.md, commit, push.
```

**You should see:** An ablation table where hybrid beats BM25 and dense alone. This table goes on a slide.

## P6 · Deterministic finance tools and MCP (M4)
**When:** 0:52–1:10 · **Terminal:** A · **Mode:** Auto mode

Prompt:

```text
Implement M4 per SPEC §7. Use subagents in separate worktrees to build in parallel:
(a) screener, suitability and costs; (b) look-through and attribution; (c) Monte Carlo. Then merge their work yourself.

Requirements:
- pydantic input/output models from backend/app/schemas
- registry.py exporting Anthropic tool definitions with strict: true and additionalProperties: false
- a request-scoped result store (result_id → payload)
- POST /api/tools/{name}
- backend/app/mcp_server.py exposing the tools via FastMCP (mcp<2)

Tests:
- unit tests per tool
- hypothesis property tests: percentiles monotonic per year, exposures sum to 100 %, overlap symmetric and ≤ 1, costs non-negative, simulation deterministic with its seed
- Monte Carlo under 300 ms for 5,000 paths × 30 years
- attribution finds the ground-truth event for Markus in August 2026

Show me Markus's look-through summary, a 50 €/20-year simulation for P03, and suitability_check for Elif against an SRI-5 ETF. Update PROGRESS.md, commit, push.
```

**You should see:** Three worked examples with plausible numbers, and all property tests green.

## P7 · Frontend polish against the designs
**When:** 1:00–1:15 · **Terminal:** B · **Mode:** Auto mode

Prompt:

```text
Compare each screen with its reference image in design/ (the mapping is the table in design/README.md). For each screen, list the 5 most visible differences (spacing, type sizes, colours, radii, hierarchy) and fix them. If you have a browser tool, take screenshots at 390×844 and 1440×900 to check; otherwise reason from the code. Run the tests and the build, then commit.
```

**You should see:** Screens visibly closer to design/. Tip: paste your own browser screenshot into Claude Code (Ctrl+V) next to the design image and ask for the differences.

## P8 · Agent, guardrails, tracing, SSE (M6)
**When:** 1:10–1:38 · **Terminal:** A · **Mode:** Auto mode. /model → strongest model

Prompt:

```text
Implement M6 per SPEC §8 and §9. This is the core, so take care.
1. agent/llm.py: the LLMClient protocol; AnthropicClient (streaming, tool use, output_config structured outputs); RecordingClient; ReplayClient (sha256 of the normalised request → fixtures/cassettes/*.jsonl); selection via LLM_MODE.
2. router.py: RouterDecision via structured output, plus the policy table from SPEC §8.
3. orchestrator.py: tool loop (at most 6 rounds), <document> wrapping, a final strict render_ui, ui.py hydration from stored results, [[cite:ID]] handling, one repair round and a safe fallback.
4. guardrails/: pii, advice, citations, numbers (German number formats) and a pipeline emitting checks.
5. tracing/: SQLite store, every SSE event from SPEC §9, per-model cost from the price table.
6. POST /api/chat with sse-starlette; GET /api/traces/{id}.

Tests with a scripted fake LLM (no network):
- event order
- a hallucinated number gets flagged
- a citation to a chunk that wasn't retrieved fails and triggers repair
- the P13 injection never reaches the model context
- the advice request yields a handoff block with no tool calls
- PII is redacted before the LLM call

Then run live (LLM_MODE=live) for "Ich will monatlich 50 € nachhaltig in Europa anlegen, ohne Waffen" and, as Markus, "Warum ist mein Depot im August gefallen?". Show me the full event stream of the second one. Update PROGRESS.md, commit, push.
```

**You should see:** A live stream: router → tool_start/tool_end → retrieval → text_delta → ui → guardrail → usage → done, with cost in euros.

## P9 · Evaluation harness (M7)
**When:** 1:10–1:38 · **Terminal:** C (new terminal) · **Mode:** Auto mode

In your terminal first:

```bash
cd invest-copilot
git pull
claude --worktree evals
```

Prompt:

```text
You own evals/ only. Build M7 per SPEC §11 against the interfaces in backend/app. The agent entry point may not exist yet: call it through a thin adapter, evals/adapter.py, that imports app.agent.orchestrator when available and otherwise skips those suites with a clear message.

1. Datasets (write them yourself in German, with realistic Austrian phrasing):
   - router.jsonl: 80 utterances (60 dev, 20 blind), including dialect, typos, negations, 12 advice requests, 8 injections and 6 out-of-scope
   - answers.jsonl: 30 questions with reference facts taken from data/generated
   - redteam.jsonl: 20 attacks across the SPEC categories
   - judge_calibration.jsonl: 12 answers with empty human_score fields for me to fill in
2. metrics.py: accuracy, macro-F1, recall@k, MRR, nDCG, bootstrap CIs and Cohen's kappa, each with unit tests on hand-computed examples.
3. judge.py: rubric prompt, structured output (scores 1–5 plus a one-sentence reason per criterion), cached.
4. run.py: CLI per SPEC §11 with thresholds.yaml gates, writing reports/<timestamp>.json, latest.json and latest.md (tables, including the retrieval ablation).

Run the retrieval suite for real and the metric tests. Commit on this branch.
```

**You should see:** Metric unit tests green and a first latest.md with the retrieval ablation. Router, answers and redteam run after P11.

## P10 · DevEx: Docker, Codespaces, CI, README draft
**When:** 1:15–1:35 · **Terminal:** B · **Mode:** Auto mode

Prompt:

```text
Now you own the DevEx files:
- docker-compose.yml (api + web; runs `make data` on first start) and Dockerfiles for backend and frontend
- .devcontainer/devcontainer.json (Python 3.12, Node LTS and uv; runs make setup && make data; forwards ports 8000 and 5173)
- .github/workflows/ci.yml: ruff, pytest, vitest, make data and make eval-ci; upload evals/reports/latest.* as an artifact; cache uv, npm and the fastembed model
- a README.md draft per SPEC §12, with placeholders for screenshots and eval numbers

Don't touch backend/app. Commit.
```

**You should see:** Files ready to be merged in P11. You only test Docker if you installed it.

## P11 · Integration and recording (M8)
**When:** 1:38–1:50 · **Terminal:** A · **Mode:** Auto mode

Prompt:

```text
Integrate M8:
1. Merge the branches worktree-frontend and worktree-evals into main. Resolve conflicts, keeping the contracts consistent (run make contracts).
2. Point the frontend at the real API (VITE_USE_FIXTURES=0 by default in dev). Check every screen against the running backend and fix mismatches.
3. Put 8 demo questions in scripts/demo_questions.yaml (2 discover, 1 product question, 2 portfolio insight, 1 simulate, 1 advice request, 1 injection attempt). Run `make record` to store their cassettes, and also record the router, redteam and answers suites.
4. Verify replay mode: unset ANTHROPIC_API_KEY, run make dev, and check that all 8 questions work.

Use the spec-reviewer subagent on M5, M6 and M8, and fix what it reports. Commit, push.
```

**You should see:** The full app on the real backend. With the key removed it still answers all 8 demo questions from cassettes.

## P12 · Live evaluation and the iteration log
**When:** 1:50–1:55 · **Terminal:** A · **Mode:** Auto mode

Prompt:

```text
Run `make eval` in live mode (all suites). Then:
1. Show me latest.md.
2. For each failed gate: explain the root cause from the individual failures, fix the top issue, and rerun only that suite. At most two iterations. Record before/after numbers and what changed in evals/CHANGELOG.md (this is my prompt-iteration log for the interview).
3. Make sure /evals shows the report. Commit evals/reports/latest.* and push.
```

**You should see:** Real numbers for every suite, an ablation table, and a changelog entry showing one improvement you can talk about.

## P13 · Ship it (M9)
**When:** 1:55–2:00 · **Terminal:** A · **Mode:** Auto mode

Prompt:

```text
Finish M9:
1. README: fill in the eval tables from evals/reports/latest.md and the ablation table; reference 4 screenshots I will add to docs/; quickstart (replay, live, Docker, Codespaces); design decisions (why numbers come from code, why hybrid retrieval, why replay cassettes); limitations; the disclaimer from SPEC §15.
2. Run the spec-reviewer subagent on the whole repo against M1–M9 and fix the gaps that break "Done when".
3. Run `make test` and `make eval-ci`, push, and wait for CI to pass (`gh run watch`).
4. Make the repo public (`gh repo edit --visibility public --accept-visibility-change-consequences`), tag v0.1.0, and create a release with the eval summary as its notes.
Show me the repo URL and the CI status.
```

**You should see:** A public repo with green CI, a tagged release and a README a reviewer can follow in 3 commands.

## Rescue prompts

### Tests keep failing (same error twice)

```text
Stop patching symptoms. Read the failing test output, explain the root cause in three sentences, then fix it. Run the single failing test first, then the suite.
```

### Context is filling up / Claude gets forgetful

```text
Update PROGRESS.md with: done, in progress, next step, commands to verify, open issues. Then stop.

→ run /clear, then:

Read PROGRESS.md and PLAN.md and continue with the next step.
```

### You're behind schedule

```text
We're behind. Apply the cut list from PLAN.md up to item 2. Tell me what you dropped, then finish the current milestone in its reduced form with tests green.
```

### An Anthropic API call errors

```text
Don't guess parameters. Fetch the Claude API docs for structured outputs and tool use at platform.claude.com, compare with our call in agent/llm.py, fix it, and add a regression test with the fake LLM.
```

### Merge conflicts after P11

```text
List every conflicted file. For contract files, backend/app/schemas is the source of truth: regenerate with make contracts, then adapt frontend/src/types and the fixtures. Run both test suites.
```

### The UI doesn't look like the design

```text
[paste your browser screenshot] This is /chat now; design/02-entdecken-ergebnisse.png is the target. List the 10 biggest differences and fix the top 5.
```

### Something is broken and you don't know why

```text
Use a subagent to investigate why [symptom] happens. It should read the logs and relevant files and report the root cause with file:line, without changing code.
```

## Claude Code cheat sheet

| Key / command | What it does |
|---|---|
| `Shift+Tab` | cycle permission modes (plan mode for P1) |
| `Esc` | stop Claude mid-action; Esc Esc or /rewind to go back to a checkpoint |
| `/clear` | empty the context (PROGRESS.md keeps the state) |
| `/context` | check what's loaded (CLAUDE.md should be listed) |
| `/model` | switch model: strongest for P1, P2 and P8 |
| `/code-review` | fresh-context bug review of the current diff |
| `@file` | attach a file to the prompt; paste images with Ctrl+V |
| `claude --worktree NAME` | start an isolated parallel session on its own branch |
| `claude --continue` | reopen the last session after closing the terminal |
