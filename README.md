# AI Cockpit (v0.3)

A safe, runnable personal AI workflow management layer. Built per the
spec in [`docs/AI_COCKPIT_SPEC_V1.md`](docs/AI_COCKPIT_SPEC_V1.md), the
v0.1 implementation plan in
[`docs/AI_COCKPIT_IMPLEMENTATION_PLAN_V0.md`](docs/AI_COCKPIT_IMPLEMENTATION_PLAN_V0.md),
and the cron-driven backlog in [`docs/ROADMAP.md`](docs/ROADMAP.md).

The core loop is a deterministic LangGraph state machine:

```
idea input
-> load memory
-> planner produces MVP spec / acceptance criteria / implementation slice
-> coder runs the selected worker (stub | aider | cursor)
-> verifier collects git diff/status and runs shell checks
-> reviewer evaluates structured evidence only (spec §9)
-> decision chooses done/retry/ask_human
-> summary prints final result
-> memory pipeline writes a suggestion (human accepts via CLI)
```

This release ships:

- **Real LLM-backed planner & reviewer** behind a generic provider abstraction
  that works with enterprise proxies (`LLM_API_KEY` / `LLM_API_BASE` /
  `LLM_MODEL_NAME` / `LLM_API_EXTRA_HEADERS`).
- **Three worker backends:** `stub` (default, no edits), `aider`
  (`--worker aider --apply`), and `cursor` (`--worker cursor`, via the
  B.10 Cursor role-backend adapter).
- **SQLite checkpoint + `--thread-id` / `--resume`** so a run survives
  process exit.
- **Workflow YAML** actually drives the graph (`idea-to-mvp.yaml`,
  `bug-fix.yaml`); `ai-cockpit workflows list / validate` inspects them.
- **Memory suggestion pipeline:** every run writes a JSON suggestion under
  `.ai-cockpit/suggestions/`; `ai-cockpit memory list / show / accept`
  surfaces and applies them. No write to `.ai-cockpit/memory/*` ever
  happens without `accept_suggestion` (hard rule §3.2).
- **Multi-step planner & plan artifact (B.6):** `ai-cockpit plan "<idea>"`
  drops the user into an interactive planner REPL; `/save` writes
  `docs/plans/<plan_id>.plan.yaml`; `ai-cockpit plans run <plan_id>
  <slice_id>` executes one slice with dependency-marker checks.
- **Cursor-backed role backends (B.10):** optional `cursor` planner /
  worker / reviewer / writer, discovered via `ai-cockpit cursor status`.
- **Cost dashboard (B.3):** `ai-cockpit cost [--since DATE] [--format
  text|json]` aggregates per-run token / cost metrics from the checkpoint
  DB.
- **Pre-run dirty-tree pre-check (A.7):** `--worker aider --apply` refuses
  to start on top of unrelated working-tree changes unless
  `--allow-dirty-tree` is passed.

It deliberately does **not** include a UI, daemon process, cloud
execution backend, multi-user mode, plugin marketplace, agent-to-agent
swarm, or any auto-outbound email / Slack / PR comments. Those are
permanent §12 boundaries — see `docs/ROADMAP.md` Section C.

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
| `--allow-dirty-tree` | off | Bypass the A.7 pre-run dirty-tree pre-check. By default `--worker aider --apply` refuses to start when uncommitted changes exist outside the aider runtime allow-list (`.aider.*`, `.ai-cockpit/suggestions/`, `.ai-cockpit/history/`). |
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

**Aider runtime artifacts are gitignored (A.8).** When aider runs it
writes `.aider.chat.history.md`, `.aider.input.history`, and a
`.aider.tags.cache.v4/` directory next to your project. These are
aider's own session state — chat transcript, input history, and source
tag cache — not ai-cockpit output, so the repo `.gitignore` excludes
them (plus a generic `.aider*` glob as a safety net for any future
filename aider adds). After a `--worker aider --apply` run,
`git status --short` should not list any `.aider.*` paths; if it does,
that's a regression in this allow-list, not normal output.

**Pre-run dirty-tree pre-check (A.7).** Before spawning aider, the
CLI inspects `git status --porcelain` and refuses to proceed if
there are uncommitted modifications to paths outside the aider
runtime allow-list (`.aider.*`, `.ai-cockpit/suggestions/`,
`.ai-cockpit/history/`). The error message lists each blocking
path with a one-line `git checkout -- <file>` hint so you can
either commit, stash, or revert before retrying. To deliberately
let aider edit on top of a dirty tree, pass `--allow-dirty-tree`.
This guard only fires for `--worker aider --apply`; preview-only
runs (`--worker aider` without `--apply`) and stub runs are
unaffected.

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

Discover and pre-flight workflows from the CLI (v0.3 A.4):

```bash
ai-cockpit workflows list                          # tab-separated table
ai-cockpit workflows validate .ai-cockpit/workflows/bug-fix.yaml
```

`workflows list` prints `name | mode | max_loops | test_commands_count`
for each `*.yaml` / `*.yml` under `<root>/.ai-cockpit/workflows/` and
flags malformed files inline (per-row `INVALID:` marker, not a hard
error) so a single broken file doesn't hide healthy ones.
`workflows validate PATH` loads through the same `load_workflow`
parser the run loop uses and prints `OK` (exit 0) or the specific
`WorkflowError` (non-zero exit), suitable for CI pre-flight.

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

### Summary rendering (v0.5)

`ai-cockpit run` finishes by printing a structured summary block. The
default view is **colored, sectioned text** (Idea / Plan / Execution /
Review) with the decision rendered as a bracket token (`[DONE]` /
`[ASK_HUMAN]` / `[RETRY]`) for easy grep. Color auto-detects from
stdout — pipes, redirects, and `NO_COLOR=1` get ANSI-free output, and
the greppable title `AI Cockpit — Run Summary` is always present. The
plain v0.1 layout remains available programmatically via
`ai_cockpit.render.render_summary_plain` for tests and tools that
depend on the historical column-aligned shape; `final_summary` in the
checkpoint DB also continues to store that plain text byte-for-byte so
historical replay keeps working.

Example:

```bash
ai-cockpit "Build a tiny CLI that summarizes meeting notes" \
  --root . \
  --max-loops 1 \
  --test-command "python -m pytest -q"
```

## Roadmap

Next work is tracked in [`docs/ROADMAP.md`](docs/ROADMAP.md): a
cron-safe backlog (Section A) that runs unattended overnight, a
needs-user-direction backlog (Section B), and the permanent
out-of-scope list (Section C, mirroring spec §12).

## Project Layout

```
pyproject.toml
README.md
AUTOMATION_PROMPT.md
AGENTS.md
.ai-cockpit/
  memory/             # markdown context loaded at intake (human-curated)
  workflows/          # workflow templates that drive the graph
  history/            # SQLite checkpoint DB (gitignored)
  suggestions/        # per-run memory suggestions (gitignored)
docs/
  AI_COCKPIT_SPEC_V1.md
  AI_COCKPIT_IMPLEMENTATION_PLAN_V0.md
  ARCHITECTURE.md     # single-document map of the current codebase (A.6)
  ROADMAP.md          # cron-safe + needs-user-direction backlogs
  V0_2_COMPLETION.md  # v0.2 exit-gate evidence
  V0_3_MILESTONES.md  # v0.3 narrative milestones
  B_*_CONTRACT.md     # one locked design contract per Section B item
src/ai_cockpit/
  cli.py              # click entry point + memory/workflows/plans subgroups
  config.py
  state.py            # TaskState TypedDict
  graph.py            # LangGraph compile + node wiring
  checkpoint.py       # SqliteSaver + thread_id helpers
  workflow.py         # workflow YAML parser + invariants
  cost.py             # B.3 cost dashboard aggregator
  nodes/              # intake, planner, coder, verifier, reviewer, decision, summary
  workers/            # base + stub_worker + aider_worker
  cursor_adapter/     # B.10 planner / worker / reviewer / writer backends + discovery
  llm/                # generic provider abstraction + prompts
  memory/             # memory loader + suggestion pipeline
  plans/              # B.6 plan schema + atomic loader + dependency check
  planner_interactive/# B.9 interactive planner REPL + tools + builtin backend
  tools/              # git + shell helpers
examples/
  broken_calc/        # §15.1 runnable end-to-end demo fixture
tests/                # 259 tests on master at v0.3 close
```

For a single-document map of how these pieces fit together — graph
wiring, state ownership, worker / LLM protocols, the memory pipeline,
workflow YAML, and the spec §9 anti-deception evidence flow — read
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). It is descriptive
(reflects `master`), not aspirational; roadmap items still live in
[`docs/ROADMAP.md`](docs/ROADMAP.md).

## Tests

```bash
source .venv/bin/activate
python -m pytest
```

## Known Limitations (v0.3 close)

- Planner and reviewer fall back to deterministic stubs when no LLM
  credentials are configured; `--llm auto` requires `LLM_API_KEY` (or
  `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`).
- The `cursor` planner / worker / reviewer / writer backends require a
  Cursor CLI binary on `PATH` (auto-discovered as `agent` →
  `cursor-agent` → `cursor`, overridable via `--binary`). Without one,
  the CLI prints `CursorUnavailableError` and suggests `--backend builtin`.
- `ask_human` is reported through the run summary; there is no
  interactive interrupt mid-graph.
- Checkpoint/resume is CLI-driven only; there is no UI.
- The v0.4 end-to-end exit-gate run (real LLM, real repo, zero human
  intervention) has not yet been operator-executed — see B.5 below.

## Recommended Next Step

Run the **v0.4 exit-gate** described in
[`docs/B_5_CONTRACT.md`](docs/B_5_CONTRACT.md) §4: a complete `plan →
plans run → verifier → reviewer → memory` loop against
`examples/broken_calc/` under real LLM credentials, with cost ≤ $1,
wall-time ≤ 15 min, zero human intervention, and the spec §9
anti-deception suite green. Cron is **not** authorized to execute the
gate run; it is operator-driven by design (hard rule §3.5). Capture
the run in `docs/V0_4_EXIT_EVIDENCE.md` and merge to declare v0.4 done.

For incremental work that does not require user open-gate signal, see
`docs/ROADMAP.md` Section A (currently 8/8 complete) and the gated
Section B items.
