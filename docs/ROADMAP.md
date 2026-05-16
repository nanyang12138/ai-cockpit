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

### B.3 — real LLM cost dashboard

Aggregate the per-run token/cost data from A.3 across the
checkpoint DB. Display via a `ai-cockpit cost` subcommand. Requires
deciding privacy + retention semantics first.

### B.4 — `--system-prompt FILE` override

Lets project-specific planner/reviewer prompts be loaded without
modifying source. Spec §9 risk — bad prompt could undo the
anti-deception evidence shape. Needs an explicit allow-list of
prompt placeholders (e.g., must include `{evidence}` for the
reviewer).

### B.5 — v0.4 exit-gate definition

v0.3 has no formal exit gate (v0.2's was spec §15). Candidate for
v0.4: "ai-cockpit can iterate a failing test to green AND keep
project memory consistent across runs". This must be defined by the
user, not cron, because it sets the bar for declaring v0.4 done.

### B.6 — multi-step planner & plan artifact

**Status: contract authored 2026-05-16, awaiting user open-gate signal.**
Full design lives in `docs/B_6_CONTRACT.md` (audit-trail-grade,
~340 lines). The summary:

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

### (B.7 and B.8 promoted to Section A — see A.7 / A.8 above.)

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
