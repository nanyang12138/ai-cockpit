# AI Cockpit (v0.1)

A minimal, safe, runnable vertical slice of a personal AI workflow
management layer. Built per the spec in
[`docs/AI_COCKPIT_SPEC_V1.md`](docs/AI_COCKPIT_SPEC_V1.md) and the
implementation plan in
[`docs/AI_COCKPIT_IMPLEMENTATION_PLAN_V0.md`](docs/AI_COCKPIT_IMPLEMENTATION_PLAN_V0.md).

This release implements only the vertical slice required by
`AUTOMATION_PROMPT.md`:

```
idea input
-> load memory
-> planner creates MVP spec
-> coder stub executes
-> verifier collects git diff/status and runs shell checks
-> reviewer evaluates evidence
-> decision chooses done/retry/ask_human
-> summary prints final result
```

It does **not** include UI, plugins, cloud execution, PR automation,
ruflo integration, real coding workers, or LLM calls. The planner and
reviewer use deterministic stub outputs; the coder uses a `StubWorker`
that performs no edits.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run

```bash
ai-cockpit "I want to build a tool that turns vague ideas into MVP specs"
```

Optional flags:

| Flag | Default | Description |
| --- | --- | --- |
| `--root PATH` | `.` | Project root in which git/test commands run. |
| `--max-loops N` | `1` | Maximum number of retry loops. |
| `--mode MODE` | `exploration` | Either `exploration` or `task`. |
| `--test-command CMD` | none | Shell command to run as a verification check. May be repeated. |
| `--dry-run` | off | Skip running the test command(s); still collect git status/diff. |
| `--llm MODE` | `none` | `none` keeps stub planner/reviewer (default). `auto` picks Anthropic vs OpenAI from env. `anthropic` / `openai` force a provider. |

### LLM configuration (v0.2 step 1, opt-in)

`--llm` reads credentials from the environment in this priority order:

1. **Generic / proxy-friendly** — `LLM_API_KEY` + `LLM_API_BASE` + `LLM_MODEL_NAME`.
   This is the only set that works with enterprise gateways such as
   `https://llm-api.amd.com/Anthropic`.
2. `ANTHROPIC_API_KEY` (default base `https://api.anthropic.com`).
3. `OPENAI_API_KEY` (default base `https://api.openai.com/v1`).

Auto-detect: if `LLM_API_BASE` contains `anthropic` or the model name
starts with `claude`, the Anthropic-compatible client is used. Otherwise
the OpenAI-compatible client is used. Override with `LLM_PROVIDER=openai`
or `LLM_PROVIDER=anthropic`.

Optional packages must be installed for the provider you select:

```bash
pip install -e ".[llm]"   # both providers
pip install -e ".[anthropic]"
pip install -e ".[openai]"
```

If credentials or the optional package are missing, the CLI prints a
warning and falls back to the v0.1 stub planner/reviewer — runs never
crash.

Example:

```bash
ai-cockpit "Build a tiny CLI that summarizes meeting notes" \
  --root . \
  --max-loops 1 \
  --test-command "python -m pytest -q"
```

## Project Layout

```
pyproject.toml
README.md
.ai-cockpit/
  memory/        # markdown context loaded at intake
  workflows/     # workflow templates (declarative, not executed in v0.1)
  history/       # placeholder for future runs
src/ai_cockpit/
  cli.py
  config.py
  state.py
  graph.py
  nodes/         # intake, planner, coder, verifier, reviewer, decision, summary
  workers/       # base worker + StubWorker
  tools/         # git + shell helpers
  memory/        # memory loader
tests/
```

## Tests

```bash
source .venv/bin/activate
python -m pytest
```

## Known Limitations (v0.1, partially addressed in v0.2 step 1)

- Planner and reviewer default to deterministic stubs; pass `--llm auto`
  with credentials to enable real LLM calls (v0.2 step 1).
- Coder is still a `StubWorker` that never modifies files.
- No human-in-the-loop interrupts; `ask_human` is reported but not interactive.
- No checkpoint persistence beyond the in-memory `TaskState`.
- No real worker integration (Aider, Cursor SDK, OpenHands intentionally excluded).

## Recommended Next Step

Replace the planner/reviewer stubs with real LLM calls behind a small
adapter, then introduce a single real coding worker (e.g. Aider) gated
behind explicit configuration. See
`docs/AI_COCKPIT_IMPLEMENTATION_PLAN_V0.md` §16 for the roadmap.
