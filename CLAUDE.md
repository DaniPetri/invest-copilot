# Invest Copilot — working rules

Read @SPEC.md before any task. PLAN.md is the milestone plan. PROGRESS.md is the running log: read it at the start of every session.

## Commands
- Everything: `make test` · `make data` · `make dev` · `make eval-ci` · `make contracts`
- Backend only: `cd backend && uv run pytest -q` · `uv run ruff check . --fix`
- Frontend only: `cd frontend && npm test -- --run` · `npm run build`
- Windows without make: `uv run python scripts/tasks.py <target>`

## Rules
- IMPORTANT: contract changes (backend/app/schemas, frontend/src/types/contracts.ts, frontend/fixtures/sse) happen together, followed by `make contracts` and both test suites.
- Numbers shown to users come from tool results or cited chunks, never from model arithmetic.
- Only the dependencies in SPEC §4. Ask before adding any other.
- UI copy is German (du-Form). Code, comments and commits are English.
- Every milestone: tests green → PROGRESS.md updated (done / how to verify / known gaps / next step) → conventional commit → push.
- Fixed seeds. Generated data goes to data/generated/ (gitignored).
- Never commit .env or keys. Never print ANTHROPIC_API_KEY.
- Show evidence (test output, command results), don't just claim success.
- If an Anthropic API parameter errors, fetch the docs at platform.claude.com. Don't guess.
- When the context gets long: update PROGRESS.md, then tell me to run /clear.
- When compacting, keep: current milestone, modified files, failing tests, commands to verify.
