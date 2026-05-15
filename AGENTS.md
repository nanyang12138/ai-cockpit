# AGENTS.md

## Cursor Cloud specific instructions

### Project Status

This is a **greenfield planning repository** for "AI Cockpit" — a personal AI workflow management layer. As of now, the repository contains only planning/specification documents (`AUTOMATION_PROMPT.md`, `docs/AI_COCKPIT_SPEC_V1.md`, `docs/AI_COCKPIT_IMPLEMENTATION_PLAN_V0.md`) and CI workflow files. **No application source code exists yet.** The `AUTOMATION_PROMPT.md` contains instructions for building v0.1.

### Tech Stack (Planned)

- **Language:** Python 3.12+
- **Orchestration:** LangGraph (state machine, checkpoint, loop control)
- **LLM Providers:** OpenAI / Anthropic APIs (via `langchain-openai`, `langchain-anthropic`)
- **CLI:** `click`
- **Testing:** `pytest`, `pytest-asyncio`
- **Linting:** `ruff`
- **Type Checking:** `mypy`
- **Data Models:** `pydantic`

### Development Environment

- Python virtual environment is at `.venv/` (created via `python3 -m venv .venv`)
- Activate with `source /workspace/.venv/bin/activate`
- All planned dependencies are pre-installed: `langgraph`, `langchain-core`, `langchain-openai`, `langchain-anthropic`, `pytest`, `pytest-asyncio`, `ruff`, `mypy`, `click`, `pydantic`

### Running Tools

- **Lint:** `source .venv/bin/activate && ruff check .`
- **Type check:** `source .venv/bin/activate && mypy .`
- **Tests:** `source .venv/bin/activate && python -m pytest`
- Once application code exists, CLI entry point will be: `ai-cockpit "some idea"`

### Key Caveats

- Workflows live under `.github/workflows/`, which is the directory GitHub Actions recognizes.
- No `pyproject.toml` or `requirements.txt` exists yet. When the project skeleton is created, the update script should be updated to install from the project manifest.
- LLM-dependent nodes (planner, reviewer) will need `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` environment variable set to use real LLM calls instead of stub outputs.
- The `python3.12-venv` system package must be installed for creating virtual environments (`sudo apt-get install -y python3.12-venv`).
