# AI Cockpit — Architecture (v0.3)

This document is the single map of how `ai-cockpit` fits together as
of v0.3. It is descriptive, not aspirational: every section reflects
code on `master`. Roadmap items live in
[`docs/ROADMAP.md`](ROADMAP.md); hard rules live in
[`docs/AI_COCKPIT_SPEC_V1.md`](AI_COCKPIT_SPEC_V1.md). When this
document and source disagree, the source wins — file a follow-up to
fix the doc.

## 1. The graph (`src/ai_cockpit/graph.py`)

A single `langgraph.graph.StateGraph` over `TaskState`. Edges are
linear except for the `decision` node, which conditionally loops
back to `coder`:

```
START -> intake -> planner -> coder -> verifier -> reviewer -> decision
                                                                  |
                       (decision == "retry") <--------------------+
                                                                  |
                       (decision in {done, ask_human, stop}) -> summary -> END
```

Compilation accepts an optional `checkpointer` (LangGraph
`SqliteSaver`) and `interrupt_before` list; both are off by default.

### Node responsibilities

- **intake** (`nodes/intake.py`) — reads `user_input`, defaults
  `mode` to `exploration`, loads the markdown memory blob via
  `memory.loader.load_memory` into `memory_context`. Initializes
  `loop_count` / `max_loops`.
- **planner** (`nodes/planner.py`) — turns `idea` + `memory_context`
  into `mvp_spec`, `acceptance_criteria`, `implementation_slice`.
  Uses `LLMProvider` when one is wired; falls back to a
  deterministic stub on any failure (LLM error, non-JSON reply,
  missing/empty `acceptance_criteria`, missing `implementation_slice`).
- **coder** (`nodes/coder.py`) — selects a `Worker`
  (`stub` or `aider`), builds a `WorkerRequest` from the planner
  outputs, runs it, writes the worker's free-form `summary` into
  `coder_result`. Increments `loop_count`.
- **verifier** (`nodes/verifier.py`) — deterministic evidence
  collection: `git status --short`, `git diff`, and the configured
  `test_commands` (skipped under `dry_run`). Captures exit code,
  stdout, stderr verbatim into `VerificationResult.commands`.
- **reviewer** (`nodes/reviewer.py`) — judges using **only** the
  structured evidence dict from `llm/prompts.build_reviewer_evidence`.
  Optional LLM verdict is overridden by `_enforce_hard_rules` whenever
  a verification command failed. See §7.
- **decision** (`nodes/decision.py`) — `done` if review passed;
  otherwise `retry` while `loop_count < max_loops`; otherwise
  `ask_human`. The `stop` variant is reserved for future explicit
  abort paths. `route_after_decision` returns the next edge name.
- **summary** (`nodes/summary.py`) — renders the human-readable
  block and writes it into `final_summary`. Side-effect: prints to
  stdout so the CLI run leaves a trace.

## 2. The state object (`src/ai_cockpit/state.py`)

`TaskState` is a `TypedDict(total=False)`. Each node populates the
keys it owns; LangGraph's default per-key overwrite merge applies.
The table below names the writer/reader pairs:

| Field                 | Written by | Read by                              |
| --------------------- | ---------- | ------------------------------------ |
| `user_input`          | caller     | intake                               |
| `mode`                | intake     | summary                              |
| `project_root`        | caller     | intake, coder, verifier              |
| `memory_context`      | intake     | planner                              |
| `idea`                | intake     | planner, coder, summary              |
| `mvp_spec`            | planner    | reviewer (evidence), summary         |
| `acceptance_criteria` | planner    | reviewer (evidence), summary         |
| `implementation_slice`| planner    | coder, summary                       |
| `coder_result`        | coder      | reviewer **only for `_deterministic_review` shape checks (stub detection); MUST NOT enter the LLM prompt**, summary |
| `git_diff`/`git_status` | verifier | reviewer (evidence), summary         |
| `verification_result` | verifier   | reviewer, decision, summary          |
| `review_result`       | reviewer   | decision, summary                    |
| `decision`            | decision   | router, summary                      |
| `loop_count`/`max_loops` | intake/coder | decision                        |
| `dry_run`             | caller     | verifier, reviewer (stub-mode hint)  |
| `test_commands`       | caller/YAML | verifier                            |
| `final_summary`       | summary    | CLI (printed)                        |

## 3. The worker protocol (`src/ai_cockpit/workers/`)

Workers implement a tiny `Protocol`:

```python
class Worker(Protocol):
    name: str
    def run(self, request: WorkerRequest) -> WorkerResult: ...
```

`WorkerRequest` is frozen and carries `objective`,
`implementation_slice`, `acceptance_criteria`, `project_root`,
`dry_run`. `WorkerResult` carries `summary` (free-form,
self-reported), `changed_files`, `notes`, and an optional
`metrics: dict[str, float]` (token/cost numbers parsed from
worker stdout in v0.3 A.3 — absence means "unknown", never zero).

Two concrete workers ship:

- **`StubWorker`** (`workers/stub_worker.py`) — never modifies
  files. Always returns a summary starting with `"Stub worker:"`
  so the reviewer can detect stub mode and the no-diff/no-commands
  case is allowed.
- **`AiderWorker`** (`workers/aider_worker.py`) — preview-only by
  default. With `--apply` it spawns the `aider` CLI with flags
  `--yes-always --no-stream --no-auto-commits --no-gitignore`,
  inheriting the current process env so LLM credentials reach it
  unchanged. When `LLM_API_EXTRA_HEADERS` and `LLM_MODEL_NAME`
  are both set, AiderWorker auto-generates a temporary
  `--model-settings-file` with `extra_params.extra_headers` so
  APIM gateways work end-to-end. The aider stdout is parsed for
  token/cost metrics (A.3).

The contract that pinned the AiderWorker shape is **PR #20**.
Future workers (Cursor SDK, OpenHands) plug in by adding a new
`Worker` implementation plus a branch in `coder._select_worker`.

## 4. The LLM provider abstraction (`src/ai_cockpit/llm/provider.py`)

`LLMProvider` is also a `Protocol`:

```python
class LLMProvider(Protocol):
    name: str
    def complete(self, *, system: str, user: str) -> str: ...
```

`build_llm(mode)` reads env in this priority order:

1. **Generic** — `LLM_API_KEY` + `LLM_API_BASE` + `LLM_MODEL_NAME`.
   The only set that works with enterprise gateways such as
   `https://llm-api.amd.com/Anthropic`.
2. `ANTHROPIC_API_KEY` (default base `https://api.anthropic.com`).
3. `OPENAI_API_KEY` (default base `https://api.openai.com/v1`).

Protocol auto-detection: `LLM_PROVIDER=anthropic|openai` is an
explicit override; otherwise an `LLM_API_BASE` containing
`"anthropic"` or a model name starting with `"claude"` picks the
Anthropic-compatible client; everything else picks the OpenAI-
compatible client.

### `LLM_API_EXTRA_HEADERS` bridge

This optional env var holds a JSON object. When present it is
forwarded to the underlying client as `default_headers`. This is
the **only** way to inject gateway-specific auth headers (e.g.
APIM's `Ocp-Apim-Subscription-Key`) without hardcoding any
provider's header name in the codebase — required by spec §12's
generic-provider rule. Malformed JSON or non-object payloads are
logged at WARNING and silently ignored; runs never crash on bad
env. `LLMProvider`-construction failures (missing optional
package, etc.) likewise fall back to stub mode.

## 5. The memory pipeline (`src/ai_cockpit/memory/`)

### 5a. Read path (`loader.py`)

At intake, `load_memory(project_root)` concatenates the existing
markdown files under `<root>/.ai-cockpit/memory/` (in the fixed
order `user.md`, `project.md`, `preferences.md`) into a single
string. Missing files / empty files are skipped silently. This is
read-only and synchronous; no other node reads memory directly.

### 5b. Suggestion path (`suggestions.py`, v0.2 step 5)

After a run, `build_suggestion_from_state(state)` may synthesize a
`Suggestion` JSON blob. It is written to
`<root>/.ai-cockpit/suggestions/<id>.json`, **never directly into
`memory/`**. The hard rule (spec §3.2): memory files are only
modified by a human accepting a suggestion via
`ai-cockpit memory accept <id>`, which appends the suggestion body
to its `target` file and archives the JSON into
`suggestions/applied/`.

Filter rules currently in force (post PR #26):

- Only `decision in {"done", "ask_human"}` runs produce
  suggestions; everything else is silently dropped.
- An `ask_human` run with an empty `git_diff` is also dropped —
  pure coder-noop / reviewer-rejected-the-stub runs add only noise.
- Required fields: non-empty `idea` and non-empty `mvp_spec`.

Only `operation: "append"` to one of `MEMORY_FILES` is allowed
today; `Suggestion.validate` raises `SuggestionError` otherwise.

## 6. The workflow YAML (`src/ai_cockpit/workflow.py`)

Two templates ship under `.ai-cockpit/workflows/`:

| File              | Mode        | `max_loops` | Default `verifier.test_commands`           |
| ----------------- | ----------- | ----------- | ------------------------------------------ |
| `idea-to-mvp.yaml`| exploration | 1           | (none)                                     |
| `bug-fix.yaml`    | task        | 3           | `python -m pytest -q`, `ruff check .`      |

`parse_workflow` enforces three invariants — any violation raises
`WorkflowError` and the run aborts before any node executes:

1. `nodes:` **must** equal the compiled graph's
   `CANONICAL_NODE_ORDER` (`intake`, `planner`, `coder`,
   `verifier`, `reviewer`, `decision`, `summary`). The YAML can't
   silently drift out of sync.
2. `mode` must be one of `{"exploration", "task"}` and `max_loops`
   a non-negative int.
3. `defaults:` keys must reference known nodes.

Defaults layering: explicit CLI flags (`--mode`, `--max-loops`,
`--test-command`) always win over YAML; YAML wins over hardcoded
v0.1 fallbacks. `ai-cockpit workflows list` / `workflows validate`
(v0.3 A.4) surface this loader for pre-flight without running the
graph.

## 7. Anti-deception evidence flow (spec §9)

The single hardest invariant in this codebase. Three layers
defend it; **all three** ship today.

### Layer 1 — Prompt shape (`llm/prompts.py`)

`build_reviewer_evidence(state)` returns a dict with **exactly**
these keys:

- `mvp_spec`, `acceptance_criteria`
- `git_status`, `git_diff`
- `verification.passed`
- `verification.commands[*].{command, exit_code, stdout_tail, stderr_tail}`

It deliberately **omits** `coder_result`. The reviewer LLM never
sees the worker's narrative self-report — only the evidence the
verifier collected. `build_reviewer_messages` is the only path
that constructs the reviewer LLM call, and it requires an evidence
dict built by the function above.

### Layer 2 — Deterministic fallback (`nodes/reviewer.py`)

If the LLM reply fails to parse as JSON, returns malformed
fields, or raises, `_deterministic_review` runs instead. It
explicitly:

- Marks `risk: high` and `passed: False` on any non-zero exit.
- Refuses to pass a run with no diff and no commands unless
  `dry_run` is on or `coder_result` starts with `"Stub worker:"`.
- Flags "diff without commands" as `risk: medium`.

### Layer 3 — Hard-rule floor (`_enforce_hard_rules`)

Runs **after** the LLM (or fallback) verdict and is unconditional:
if any captured command has a non-zero exit code, `passed` is
forced to `False`, `risk` to `high`, and the failing command is
appended to `issues` if not already mentioned. No prompt can talk
the reviewer past this floor.

### Test coverage

`tests/test_llm_planner_reviewer.py` (16 tests, including the
A.5 hardening trio) pins:

- the prompt-shape guarantee (`coder_result` byte-string absent
  from the captured messages, even when it imitates a verdict)
- the deterministic-fallback escalation when JSON parsing fails
- the hard-rule override when the LLM tries to pass a failing run

CI runs these with a fake `langchain_anthropic` injected via
`sys.modules`, so no real LLM call ever fires — consistent with
the spec §12 "no real LLM in CI" rule.

## 8. CLI & checkpointing (`src/ai_cockpit/cli.py`, `checkpoint.py`)

The `ai-cockpit` entry point is `click`-based. Checkpointing is
on by default: each run gets a `thread_id` (auto-minted or
passed via `--thread-id`) and is persisted through
`SqliteSaver` to `<root>/.ai-cockpit/history/checkpoints.sqlite`
(overridable via `--checkpoint-db`). `--resume --thread-id ID`
re-enters the graph with `invoke(None)` so LangGraph picks up
from the last saved checkpoint. `--no-checkpoint` disables
persistence entirely (used by the smoke-test invocation in the
pre-push checklist).

The `ai-cockpit memory` and `ai-cockpit workflows` sub-command
groups are pure status/inspection paths — they never invoke the
graph and never call out to an LLM.

## 9. What this document deliberately does **not** cover

- Future-tense plans (see `docs/ROADMAP.md` Sections A & B).
- Multi-step planner / plan-artifact design (see
  `docs/B_6_CONTRACT.md`; gated, not implemented).
- Permanent out-of-scope items (spec §12 and `ROADMAP.md`
  Section C): UI, daemon, cloud execution, ruflo, plugin
  marketplace, multi-user permissions.

If you came here expecting one of those and want to add it,
the answer is "open a new step contract first" — never expand
this doc to cover code that doesn't exist on `master`.
