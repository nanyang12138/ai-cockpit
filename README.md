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

## Known Limitations (v0.1)

- Planner and reviewer are deterministic stubs; no LLM is called.
- Coder is a `StubWorker` that never modifies files.
- No human-in-the-loop interrupts; `ask_human` is reported but not interactive.
- No checkpoint persistence beyond the in-memory `TaskState`.
- No real worker integration (Aider, Cursor SDK, OpenHands intentionally excluded).

## Recommended Next Step

Replace the planner/reviewer stubs with real LLM calls behind a small
adapter, then introduce a single real coding worker (e.g. Aider) gated
behind explicit configuration. See
`docs/AI_COCKPIT_IMPLEMENTATION_PLAN_V0.md` §16 for the roadmap.
