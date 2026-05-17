# Roadmap

Single source of truth for what ships next. v0.2 is fully complete
(see `docs/V0_2_COMPLETION.md` for the exit-gate evidence). v0.3 has
shipped the Aider worker, the filter for trivial memory suggestions,
the `bug-fix.yaml` workflow, and the runnable `examples/broken_calc/`
demo. From this point forward, every line of this document defines
a self-contained micro-step a cron tick (or a single user session)
can finish without ambiguity.

If anything below is unclear, STOP and ask the user — do not guess.

## Section A — cron-safe backlog (overnight queue)

These items are deterministic, read-only-leaning, and have no
external dependencies (no real LLM, no network). A cron run is
authorized to start them in order, one PR per tick, without any
further user direction.

Per-item rules:

- One step = one branch = one PR (same hard rules as v0.2).
- ≤ 8 files changed, ≤ 400 net LOC per PR. Split if exceeded —
  the v0.3 Step 2a/2b split is the canonical pattern.
- All four pre-push checks must pass locally before push:
  `python -m pytest && ruff check . && mypy . && ai-cockpit
  "smoke ..." --max-loops 1 --dry-run --llm none --no-checkpoint`.
- Use `mypy .` (NOT just `mypy src`) — CI checks tests too.
- Never commit anything matching `.ai-cockpit/memory/*` directly;
  go through `accept_suggestion` only. (Hard rule §3.2.)

### A.1 — `ai-cockpit status` subcommand  ✅ DONE (PR #31, 2026-05-16)

Shipped by ai-cockpit itself via `--worker aider --apply --llm auto`
on 2026-05-16. The generated source matched this contract verbatim
and merged without human edits. See `docs/V0_3_MILESTONES.md` for
the full run record (prompt, cost, leftover-state confound,
end-user-visible output).

**Why:** today a user wanting to know "what's pending? what LLM
will be used? which workflows are available?" has to grep the
filesystem. A read-only `status` subcommand surfaces all of that
without touching anything.

**Scope (must):**

- New `status` subcommand on the `main` group in `src/ai_cockpit/cli.py`.
- Output (plain text, deterministic ordering):
  - `version: <ai_cockpit.__version__ or package metadata>`
  - `project_root: <resolved path>`
  - `llm_mode_none: ok` (always — proves the import chain works)
  - `llm_mode_auto: <build_llm('auto').name OR 'unavailable (no creds)'>`
    — must NEVER actually call the LLM, just construct the provider.
  - `workflows: <comma-separated YAMLs found in .ai-cockpit/workflows/>`
  - `suggestions_pending: <int count from list_suggestions()>`
  - `checkpoint_db: <path if it exists, else 'none'>`
  - Each line single-line, tab- or colon-separated, easy to grep.

**Out of scope:** No interactive mode. No table formatting libs. No
real LLM call. Do not query an external API.

**DoD:** new pytest test exercises the subcommand via CliRunner,
asserts each line is present. Existing 99 tests still green.

**Files touched (budget):** ≤ 3 files (cli.py + 1 test + maybe a
README line). ≤ 150 net LOC.

### A.2 — `memory list` quality-of-life upgrades

**Why:** the §15.1 demo run wrote a real `done` suggestion; users
will accumulate dozens of these over weeks. The current `ai-cockpit
memory list` output is one line per suggestion (id\ttarget\top\tfirst-line)
with no aggregate.

**Scope (must):**

- After the per-suggestion lines, print a one-line summary:
  `total: N (done: A, ask_human: B)`.
- Sort suggestions by `created_at` descending (newest first) instead
  of by id alphabetic. The current id format starts with a timestamp
  so this is mostly cosmetic, but explicit `created_at` parsing is
  more robust.
- Each row gains a leading `age: <Nd Nh ago>` column derived from
  `created_at` vs `datetime.now(UTC)`. Use a small helper, no new
  dependencies.

**Out of scope:** No interactive filtering. No new flags. No
modification to suggestion JSON shape. No write paths touched.

**DoD:** the existing list-tests in `tests/test_memory_cli.py` are
adjusted; one new test exercises the summary line and age column on
a fixture of three suggestions with different timestamps and decisions.

**Files touched:** ≤ 3 (cli.py + tests/test_memory_cli.py + maybe a
README line). ≤ 200 net LOC.

### A.3 — token / cost extraction from aider stdout

**Why:** PR #28's demo run showed `Tokens: 6.7k sent, 316 received.
Cost: $0.04 message, $0.04 session.` lines in aider's stdout. Those
are valuable signal for cost-bounded workflows but are buried in a
free-text blob today.

**Scope (must):**

- In `src/ai_cockpit/workers/aider_worker.py`, after a real (non
  dry-run) aider invocation, regex-extract token + cost lines from
  the captured stdout and surface them as a small structured dict
  under `WorkerResult.notes` (or a new `metrics` field on the
  dataclass — pick one and document the choice).
- If aider's stdout shape changes and the regex misses, fall back
  silently to the current behavior — no crash.
- No new dependencies; standard library `re` only.

**Out of scope:** no aggregation across runs (that's a v0.4
concern). No persistence beyond what's already in the checkpoint
DB. Do not change `WorkerRequest` shape.

**DoD:** parameterized tests on canned aider stdout fixtures
covering the documented Tokens / Cost format AND missing/malformed
inputs. All existing aider-worker tests still pass.

**Files touched:** ≤ 3 (aider_worker.py + tests/test_aider_worker.py
+ optional `base.py` if adding a metrics field). ≤ 200 net LOC.

### A.4 — workflow YAML `list` + `validate` subcommands

**Why:** v0.3 micro-step #2 shipped a second workflow. As more land,
discoverability and pre-flight validation matter.

**Scope (must):**

- `ai-cockpit workflows list [--root PATH]`: prints
  `name | mode | max_loops | test_commands_count` for each
  `*.yaml` under `<root>/.ai-cockpit/workflows/`.
- `ai-cockpit workflows validate PATH`: load the YAML through
  `load_workflow`, print `OK` on success, print specific
  `WorkflowError` messages on failure with non-zero exit.
- Add a `workflows` `click.Group` analogous to the existing
  `memory` group; route through `_DefaultGroup` shim so the v0.1
  positional form is unaffected.

**Out of scope:** no editing / writing workflow files via CLI. No
schema migration. No new YAML fields.

**DoD:** new tests under `tests/test_workflow.py` for each
subcommand. The existing repo's two YAMLs (`idea-to-mvp.yaml` and
`bug-fix.yaml`) round-trip through `validate` and `list` cleanly.

**Files touched:** ≤ 3 (cli.py + tests/test_workflow.py + README).
≤ 250 net LOC.

### A.5 — anti-deception edge-case tests (spec §9 hardening)

**Why:** the four mandatory mock-LLM anti-deception tests cover the
canonical cases (empty diff with upbeat coder, etc.). The §15.1
demo session surfaced realistic edge cases worth pinning explicitly.

**Scope (must):** add at least 3 new mock-LLM tests in
`tests/test_llm_planner_reviewer.py`:

1. The coder claims to have run tests successfully, but
   `verification_result.commands` is empty. The reviewer LLM is
   given an upbeat fake reply ("looks fine") — reviewer-node logic
   MUST still escalate (`passed: False`) because there's no test
   evidence.
2. The coder pastes what looks like a reviewer verdict into its
   own `coder_result` ("review: passed, low risk"). The reviewer
   prompt must NOT contain that string. Re-assert the existing
   sys.modules-shim pattern.
3. The planner LLM returns valid JSON but acceptance_criteria is
   empty. The reviewer MUST refuse to pass (any diff trivially
   "satisfies" zero criteria, which is the deception vector).

**Out of scope:** no changes to reviewer / planner production code.
Tests assert existing behavior; if a test reveals a hole, STOP and
open a separate bug PR — do not silently fix it as part of this step.

**DoD:** new tests green; existing 99 tests still green.

**Files touched:** ≤ 1 (test file only). ≤ 200 net LOC.

### A.7 — pre-run dirty-tree pre-check (surfaced by A.1 milestone)

Originally B.7 — promoted into the cron-safe queue by the 2026-05-16
24h-autonomous authorization (see `V0_3_STATUS.md`). Self-contained
CLI change, mock-friendly tests, no LLM dependency.

**Scope (must):** before any `--worker aider --apply` invocation,
inspect `git status --porcelain` on `--root`:

- If there are uncommitted modifications to files NOT inside the
  aider runtime allow-list (`.aider.*`, `.ai-cockpit/suggestions/`,
  `.ai-cockpit/history/`), print a warning listing each path and a
  one-line `git checkout -- <file>` hint.
- Refuse to proceed unless `--allow-dirty-tree` is passed.
- `--worker stub` / `--llm none` / dry-run paths are unaffected.

**Out of scope:** no diff inspection. No three-way merge. No
attempt to auto-revert. Just block + report.

**DoD:** tests that simulate dirty-tree via tmp_path git repos and
assert refusal vs `--allow-dirty-tree` succeeds.

**Files touched:** ≤ 3 (cli.py + tests + README). ≤ 200 net LOC.

### A.8 — gitignore `.aider.*` runtime artifacts

Originally B.8 — promoted into the cron-safe queue by the
2026-05-16 24h authorization. Trivial.

**Scope (must):** add `.aider.chat.history.md`, `.aider.input.history`,
`.aider.tags.cache.v4/`, and the generic `.aider*` glob to the repo
`.gitignore`. Document in README under "Coder worker (v0.3 step 2)"
why these are aider's runtime side-artifacts, not ai-cockpit output.

**Out of scope:** no AiderWorker change. No auto-cleanup at run time
(future improvement, separate step).

**DoD:** after the next AiderWorker run, `git status --short` does
not list `.aider.*` paths. Existing tests still green.

**Files touched:** ≤ 2 (.gitignore + README). ≤ 20 net LOC.

### A.6 — `docs/ARCHITECTURE.md`

**Why:** future contributors (including a future cron-self) need a
single document explaining how the pieces fit together without
spelunking source.

**Scope (must):** one new markdown file under `docs/`, ~200-300
lines. Sections:

1. The graph: list each node (`intake`, `planner`, `coder`,
   `verifier`, `reviewer`, `decision`, `summary`) and its
   responsibility in 2-3 lines each.
2. The state object (`TaskState`): the fields, who writes them,
   who reads them.
3. The worker protocol: how `StubWorker` and `AiderWorker` plug
   in. Point to PR #20's contract.
4. The LLM provider abstraction: env priority, protocol auto-
   detection, `LLM_API_EXTRA_HEADERS` bridge, why no provider's
   header name is hardcoded (spec §12 generic-provider rule).
5. The memory pipeline (Step 5a/5b): suggestion JSON shape,
   filter rules (post-PR #26), the hard rule §3.2 invariant.
6. The workflow YAML: node-order validation, defaults layering,
   `bug-fix.yaml` vs `idea-to-mvp.yaml`.
7. Anti-deception evidence flow: which fields enter the
   reviewer prompt, which do not.

**Out of scope:** no code changes. No diagrams that aren't ASCII.
No future-tense roadmap content (that lives here in `ROADMAP.md`).

**DoD:** doc file present, mentioned in top-level README's "Project
Layout" section. No tests required (it's prose).

**Files touched:** ≤ 2 (new doc + README link). ≤ 350 net LOC
(this is the largest of the A items).

---

## Section B — needs-user-direction backlog (do NOT start in cron)

These items require human judgment that cron is not authorized to
exercise overnight. Each has a written-up sketch so when the user
DOES come back and say "go", the contract is ready.

### B.1 — second real worker (Cursor SDK or OpenHands)

Spec §14 lists alternatives. Pick ONE before starting. Same shape
as the Aider worker (Worker protocol, `--worker <name>` CLI choice,
dry-run-by-default, env passthrough). Likely needs an APIM-style
bridge follow-up; budget for that.

### B.2 — planner prompt awareness of worker quirks

The §15.1 first run rejected on aider's `.gitignore` auto-edit.
PR #24 silenced that at the worker level. A safer long-term fix is
to teach the planner to avoid criteria the worker can't satisfy.
This touches the planner prompt, which is spec §9 sensitive — needs
human review.

### B.3 — real-LLM cost dashboard

**Status: contract authored 2026-05-17 (queue item #6 of the
v0.3 Cursor hardening + v0.4 startup window). Full design lives
in `docs/B_3_CONTRACT.md`.** The locked CLI surface and stance
(Q1–Q6, resolved with the user 2026-05-17 03:57 UTC):

- **CLI:** `ai-cockpit cost [--root PATH] [--checkpoint-db PATH]
  [--since DATE] [--format text|json]`. Read-only aggregator
  over the existing LangGraph SqliteSaver checkpoint DB at
  `.ai-cockpit/history/checkpoints.sqlite`. Reports per-thread
  rows + grand total. Covers A.3 aider keys (`tokens_sent`,
  `tokens_received`, `cost_message_usd`, `cost_session_usd`)
  and B.10pty cursor keys (`input_tokens`, `output_tokens`,
  `cache_read_tokens`, `cache_write_tokens`).
- **Persistence change:** add one optional field
  `metrics: dict[str, float]` to `TaskState` (`total=False`);
  `make_coder_node` propagates `WorkerResult.metrics`. No DB
  schema migration.
- **No cost cap enforcement** (B.6 §3 Q6 precedent + B.5 Q5
  exclusion). The B.5 Q4 (1) ≤ $1 check is operator-evaluated
  against the printed total.
- **Out of scope this gate:** cursor planner / reviewer
  `last_usage` propagation (OQ-20, v0.5 candidate).

Cron is pre-authorized for both queue #6 (contract, this PR)
and queue #7 (implementation, ≤5 files / ≤350 net LOC on
branch `cursor/v0_4-b3-impl`). One gate per tick; see
`docs/B_3_CONTRACT.md` §11 + §15.

### B.4 — `--system-prompt FILE` override

Lets project-specific planner/reviewer prompts be loaded without
modifying source. Spec §9 risk — bad prompt could undo the
anti-deception evidence shape. Needs an explicit allow-list of
prompt placeholders (e.g., must include `{evidence}` for the
reviewer).

### B.5 — v0.4 exit-gate definition

**Status: contract authored 2026-05-17 (queue item #5 of the v0.3
Cursor hardening + v0.4 startup window). Full design lives in
`docs/B_5_CONTRACT.md`.** The locked gate definition (Q1–Q5,
resolved with the user 2026-05-17 03:57 UTC):

- **Capability proof:** `ai-cockpit` runs a complete `plan → plans
  run → verifier → reviewer → memory` loop on a real git repo
  (default `examples/broken_calc`) under real LLM credentials, with
  ≥1 real-LLM-driven commit on master and ≥1 `done` suggestion
  applied via `accept_suggestion`.
- **Hard metrics (AND):** (1) total cost ≤ $1 USD; (2) total
  wall-time ≤ 15 min; (3) human interventions = 0; (4) full test
  suite green = existing master tests + ≥10 new v0.4 tests + the
  5-test §9 anti-deception suite.
- **Cursor backend:** optional bonus, not gate-blocking.
- **Excluded:** cost auto-optimization, prompt auto-tuning,
  daemon / UI / web app, multi-repo parallel run, A2A swarm,
  automatic outbound email / Slack / PR comments, browser
  automation, real-LLM-budget auto-expansion.

Cron is authorized to land contract preparation gates (B.3, B.2,
B.4 contracts, B.1 supersede) but the v0.4 exit-gate run itself
is operator-driven and produces a separate `docs/V0_4_EXIT_EVIDENCE.md`
PR. See `docs/B_5_CONTRACT.md` §11 (authorization) and §15
(open-gate protocol) for the binding rules.

### B.6 — multi-step planner & plan artifact

**Status: delivered 2026-05-16 (B.6a + B.6b + B.6c merged to master).**
Full design lives in `docs/B_6_CONTRACT.md` (audit-trail-grade,
~340 lines). The summary:

2026-05-16 addendum: B.9's interactive planner contract supersedes the
original one-shot `ai-cockpit plan` generation path in B.6 §5.1. B.6
still owns the plan artifact schema, `plans run`, `plans list/show`,
and dependency-marker execution semantics.

Today the planner produces one `implementation_slice` and `ai-cockpit
run` consumes exactly one idea. Complex tasks have to be hand-
decomposed by the operator before they can enter the pipeline. B.6
internalizes the decomposition step **without introducing a second
writer agent**, using the Magentic-One Task Ledger / Plan-then-Execute
shape that the 2025–2026 multi-agent literature has converged on as
the only multi-step pattern that survives production.

The contract is locked along these axes (Q1–Q6, resolved with the user
on 2026-05-16):

| # | Decision |
| --- | --- |
| Q1 | Plan file format: `.plan.yaml` (Pydantic-validated, markdown-content fields allowed via YAML `\|` multi-line blocks). |
| Q2 | CLI shape: new `ai-cockpit plans run <plan_id> <slice_id>` under the `plans` group; `run` is **not** extended. |
| Q3 | No hard schema cap on `len(slices)` — operator concern, not safety. |
| Q4 | `--max-slices` flag retained on `ai-cockpit plan`; **default = unbounded.** |
| Q5 | Cron authorization for executing slices: **two keys** — plan YAML merged to `master` AND `V0_3_STATUS.md` explicitly names `active_plan_id: <id>`. Both required; absence of either ⇒ idle-healthy. |
| Q6 | Dropped — no per-call cost cap (inconsistent with v0.2/v0.3 elsewhere). |

Implementation splits into three serial PRs (B.6a / B.6b / B.6c) under
the same ≤8 files / ≤400 net LOC cap as every other step. See
`docs/B_6_CONTRACT.md` §6 for the file budget and §7 for the threat
model.

**Permission rule (binding on cron):** cron is NOT authorized to start
B.6a until the user explicitly says "open-gate B.6a" (or equivalent).
Even the contract-PR itself was opened only because the user pre-
authorized writing the contract during the 2026-05-16 design
conversation. Section B as a whole still requires fresh user direction
per `V0_3_STATUS.md`.

**Delivery note (2026-05-16):** all three B.6 PRs landed this day
under the user-authorized Section-B cron window. B.6a (PR #49,
`b8b790c`) shipped the schema + atomic loader; B.6b (PR #50,
`da7ea1f`) shipped `plans run` + git-log dep check + anti-deception
test #5; B.6c shipped `plans list` / `plans show` + this status
update + the spec §9 addendum that pins "plans are scheduling
artifacts, not reviewer-prompt evidence" byte-for-byte. Q5's
two-key authorization for executing a real `plans run` tick
remains binding and is still satisfied only when the user (or
cron-self) names `active_plan_id` in `V0_3_STATUS.md`.

### (B.7 and B.8 promoted to Section A — see A.7 / A.8 above.)

### B.9 — interactive planner mode

**Status: B.9a open-gated by the user on 2026-05-16 and implemented on
branch `cursor/b9-interactive-planner-contract-1a13`; B.9b/B.9c/B.9d
remain gated.** Full design lives in
`docs/B_9_INTERACTIVE_PLANNER_CONTRACT.md`.

B.9 adds an interactive `ai-cockpit plan "<idea>"` planning surface:
the user and a planner loop discuss, inspect repository context through
read-only tools, revise draft slices, and write a B.6-compatible
`docs/plans/<plan_id>.plan.yaml` only after the user explicitly runs
`/save`.

This is the contract-level correction from the Cursor Plan Mode
discussion: planning is human-in-the-loop and iterative; execution is
the later non-interactive `plans run` path. Cursor / Claude Code may be
optional planner backends later, but the builtin backend is required and
default so `ai-cockpit` does not depend on a closed-source CLI.

Key locked decisions:

| # | Decision |
| --- | --- |
| Q1 | `ai-cockpit plan` is an interactive foreground CLI REPL, not a daemon, UI, or non-interactive autonomous planner. |
| Q2 | `stdin.isatty()` is required for real planning; non-TTY mode is only allowed for deterministic `--llm none` tests. |
| Q3 | Builtin backend ships first and uses the existing `LLMProvider` plus read-only tools (`read_file`, `glob`, `ripgrep`, `git_status`, `git_log`, `read_existing_plans`). |
| Q4 | Cursor backend is optional/deferred; the user's three CLI experiments showed `agent --print` returns first-turn progress, not reliable completed plan artifacts. |
| Q5 | `/save` is the only write path and writes only `docs/plans/*.plan.yaml`; no source edits, no memory writes, no coder invocation. |
| Q6 | New §9 regression: planner conversation and planner tool output must be byte-for-byte absent from reviewer prompt evidence. |

Implementation splits into B.9a / B.9b / B.9c, with optional B.9d for
Cursor backend. Same ≤8 files / ≤400 net LOC cap applies. B.9a is now
authorized; later source work is NOT authorized until the user
explicitly says "open-gate B.9b" / "open-gate B.9c" (or equivalent).

2026-05-16 addendum: the optional Cursor planner backend should be
implemented through B.10's broader Cursor-backed role backend contract,
not as an isolated B.9-only adapter.

**B.9d — SUPERSEDED-FINAL by B.10b (2026-05-17).** The Cursor-backed
interactive planner is now delivered by `CursorPlannerBackend` from
B.10b (PR #53, `62976f9`); a separate B.9-only adapter would only
duplicate that path. B.9d will not ship as a standalone gate. The
B.9 contract §9 / §12 entries carry the same final-supersede marker.

### B.10 — Cursor-backed role backends

**Status: contract authored 2026-05-16, awaiting user open-gate signal.**
Full design lives in `docs/B_10_CURSOR_ROLE_BACKENDS_CONTRACT.md`.

B.10 captures the user's preferred direction: use Cursor as the high-
capability agent engine for roles, while `ai-cockpit` remains the
manager / policy / memory / verifier / evidence-boundary layer.

Target shape:

```text
ai-cockpit Manager / Controller
  -> Cursor-backed Planner Agent
  -> Cursor-backed Worker Agent
  -> deterministic Verifier
  -> Cursor-backed Reviewer Agent
  -> ai-cockpit Decision / Memory / Summary
```

Key locked decisions:

| # | Decision |
| --- | --- |
| Q1 | Cursor is a role backend, not the `ai-cockpit` manager. The Python/LangGraph controller still owns sequencing and policy. |
| Q2 | Planner, Worker, Reviewer, and optional Writer may be Cursor-backed. Verifier must remain deterministic shell/git/test evidence collection. |
| Q3 | Cursor roles are invoked serially by `ai-cockpit`; no agent-to-agent swarm, A2A server, or role-to-role chat. |
| Q4 | Cursor Reviewer receives only the existing §9 evidence bundle; Cursor Worker self-report and planner transcripts are forbidden as reviewer evidence. |
| Q5 | Cursor is optional. Builtin/stub/Aider paths remain valid fallbacks. |
| Q6 | Implementation starts with `ai-cockpit cursor status` discovery, because the installed Cursor CLI name/flags/trust behavior vary by environment. |

Implementation splits into B.10a adapter discovery, B.10b Cursor Planner
backend, B.10c Cursor Worker backend, B.10d Cursor Reviewer backend, and
optional B.10e Cursor Writer backend.

- **B.10a — delivered 2026-05-16.** `ai-cockpit cursor status` ships
  the read-only Cursor CLI discovery probe from contract §11/§9: it
  resolves a binary (default order `agent` → `cursor-agent` →
  `cursor`, overridable via `--binary`), parses `--version` (with
  `-v` fallback), and inspects `--help` for advertised `--mode`
  values plus tri-state flags for `--print --output-format=json`,
  `--yolo`/`--trust`, and `--resume`/`session`. All tests use fake
  binaries + an injected runner; the real Cursor CLI is never called.
- **B.10b — delivered 2026-05-16.** `ai-cockpit plan ... --backend
  cursor` plugs Cursor into the B.9 planner protocol via
  `CursorPlannerBackend`. The bridge is interactive-first: each
  user turn flows through an injectable `CursorPlannerSession`
  (default `_SubprocessSession` over `Popen --mode plan`); replies
  are parsed by `parse_json_response` and validated through the
  B.6 `PlanDraft` schema before becoming the active draft. Source
  writes from the planner are forbidden; saves still go through
  `/save` + `save_plan_atomic`. When no Cursor binary is on `PATH`
  the backend raises `CursorUnavailableError` suggesting
  `--backend builtin`. Tests inject a fake session — the real
  Cursor CLI is never spawned.
- **B.10c — delivered 2026-05-16.** `--worker cursor` ships `CursorWorker` (controlled task package, self-report semantics).
- **B.10d — delivered 2026-05-16.** `--reviewer cursor` ships `CursorReviewerBackend` on the §9 evidence-only prompt path.
- **B.10e — delivered 2026-05-17.** `CursorWriterBackend` ships a draft-only writer (PR description / run summary / status report); spec §12 outbound-comms boundary pinned by an AST import scan.

---

## Section C — permanent boundaries (never relax)

From spec §12 and `AUTOMATION_PROMPT.md` §3.1, none of the following
will ever ship — regardless of section A/B progress:

- UI, web app, daemon process, long-running background service.
- Cloud execution backend, multi-user / team permissions.
- ruflo, swarm behavior, plugin marketplace, generic agent platform.
- Automatic emails / Slack / PR comments outside the agent's own PR.

These are NOT future work; they are deliberately out of scope. Any
proposal touching them must be rejected by the cron with a STOP
question to the user.

---

## How cron should consume this file

1. On every tick, read `V0_3_STATUS.md` from memory first (it
   points at the next A-item to start).
2. If `V0_3_STATUS.md` says "start A.N", look up A.N's contract
   here, branch, implement strictly inside scope, pre-push, push,
   let auto-merge handle the rest.
3. If A.N has a "Blockers" line that is currently red (no such
   line as of writing), do not start it; skip to A.N+1 and update
   STATUS.
4. After a successful PR merge, update `V0_3_STATUS.md` to point
   to A.N+1 BEFORE the next tick.
5. If the entire Section A list is exhausted, the cron returns to
   `idle-healthy` and waits for the user to authorize Section B
   work explicitly. Do NOT pick a Section B item without the user
   answering in their next session.

Section C items are forbidden regardless of any other signal.
