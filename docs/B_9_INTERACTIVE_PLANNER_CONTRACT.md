# B.9 — Interactive Planner Mode (contract v0.1)

Status: **B.9a/B.9b/B.9c DONE & merged to master (PRs #44, #46, #47).
B.9d is SUPERSEDED-FINAL by B.10b (2026-05-17) — the Cursor-backed
interactive planner ships as `CursorPlannerBackend` and B.9d will not
be opened as a standalone gate.** This document captures the design
reviewed with the user on 2026-05-16 after the A2A / Cursor Plan Mode
/ Claude Code discussion.

> This contract adds a human-in-the-loop planning surface to
> `ai-cockpit`. The user explicitly opened B.9a. Later implementation
> steps still require their own explicit open-gate signal.

## 1. Why

The current planner stage is a one-shot text-to-JSON step inside
`ai-cockpit run`: it receives the user's idea and memory context, then
emits one `mvp_spec`, `acceptance_criteria`, and
`implementation_slice`. That is sufficient for narrow tasks, but it is
weak for the core exploration workflow described in
`docs/AI_COCKPIT_SPEC_V1.md`:

- complex ideas need clarification before execution;
- the planner should inspect the repository before proposing slices;
- trade-offs often need human judgment, not an autonomous guess;
- a good plan is normally revised through conversation.

Cursor Plan Mode is the right UX reference: the user proposes an idea,
the tool reads context, asks questions, proposes a draft, accepts
feedback, and only saves a plan once the human says it is ready.

B.9 therefore introduces an **interactive planner mode**:

```text
idea
-> interactive discussion with a planner
-> read-only repository grounding
-> draft / revise / clarify loop
-> explicit user save
-> docs/plans/<plan_id>.plan.yaml
```

This is deliberately different from an autonomous non-interactive
planner. Planning is where the human makes product and scope decisions;
execution is where `ai-cockpit` can be scripted.

## 2. Cursor Agent experiment results (2026-05-16)

The user tested the installed Cursor CLI binary (`agent`) to see
whether `ai-cockpit` could directly reuse Cursor Plan Mode instead of
building its own planner loop.

Observed runs:

| Run | Command shape | Observed result | Design implication |
| --- | --- | --- | --- |
| 1 | `agent --mode=plan --print --output-format=json --yolo "<meta question>"` | Returned valid JSON with a prose answer. No evidence that it read the repo. | `--print` can return one response, but this does not prove plan completion. |
| 2 | `agent --print --output-format=json --yolo "<read cli.py and propose 3-step plan>"` | Read repository context (`inputTokens` rose to ~44k, `cacheReadTokens` ~105k) but returned a progress narration instead of the requested final plan. | Default mode can use tools, but `--print` appears to stop after the first assistant turn. |
| 3 | `agent --mode=plan --print --output-format=json --yolo "<output ONLY YAML...>"` | Again read repo context and knew relevant files, but still returned progress narration, not YAML. | Prompt engineering did not turn `--print` into "run until task complete". |

Conclusion:

- Cursor CLI is useful as an **interactive** planning surface.
- Cursor CLI `--print` is not a reliable non-interactive plan generator
  for `docs/plans/*.plan.yaml`.
- B.9 should not depend on Cursor-specific completion semantics.
- A future Cursor backend is allowed as an optional enhancement, but
  `ai-cockpit` needs a builtin interactive planner so the feature works
  without Cursor, Claude Code, or any closed-source CLI.

## 3. Hard invariants (cannot be overridden)

| Invariant | Source | How B.9 honors it |
| --- | --- | --- |
| Planning is human-in-the-loop | spec §§4.2, 15 | The plan is not saved until the user explicitly runs `/save`. The planner may propose, but the user decides. |
| Single-threaded writer | spec §12 | B.9 is read-only until `/save`, and `/save` writes only a plan artifact. No source files are modified. Actual code changes still happen through the existing coder worker or future `plans run`. |
| No daemon / no background service | spec §12 | `ai-cockpit plan` is a foreground CLI REPL. It exits on `/save`, `/abort`, EOF, or Ctrl-C. |
| No UI / web app | spec §12 | The interface is plain terminal text, like `git rebase -i` or `aider`; no web or desktop UI. |
| No generic agent platform / swarm | spec §12 | One planner loop talks to one human. There is no agent-to-agent bus, A2A endpoint, worker marketplace, or multi-agent chat. |
| §9 evidence-only reviewer | spec §9 | Planner conversation and tool outputs never enter the reviewer prompt. They may shape a saved plan, but reviewer evidence remains `mvp_spec`, `acceptance_criteria`, `git_diff`, `git_status`, and `verification_result`. |
| Memory not auto-written | spec §3.2 | B.9 reads memory through existing intake-style helpers but never writes `.ai-cockpit/memory/*`. |
| Non-interactive safety | implementation rule | Real planning requires `stdin.isatty()`. If stdin is not a TTY, the command exits non-zero instead of hanging in CI or automation. |
| Generic provider principle | spec §12 | Builtin planner uses the existing `LLMProvider` abstraction. Cursor / Claude backends are optional, not required. |

## 4. Product boundary: "plan" vs "run"

B.9 intentionally separates two jobs:

### `ai-cockpit plan`

- interactive;
- human present;
- read-only tools allowed;
- produces or updates a plan artifact;
- never modifies source files;
- never invokes coder / verifier / reviewer.

### `ai-cockpit plans run`

- future B.6 execution command;
- non-interactive and scriptable;
- executes exactly one already-approved slice;
- may invoke coder / verifier / reviewer;
- may modify source files only through the existing worker boundary.

This split is the core design correction from the 2026-05-16
discussion: planning is a conversation; execution is a controlled
pipeline.

## 5. CLI surface

B.9 defines the interactive planning command. It is compatible with
B.6's plan artifact schema but does not require B.6 execution to be
implemented first.

```bash
ai-cockpit plan "<idea>" \
  [--root .] \
  [--output docs/plans/<plan_id>.plan.yaml] \
  [--llm {none|auto|anthropic|openai}] \
  [--backend {builtin|cursor}] \
  [--max-slices <int>] \
  [--max-turns 12] \
  [--max-tool-bytes 12000]
```

Defaults:

- `--backend builtin`
- `--llm auto`
- `--max-slices` omitted means unbounded, matching B.6's schema
  decision; when present, the planner treats it as a hard save-time
  validation cap.
- `--max-turns 12`
- `--max-tool-bytes 12000`
- `--output` omitted means the user must choose a path during `/save`,
  or the REPL derives `docs/plans/<slug>.plan.yaml` from the accepted
  plan id.

TTY guard:

- If stdin is not a TTY and `--llm none` is not selected, exit with:
  `Interactive planner requires a TTY. Use --llm none only for tests.`
- `--llm none` is the deterministic fixture mode for CI tests. It may
  run without a TTY and should not call real LLMs.

## 6. REPL user experience

The command starts by loading memory and repository metadata, then
enters a small command-oriented REPL.

Required commands:

| Command | Meaning |
| --- | --- |
| free text | User feedback or answer to the planner's question. |
| `/help` | Print command list. |
| `/draft` | Ask the planner to render the current best draft plan. |
| `/show` | Show the current draft plan YAML, if one exists. |
| `/revise <feedback>` | Explicitly request a revised draft. Equivalent to free text but clearer in transcripts. |
| `/tools` | List the read-only tools available to the planner. |
| `/save [path]` | Validate the current draft and write it to disk. This is the only write path. |
| `/abort` | Exit without writing. |

Session behavior:

1. On startup, the planner restates the idea and either asks a
   clarifying question or proposes a first draft.
2. The user can answer, challenge assumptions, request narrower slices,
   ask why a file is in scope, or request a new decomposition.
3. The planner may call read-only tools between turns to ground the
   discussion.
4. `/save` validates the draft against the plan schema and performs an
   atomic write. If validation fails, the file is not written and the
   REPL remains open.
5. `/abort`, EOF, or Ctrl-C exits without side effects.

The REPL may display short "reading ..." progress lines on stderr, but
it must not dump large file contents to the terminal unless the user
asks.

## 7. Planner backend protocol

B.9 introduces a small protocol so the interactive shell is independent
of the actual planning backend:

```python
class PlannerBackend(Protocol):
    name: str

    def start(self, request: PlannerRequest) -> PlannerResponse: ...
    def respond(self, turn: PlannerTurn) -> PlannerResponse: ...
    def draft(self) -> PlanDraft | None: ...
```

Conceptual data shapes:

- `PlannerRequest`: `idea`, `project_root`, `memory_context`,
  `max_turns`, `max_tool_bytes`.
- `PlannerTurn`: user text or REPL command payload.
- `PlannerResponse`: text to display, optional tool-call summaries,
  optional updated `PlanDraft`, optional `needs_user_input` flag.
- `PlanDraft`: in-memory representation matching B.6's plan schema.

This is a Python protocol, not an A2A protocol. No HTTP server,
JSON-RPC endpoint, agent card, or external agent registry is introduced.

## 8. Builtin backend (required)

The builtin backend is the default and must ship before optional
closed-source integrations.

Design:

- Use the existing `LLMProvider` abstraction.
- Keep state in process; no database or background worker.
- Let the LLM choose from a fixed read-only tool list.
- After each turn, either ask the user a question, update the draft,
  or show a concise rationale.
- Stop after `max_turns` and ask the user to `/save`, `/abort`, or
  restart with a larger budget.

Allowed read-only tools:

| Tool | Purpose | Guardrail |
| --- | --- | --- |
| `read_file(path)` | Inspect relevant source/docs. | Path must resolve under `--root`; binary files rejected; output clipped by `max_tool_bytes`. |
| `glob(pattern)` | Discover files. | Respects repo root; result count capped. |
| `ripgrep(pattern, path=None)` | Find symbols / existing patterns. | Result count and bytes capped. |
| `git_status()` | Understand dirty tree before planning. | Read-only `git status --short`. |
| `git_log(limit=20)` | Learn recent work and shipped slices. | Read-only; limit capped. |
| `read_existing_plans()` | List `docs/plans/*.plan.yaml` when present. | Read-only; schema errors summarized, not fatal. |

Forbidden tools:

- any file write / edit / delete / rename;
- shell execution beyond the fixed read-only git commands above;
- network fetch or web search;
- invoking coder workers (`aider`, Cursor edit mode, OpenHands, etc.);
- sending Slack / email / PR comments;
- writing `.ai-cockpit/memory/*`;
- calling another autonomous agent as a peer.

## 9. Optional Cursor backend (SUPERSEDED-FINAL by B.10b)

**SUPERSEDED-FINAL 2026-05-17 by B.10b (PR #53, `62976f9`).** The
Cursor-backed interactive planner is delivered by
`CursorPlannerBackend` under the broader B.10 Cursor-role-backends
contract; B.9d will not ship as a standalone gate. The sketch below
is preserved for historical context only.

A future B.9d may add:

```bash
ai-cockpit plan "<idea>" --backend cursor
```

Rules:

- It is optional. Absence of the `agent` / `cursor-agent` binary must
  produce a clear error and suggest `--backend builtin`.
- It is interactive-first. The Cursor backend may forward the user into
  Cursor's CLI conversation, but must still end by producing a local
  `PlanDraft` and requiring `/save`.
- It must not become the only way to plan.
- It must not relax §9 or §12.
- It must document privacy and quota implications because Cursor may use
  its own cloud service and account quota.

Cursor is therefore an accelerator for users who already have it, not a
dependency of `ai-cockpit`.

2026-05-16 addendum: this optional Cursor planner backend is now part of
the broader Cursor-backed role backend direction captured in
`docs/B_10_CURSOR_ROLE_BACKENDS_CONTRACT.md`. If B.10 is open-gated, do
not implement Cursor support as a one-off B.9 adapter; implement it as
the B.10 Cursor Planner backend that plugs into this B.9 REPL.

## 10. Plan artifact compatibility

B.9 saves the same plan artifact shape described in
`docs/B_6_CONTRACT.md`:

```yaml
schema_version: 1
plan_id: <slug>
created_at: <ISO8601 UTC>
idea: |
  <restated goal>
acceptance_criteria:
  - <whole-task criterion>
slices:
  - id: <slug>
    depends_on: []
    title: <one-line>
    why: <2-5 lines>
    scope_must:
      - <bullet>
    scope_out:
      - <bullet>
    dod:
      - <bullet>
    files_budget: <int <= 8>
    loc_budget: <int <= 400>
    test_commands: [<shell>]
```

If B.6 schema code does not exist yet, B.9a may introduce a shared
`plans/schema.py` module that B.6 later reuses. If B.6a has already
shipped, B.9 must reuse that module instead of creating a second schema.

Validation failures are user-facing and non-destructive:

- no partial file writes;
- no best-effort repair during `/save` unless the user asks the planner
  to revise the draft;
- explicit error messages naming the invalid field.

## 11. §9 anti-deception extension

B.9 adds one new regression test requirement:

> Planner conversation text and planner tool outputs must be absent from
> the reviewer LLM prompt bytes.

Test shape:

1. Run or construct a planner session where a tool returns a distinctive
   sentinel string, e.g. `PLANNER_TOOL_SECRET_SHOULD_NOT_REACH_REVIEWER`.
2. Save or load a plan derived from that session.
3. Execute the reviewer prompt builder on a state that references the
   plan or slice.
4. Assert the sentinel string is not present in the reviewer messages.

This test is separate from the existing coder-result anti-deception
tests. The reason is different: B.9's risk is not coder self-report, but
planning context being mistaken for verification evidence.

## 12. Implementation split

Each implementation PR must remain within the project cap: at most
8 files changed and at most 400 net LOC.

### B.9a — Planner protocol + REPL shell

Estimated 5 files / 300 net LOC.

- `src/ai_cockpit/planner_interactive/__init__.py` (new)
- `src/ai_cockpit/planner_interactive/types.py` (new protocol/data
  classes)
- `src/ai_cockpit/planner_interactive/repl.py` (new command loop)
- `src/ai_cockpit/cli.py` (wire `ai-cockpit plan` to the REPL; keep
  `--llm none` deterministic)
- `tests/test_interactive_planner_cli.py` (TTY guard, `/abort`,
  `/save` fixture path)

### B.9b — Read-only planner tools

Estimated 4 files / 300 net LOC.

- `src/ai_cockpit/planner_interactive/tools.py` (new tool registry)
- `src/ai_cockpit/planner_interactive/backends/builtin.py` (basic
  backend shell with deterministic `--llm none` path)
- `tests/test_interactive_planner_tools.py` (path containment,
  clipping, git command behavior)
- optional README note if needed for discoverability

### B.9c — LLM-backed builtin planner + schema save

Estimated 6 files / 350 net LOC.

- extend builtin backend to call `LLMProvider`
- add planner prompt template with the tool list and output contract
- parse / validate `PlanDraft`
- write atomically to `docs/plans/*.plan.yaml`
- tests for malformed draft, validation failure, and successful save

If B.6 schema code exists, reuse it. If not, this PR may introduce only
the schema subset needed for saving; B.6 must later import or extend it.

### B.9d — Optional Cursor backend (SUPERSEDED-FINAL by B.10b)

**SUPERSEDED-FINAL 2026-05-17.** Delivered by `CursorPlannerBackend`
in B.10b (PR #53, `62976f9`). B.9d will not ship as a standalone
gate; the original sketch (3 files / 180 net LOC,
`src/ai_cockpit/planner_interactive/backends/cursor.py`, CLI backend
selection, fake-`agent` tests) is preserved only for historical
context.

## 13. Threat model

| Threat | Mitigation |
| --- | --- |
| Interactive planner hangs in CI or automation | TTY guard; non-TTY exits immediately unless `--llm none` fixture mode is selected. |
| Planner accidentally edits source files | B.9 exposes no write tools except atomic plan save under `docs/plans/`; no coder worker invocation. |
| Tool output leaks into reviewer evidence | New §9 anti-deception test pins the absence of planner tool sentinel strings from reviewer prompt bytes. |
| LLM plans beyond the allowed per-slice budget | Plan schema validation rejects `files_budget > 8`, `loc_budget > 400`, missing `scope_out`, invalid dependencies. |
| User saves a bad plan because the assistant sounded confident | `/save` is schema-gated; the command prints validation errors and refuses partial writes. Human review is still required before executing slices. |
| Context explosion / high token spend | `max_turns`, `max_tool_bytes`, capped tool result counts, and clipped file output. Cost telemetry should print to stderr when provider usage data is available. |
| Cursor backend creates vendor lock-in | Builtin backend is required and default; Cursor backend is optional and deferred. |
| Planner conversation is mistaken for memory | B.9 never writes `.ai-cockpit/memory/*`; memory changes still require `memory accept`. |
| A2A / agent-platform scope creep | Protocol is in-process Python only; no Agent Card, no HTTP listener, no JSON-RPC task API. |

## 14. DoD — what "B.9 done" means

1. `ai-cockpit plan "<idea>" --llm none` can run in tests and save a
   deterministic valid plan fixture.
2. Interactive TTY mode supports `/help`, `/draft`, `/show`, `/revise`,
   `/save`, and `/abort`.
3. Builtin backend can call the existing LLM provider and read-only
   tools without adding new dependencies.
4. `/save` writes a valid plan artifact under `docs/plans/` using the
   B.6-compatible schema.
5. No source files are modified by `ai-cockpit plan`; only the plan
   artifact may be written.
6. New §9 anti-deception regression proves planner conversation/tool
   output does not enter reviewer prompt bytes.
7. All standard checks pass:
   `python -m pytest`, `ruff check .`, `mypy .`, and the existing
   smoke command with `--llm none --no-checkpoint`.

## 15. Out of scope

- No autonomous non-interactive plan generation as the primary UX.
  `--llm none` exists for tests, not for real planning.
- No automatic execution after `/save`. The next step is explicit:
  run a slice through B.6's `plans run` once that exists.
- No source edits from the planner.
- No background session persistence across terminal windows.
- No web UI, desktop UI, or IDE panel.
- No A2A server, MCP server, marketplace, plugin registry, or generic
  agent platform.
- No Cursor requirement.
- No memory writes.
- No Slack / email / PR comments.

## 16. Rollback plan

Because B.9 is additive and write-limited:

1. Stop using `ai-cockpit plan`.
2. Delete any draft `docs/plans/*.plan.yaml` files that were created
   during planning experiments.
3. Revert B.9c, then B.9b, then B.9a if needed. The existing
   single-slice `ai-cockpit run` path is unaffected.
4. Optional Cursor backend B.9d, if ever implemented, can be reverted
   independently.

## 17. Authorization rhythm

B.9a is open-gated and implemented as the minimal REPL/protocol shell.
B.9b and later are not open for implementation.

Allowed now:

- read this document;
- discuss or amend the contract;
- reference it from ROADMAP.

Not allowed until the next explicit user open-gate:

- adding B.9b read-only tools;
- adding B.9c LLM-backed builtin planner behavior;
- wiring Cursor / Claude Code / any external CLI backend (B.9d).

The implementation gate phrase is:

```text
open-gate B.9b
```

Any equivalent instruction from the user is acceptable, but it must be
explicit.
