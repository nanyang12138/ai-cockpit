# AGENTS.md

## Cursor Cloud specific instructions

### Project Status

AI Cockpit v0.3.0 — a personal AI workflow management layer (CLI tool). Full application source code lives under `src/ai_cockpit/` with 301 tests under `tests/`. See `README.md` for feature overview, CLI flags, and project layout.

### Development Environment

- **Python 3.12+** is required. Virtual environment at `.venv/`.
- Activate: `source /workspace/.venv/bin/activate`
- Install (dev + LLM extras): `pip install -e ".[dev,llm]"`
- The update script handles venv creation and `pip install` automatically.

### Running Tools

- **Lint:** `source .venv/bin/activate && ruff check .`
- **Type check:** `source .venv/bin/activate && mypy src/`
- **Tests:** `source .venv/bin/activate && python -m pytest`
- **CLI (stub mode, no LLM keys needed):** `source .venv/bin/activate && ai-cockpit run "some idea" --no-checkpoint --dry-run`
- **CLI status:** `source .venv/bin/activate && ai-cockpit status`

### Key Caveats

- The CLI runs end-to-end in stub mode (no LLM calls) by default. Pass `--llm auto` to use real LLM backends, which requires `LLM_API_KEY`, `ANTHROPIC_API_KEY`, or `OPENAI_API_KEY` in the environment.
- Tests (301 total) take ~2 minutes. All tests pass without LLM API keys — they use stubs/mocks.
- `mypy` should be run against `src/` (not `.`) to avoid checking test files and examples that aren't part of the strict config.
- The `--no-checkpoint` flag avoids writing to SQLite during smoke tests; useful for ephemeral CI or quick verification.
- GitHub Actions CI workflows live under `.github/workflows/` (`validate.yml` runs ruff + mypy + pytest).
- Memory suggestions written by `ai-cockpit run` land in `.ai-cockpit/suggestions/` (gitignored). Clean up with `ai-cockpit memory list`.
