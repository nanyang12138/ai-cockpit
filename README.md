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
source .venv/bin/activate          # tcsh / csh: source .venv/bin/activate.csh
pip install -e ".[dev]"             # NOT plain `pip install -e .` — the
                                    # dev extras carry pytest / ruff / mypy
                                    # which the verifier and pre-push
                                    # checklist rely on.
```

> **csh / tcsh users:** after every `pip install ...` you also need
> `rehash` so the shell picks up newly-added executables (e.g.
> `ai-cockpit`, `aider`, `pytest`). bash users can ignore this.

To also enable real-LLM `--llm auto` and the AiderWorker:

```bash
pip install -e ".[llm]"             # langchain-anthropic + langchain-openai
pip install aider-chat              # only if you want --worker aider
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
| `--worker MODE` | `stub` | `stub` (default) never modifies files. `aider` spawns the `aider` CLI to execute the implementation slice; requires `--apply` to actually edit (preview-only otherwise). |
| `--apply` | off | Opt-in for `--worker aider`: actually invoke aider so it can modify files. Mutually exclusive with `--dry-run`. Ignored for `--worker stub`. |
| `--llm MODE` | `none` | `none` keeps stub planner/reviewer (default). `auto` picks Anthropic vs OpenAI from env. `anthropic` / `openai` force a provider. |
| `--thread-id ID` | auto-minted | Explicit thread id under which this run is persisted. When omitted, a fresh id is generated and printed to stderr. |
| `--resume` | off | Boolean flag. Resume the run identified by `--thread-id` from its last checkpoint. Requires `--thread-id`; the idea argument is ignored. |
| `--no-checkpoint` | off | Disable SQLite checkpointing for this run (no DB writes). Mutually exclusive with `--thread-id` / `--resume` / `--checkpoint-db`. |
| `--checkpoint-db PATH` | `<root>/.ai-cockpit/history/checkpoints.sqlite` | Override the checkpoint DB location. |

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

`LLM_API_EXTRA_HEADERS` (optional, JSON object) is forwarded to the
underlying client as `default_headers`. Use this — and only this — to
add gateway-specific auth headers (e.g. Azure API Management's
`Ocp-Apim-Subscription-Key`) without hardcoding any provider's header
name. Example for an APIM-fronted Anthropic endpoint:

```bash
export LLM_API_KEY=<your-key>
export LLM_API_BASE=https://llm-api.amd.com/Anthropic
export LLM_MODEL_NAME=claude-opus-4-6
export LLM_API_EXTRA_HEADERS='{"Ocp-Apim-Subscription-Key": "<your-key>"}'
ai-cockpit "..." --llm auto
```

Malformed `LLM_API_EXTRA_HEADERS` (invalid JSON or non-object) is logged
at WARNING and silently ignored — the run does not crash.

Optional packages must be installed for the provider you select:

```bash
pip install -e ".[llm]"   # both providers
pip install -e ".[anthropic]"
pip install -e ".[openai]"
```

If credentials or the optional package are missing, the CLI prints a
warning and falls back to the v0.1 stub planner/reviewer — runs never
crash.

### Coder worker (v0.3 step 2, opt-in)

By default the coder node uses `StubWorker` and never touches files —
this is the v0.1 behavior and is safe for every CI / smoke run. Pass
`--worker aider` to route the implementation slice through the
[`aider`](https://aider.chat/) CLI instead:

```bash
pip install aider-chat
ai-cockpit "fix the failing test in tests/test_calc.py" --worker aider
```

**Safety default: `--worker aider` is preview-only.** Without `--apply`
the worker prints the message it *would* send to aider but spawns no
subprocess. To actually let aider edit your working tree:

```bash
ai-cockpit "fix the failing test" --worker aider --apply --llm auto
```

`--apply` is mutually exclusive with `--dry-run`. Aider inherits the
current environment so `LLM_API_KEY` / `LLM_API_BASE` /
`LLM_MODEL_NAME` / `LLM_API_EXTRA_HEADERS` reach it unchanged; map
them to aider's expected names (typically `ANTHROPIC_API_KEY` +
`ANTHROPIC_API_BASE` for Anthropic-compatible endpoints) yourself
when needed. Aider runs with `--yes-always --no-stream
--no-auto-commits --no-gitignore` so it stays non-interactive,
leaves its diff in the working tree for the verifier to pick up,
and does NOT touch your `.gitignore` (which would otherwise show
up as unrelated noise in the reviewer's evidence).

**APIM gateways (v0.3 step 2 follow-up):** when both
`LLM_API_EXTRA_HEADERS` and `LLM_MODEL_NAME` are set, AiderWorker
auto-generates a temporary aider `--model-settings-file` entry with
`extra_params.extra_headers` so the same APIM subscription header
that bridges the planner/reviewer also bridges aider's LiteLLM
calls. No provider's header name is hardcoded; the same env that
makes `--llm auto` work makes `--worker aider --apply` work, with
no additional configuration:

```bash
export LLM_API_KEY=<your key>
export LLM_API_BASE=https://llm-api.amd.com/Anthropic
export LLM_MODEL_NAME=claude-opus-4-6
export LLM_API_EXTRA_HEADERS='{"Ocp-Apim-Subscription-Key": "<your key>"}'
# Aider also needs ANTHROPIC_API_KEY / ANTHROPIC_API_BASE to discover
# the same endpoint; map them from LLM_*:
export ANTHROPIC_API_KEY="$LLM_API_KEY"
export ANTHROPIC_API_BASE="$LLM_API_BASE"
ai-cockpit "fix the failing test" --worker aider --apply --llm auto
```

> **Note on dependency conflicts:** `pip install aider-chat` may
> downgrade the `openai` package to a version that's incompatible
> with `langchain-openai`. This is harmless if you use `--llm auto`
> against an Anthropic-compatible endpoint (the OpenAI client is
> never loaded). If you need both, install aider into a separate
> virtualenv.

### Workflow YAMLs (v0.2 step 4 + v0.3 micro-step #2)

`ai-cockpit` ships two workflow YAMLs under `.ai-cockpit/workflows/`:

| File | Mode | Purpose |
| --- | --- | --- |
| `idea-to-mvp.yaml` | exploration | Default. Take a vague idea, produce a spec/slice. No automatic test commands. |
| `bug-fix.yaml` | task | Target a concrete failing test or bug. `max_loops: 3` to let the worker iterate; `defaults.verifier.test_commands` already includes `python -m pytest -q` and `ruff check .` so the reviewer has lint/test evidence even when you forget `--test-command`. |

Select with `--workflow`:

```bash
ai-cockpit "fix the failing test in tests/test_calc.py" \
    --workflow .ai-cockpit/workflows/bug-fix.yaml \
    --worker aider --apply --llm auto
```

Explicit CLI flags (`--mode`, `--max-loops`, `--test-command`) always
win over YAML defaults. YAML node order MUST match
`src/ai_cockpit/graph.py`; the loader refuses to start otherwise.

A runnable §15.1 end-to-end demo (deliberately broken calc + failing
pytest, fixed by aider via the `bug-fix.yaml` workflow) lives under
[`examples/broken_calc/`](examples/broken_calc/README.md).

### Checkpoint & resume (v0.2 step 3, on by default)

Every run is persisted via LangGraph's `SqliteSaver` to
`<root>/.ai-cockpit/history/checkpoints.sqlite` (or a custom
`--checkpoint-db PATH`). When you don't pass `--thread-id`, a fresh id
is auto-generated and printed to stderr — record it if you might want
to resume later.

If the process exits between nodes, you can continue the same run:

```bash
ai-cockpit "build a tiny CLI" --thread-id my-run-001
# ...later, after a kill or another session...
ai-cockpit --resume --thread-id my-run-001
```

To opt out entirely (e.g. for ephemeral CI checks or smoke tests):

```bash
ai-cockpit "smoke" --no-checkpoint
```

`--no-checkpoint` cannot be combined with `--thread-id`, `--resume`,
or `--checkpoint-db`.

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

## Known Limitations (v0.1, partially addressed in v0.2 step 1 + step 3)

- Planner and reviewer default to deterministic stubs; pass `--llm auto`
  with credentials to enable real LLM calls (v0.2 step 1).
- Coder is still a `StubWorker` that never modifies files.
- No human-in-the-loop interrupts; `ask_human` is reported but not interactive.
- Checkpoint/resume now persists graph state to SQLite (v0.2 step 3),
  but resumption is currently driven by the CLI only — no UI.
- No real worker integration (Aider, Cursor SDK, OpenHands intentionally excluded).

## Recommended Next Step

Replace the planner/reviewer stubs with real LLM calls behind a small
adapter, then introduce a single real coding worker (e.g. Aider) gated
behind explicit configuration. See
`docs/AI_COCKPIT_IMPLEMENTATION_PLAN_V0.md` §16 for the roadmap.
