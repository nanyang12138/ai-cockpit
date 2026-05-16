# B.6 — Multi-step Planner & Plan Artifact (contract v0.1)

Status: **contract authored, awaiting user open-gate signal.** Cron is
explicitly NOT authorized to begin implementation. This document
captures the full design that was reviewed and locked in conversation
with the user on 2026-05-16 ~10:22 UTC, so a future implementer (cron
or human) has an unambiguous specification to work from.

> This contract supersedes the one-paragraph placeholder in
> `docs/ROADMAP.md` Section B.6. Once the user explicitly says
> "open-gate B.6a", this file becomes the source of truth for the
> three implementation PRs (B.6a / B.6b / B.6c). Until then, no
> source code under `src/` may be modified in service of B.6.

2026-05-16 addendum: `docs/B_9_INTERACTIVE_PLANNER_CONTRACT.md`
supersedes this document's original one-shot `ai-cockpit plan`
generation design in §5.1. B.6 remains the source of truth for the
plan artifact schema, `plans run`, `plans list`, `plans show`, and
dependency markers. If B.9 is open-gated first, B.6 implementation
must reuse B.9's interactive `plan` surface instead of adding a second
non-interactive planner command.

## 1. Why

Today `ai-cockpit run` consumes exactly one user idea per invocation
and the planner emits exactly one `implementation_slice`. This makes
the tool unable to take a single complex goal as input — the human (or
an external chat) must hand-decompose into slices and feed them one at
a time. The cron's progress through `docs/ROADMAP.md` Section A is the
canonical example of this manual decomposition.

B.6 internalizes the decomposition step **without introducing a second
writer agent**. The architectural reference is Microsoft Magentic-One's
Task Ledger (2024) and the academic Plan-then-Execute pattern. Writes
stay single-threaded; the 2025–2026 empirical consensus (Cognition's
"Don't Build Multi-Agents", Anthropic's research-system retrospective,
NeurIPS 2025 MAST taxonomy) says this is the only multi-step shape
that survives production.

## 2. Hard invariants (cannot be overridden by anything else)

These are non-negotiable. They override §5's CLI shape, §6's PR split,
and any future "small extra improvement" temptation during implementation.

| Invariant | Source | How B.6 honors it |
| --- | --- | --- |
| Single-threaded writer | spec §12 + 2026 consensus | One `plans run` invocation executes exactly one slice. Cron may run consecutive slices on consecutive ticks; never parallel. |
| §9 evidence-only reviewer | spec §9 | Reviewer prompt receives only `mvp_spec`, `acceptance_criteria`, `git_diff`, `git_status`, `verification_result`. The plan YAML's content **never** enters the reviewer prompt as positive evidence. A new anti-deception regression test (`test #5`) will pin this byte-for-byte. |
| Memory not auto-written | hard rule §3.2 | Plans live under `docs/plans/<plan_id>.plan.yaml`. `.ai-cockpit/memory/*` is untouched; `memory accept` remains the only writer. |
| ≤8 files / ≤400 LOC per PR | EXECUTION_RULES | Plan schema enforces `files_budget ≤ 8` and `loc_budget ≤ 400` per slice at validation time, before any coder runs. |
| No daemon / UI / cloud / swarm / marketplace | spec §12 | `plan` and `plans run` are both fire-and-exit CLI commands. No background process. No agent-to-agent message bus. |
| No automatic emails / Slack / PR comments | spec §12 | Unchanged; B.6 emits only the standard `validate` workflow PR comment via the existing cursor-pr-automation pipeline. |

## 3. Resolved design decisions (Q1–Q6, 2026-05-16)

The six questions raised by the contract draft were resolved by the
user as follows. Each row records the final decision plus the rationale
that made it not arbitrary.

| # | Question | Decision | Rationale |
| --- | --- | --- | --- |
| Q1 | Plan file format | `.plan.yaml` with markdown-formatted multi-line content blocks (`|`) for free-text fields | YAML gives strict Pydantic validation, lossless round-trip, and matches the existing `.ai-cockpit/workflows/*.yaml` convention. Multi-line `|` blocks keep human readability for `why` / `scope_*` / `dod` fields. |
| Q2 | CLI shape | `ai-cockpit plans run <plan_id> <slice_id>` (subcommand under the `plans` group) | Cleaner than overloading `run --from-plan`: avoids growing `run`'s mutually-exclusive flag matrix, eliminates the "did I mean an ad-hoc run or a planned slice?" ambiguity, and mirrors the existing `memory list/show/accept` group pattern. |
| Q3 | Hard cap on `len(slices)` | **None** — schema does not cap slice count | Operational concerns (reviewability, replan cost, planner output quality) are real but not safety-critical. They are addressed by Q4's `--max-slices` knob and a soft warning, not a hard schema rejection. |
| Q4 | `--max-slices` default | Flag retained, **default = None (unbounded)** | Consistent with Q3. The flag exists so the user can deliberately cap planner output when they want a tighter plan; absent the flag, the planner is free to choose, subject only to the per-slice budget invariants. |
| Q5 | Cron authorization model for B.6 | **Two-key:** plan YAML must be merged to `master` AND `V0_3_STATUS.md` must explicitly list `active_plan_id: <plan_id>`; both keys required for cron to advance one slice per tick | Plan-merge proves the plan content was code-reviewed. The status-file pointer proves the operator (user or cron-self) has explicitly chosen "yes, advance this plan now". Putting the second key in `V0_3_STATUS.md` (which is never LLM-written) ensures a jailbroken planner cannot self-authorize. |
| Q6 | Per-call cost cap on `plan` LLM invocation | **Dropped** — no cost cap | v0.2/v0.3 do not cap planner/reviewer cost elsewhere; adding it only for `plan` would be inconsistent. The LLM SDK's `max_tokens` parameter and Q4's `--max-slices` together provide enough structural bound. Cost telemetry is logged to stderr (info-level) but never enforced. |

## 4. Plan artifact schema (`docs/plans/<plan_id>.plan.yaml`)

```yaml
schema_version: 1
plan_id: <slug>                # ^[a-z0-9-]+$, ≤48 chars, filesystem-safe
created_at: <ISO8601 UTC>
idea: |
  <multi-line restatement of the user's complex goal; context only,
   never enters reviewer prompt as positive evidence>
acceptance_criteria:           # whole-task level, 1..10 entries
  - <bullet>
slices:                        # 1..n entries (no schema upper bound)
  - id: <slug>                 # ^[a-z0-9-]+$
    depends_on: []             # ids of earlier slices only
    title: <one-line>
    why: <2-5 lines>
    scope_must:                # ≥1 entry
      - <bullet>
    scope_out:                 # ≥1 entry — empty is REJECTED
      - <bullet>
    dod:                       # ≥1 entry
      - <bullet>
    files_budget: <int ≤ 8>
    loc_budget: <int ≤ 400>
    test_commands: [<shell>]   # may be empty for docs-only slices
```

### Validation rules (raise `PlanError` on any violation, no partial writes)

1. `schema_version == 1` (forward-compat hook).
2. `plan_id` regex `^[a-z0-9-]+$`, length 1–48, lowercase only.
3. `len(slices) >= 1` (a zero-slice plan is a bug; use `run` instead).
4. Every `slice.id` matches the same regex and is unique within the file.
5. Every `depends_on` entry references a `slice.id` that appears
   **earlier** in the `slices` list. Forward references → reject.
   Cycles are impossible by construction.
6. Every `scope_out` list is non-empty (MAST-2025 #1 drift cause).
7. Every `files_budget` is in `[1, 8]`; every `loc_budget` is in `[1, 400]`.
8. `created_at` parses as ISO-8601 with timezone information.

## 5. CLI surface (three commands; none touch source by themselves except `plans run`)

### 5.1 `ai-cockpit plan` — generate a plan; never execute

**Superseded by B.9 if B.9 is open-gated.** The original B.6 design
below described a one-shot non-interactive planner. The 2026-05-16
Cursor Plan Mode discussion changed the product decision: real
planning should be interactive and human-approved. Implementers should
read `docs/B_9_INTERACTIVE_PLANNER_CONTRACT.md` before touching this
command.

```
ai-cockpit plan "<complex goal>" \
  [--root .] \
  [--output docs/plans/<plan_id>.plan.yaml] \
  [--llm {none|auto|anthropic|openai}] \
  [--max-slices <int>]     # default: unbounded (see Q4)
```

Behavior:

- Exactly one LLM call, against the dedicated multi-step planner prompt
  (separate from the single-slice planner prompt; lives at
  `src/ai_cockpit/llm/prompts/multi_step_planner.py`). The prompt
  explicitly enumerates the spec §12 forbidden list, the per-slice
  budgets, and the `scope_out` non-empty requirement.
- LLM output is parsed as YAML and run through the Pydantic schema. On
  any validation failure, the command exits non-zero with the specific
  violation message and writes nothing to disk.
- `--llm none` emits a deterministic stub plan suitable for CI fixtures.
- Stderr emits a single `info: plan LLM call used X input / Y output tokens`
  line for observability; no enforcement.
- This command **never** spawns a coder, **never** touches
  `.ai-cockpit/memory/*`, **never** modifies source files.

### 5.2 `ai-cockpit plans run` — execute one slice of an existing plan

```
ai-cockpit plans run <plan_id> <slice_id> \
  [--root .] \
  [--worker {stub|aider}] \
  [--apply]                # required for aider to actually write files
  [--llm ...] [--test-command ...] [--max-loops ...] \
  [--no-checkpoint | --thread-id ... | --checkpoint-db ...]
```

Behavior:

1. Resolve `docs/plans/<plan_id>.plan.yaml` under `--root`. Reject
   if missing or schema-invalid (revalidated on every load — a hand
   edit that introduces a violation refuses to run, never silently
   accepted).
2. Look up `<slice_id>` in `slices`. Reject if absent.
3. **Dependency check (the safety property):** for each `dep_id` in
   `slice.depends_on`, scan `git log` for a commit whose message
   contains the marker `[<plan_id>/<dep_id>]`. Every dep must be
   found, or the command refuses with a precise error naming the
   missing dep(s). Git log is ground truth — no internal state cache.
4. Inline the slice's `title / why / scope_must / scope_out / dod /
   test_commands` into the existing `TaskState` as if a human typed
   the idea. The plan's whole-task `idea` is attached as background
   context only — it does **not** become an acceptance criterion.
5. Run the standard graph exactly as today. §9 reviewer receives the
   same evidence shape as a normal run; the plan itself is not in
   the prompt.
6. On a successful aider apply, the eventual commit message must
   include the trailing marker `[<plan_id>/<slice_id>] from
   docs/plans/<plan_id>.plan.yaml`. This is what subsequent
   `depends_on` checks key on.

### 5.3 `ai-cockpit plans list` and `ai-cockpit plans show` — read-only

```
ai-cockpit plans list  [--root .]
ai-cockpit plans show <plan_id> [--root .]
```

- `list`: walks `docs/plans/*.plan.yaml`, for each plan computes
  `(total_slices, done_slices, next_slice)` where `done_slices` is
  derived by scanning `git log` for `[<plan_id>/*]` markers. Output:
  `plan_id | created_at | total | done | next`. When `total > 20`,
  appends a `WARN: large plan, manual audit recommended` line (soft
  warning per Q3 rationale).
- `show <plan_id>`: prints the plan YAML plus per-slice `[✓|✗] <id>:
  <title>` derived from git log. No write paths.

## 6. PR split (three independently shippable PRs)

Each PR independently satisfies `pytest + ruff check . + mypy . +
ai-cockpit smoke`, and each respects the ≤8 files / ≤400 net LOC cap.

### B.6a — Plan schema + `plan` subcommand

Estimated 7 files / 350 net LOC.

- `src/ai_cockpit/plans/__init__.py` (new)
- `src/ai_cockpit/plans/schema.py` (new — Pydantic models + validators)
- `src/ai_cockpit/plans/loader.py` (new — `load_plan`, `save_plan`)
- `src/ai_cockpit/llm/prompts/multi_step_planner.py` (new — prompt template)
- `src/ai_cockpit/cli.py` (add `plan` subcommand)
- `tests/test_plan_schema.py` (new — every negative validation case)
- `tests/test_plan_cli.py` (new — `plan` subcommand with `--llm none`)

### B.6b — `plans run` execution + §9 anti-deception test #5

Estimated 5 files / 300 net LOC.

- `src/ai_cockpit/plans/dependencies.py` (new — `git log` scanner)
- `src/ai_cockpit/cli.py` (add `plans run` subcommand to the `plans` group)
- `src/ai_cockpit/graph.py` (thread slice metadata into `TaskState`;
  add a commit-message-marker helper used by aider worker)
- `tests/test_plan_run.py` (new — dependency-met / dependency-missing
  cases, single-slice execution against `--worker stub`)
- `tests/test_llm_planner_reviewer.py` (extend with anti-deception
  test #5: assert the plan YAML's content does not appear in the
  reviewer prompt's bytes)

### B.6c — `plans list/show` + ROADMAP migration + spec §9 addendum

Estimated 4 files / 200 net LOC.

- `src/ai_cockpit/cli.py` (add `plans list` and `plans show`)
- `tests/test_plans_cli.py` (new — list/show against fixture plans)
- `docs/ROADMAP.md` (move B.6 from "deferred" to "delivered" once
  B.6a + B.6b have merged; this file's `Status:` line at the top
  also updates)
- `docs/AI_COCKPIT_SPEC_V1.md` (append one paragraph to §9 making
  explicit that multi-step plans are scheduling artifacts, not
  reviewer-prompt inputs)

## 7. Threat model (the safety case)

| Threat | Mitigation |
| --- | --- |
| Planner produces a slice exceeding per-PR budget | Pydantic validator rejects at `plan` time; no coder ever spawned |
| Planner produces a slice violating §12 (e.g., "add a daemon") | (a) Multi-step planner prompt enumerates the §12 forbidden list explicitly; (b) even if the prompt is bypassed, the per-slice ≤8-files / ≤400-LOC cap plus the §9 reviewer at execution time form an additional gate |
| Cron runs slice N+1 before slice N has been merged | `plans run`'s dependency check reads `git log` — bypassable only by lying to git itself, not by any in-process state mutation |
| Reviewer is fooled by the plan's "trivial" framing | §9 invariant: a new anti-deception test pins that plan-YAML content is byte-for-byte absent from the reviewer prompt construction |
| Coder uses parent-plan context to drift beyond its slice | Coder receives only the per-slice `mvp_spec` and `implementation_slice` (same as today); the plan is not in coder prompt. Verifier + git_diff are the existing backstop. |
| Hand-edited plan YAML smuggles in oversize budgets | Re-validation occurs on every `plans run` load; trusting "the file passed validation when it was created" is not allowed |
| Cron auto-executes a freshly merged plan without operator intent | Q5 two-key rule: cron requires `V0_3_STATUS.md` to name `active_plan_id`; merging the plan alone is not authorization |
| Planner LLM jailbroken into self-authorizing | The second key (`V0_3_STATUS.md`) is never LLM-written; it lives in AutomationMemory and is updated only by the agent transcript, not by any prompt content |
| Need to abandon a plan partway through | Plans are YAML under `docs/plans/`; deletion has no DB / checkpoint / memory side-effects. The existing single-slice `run` path is unmodified and remains a complete fallback. |

## 8. DoD — what "B.6 done" means

1. Three PRs (B.6a + B.6b + B.6c) merged to `master`, each green on
   `pytest`, `ruff check .`, `mypy .`, and `ai-cockpit "smoke ..." --max-loops 1 --dry-run --llm none --no-checkpoint`.
2. One real-LLM end-to-end demo executed on this repo and archived to
   `docs/V0_3_MILESTONES.md`:
   - `ai-cockpit plan "<some real complex goal>" --llm auto` produces
     a valid multi-slice plan YAML on disk.
   - Slice 1 runs via `plans run`, opens a PR, merges.
   - Slice 2 runs via `plans run`, the dependency check passes against
     the now-extant `[<plan_id>/slice-1]` marker in git log.
   - Anti-deception test #5 is green.
3. spec §9 addendum committed; the anti-deception test count is **5**
   (was 4 throughout v0.3).
4. spec §12 / `docs/ROADMAP.md` Section C: unchanged, verbatim.

## 9. Out of scope for B.6 (do not let scope creep in)

- No automatic slice chaining inside a single `plans run`. One slice
  per invocation, ever. The user (or cron) controls cadence.
- No parallel slice execution. Even slices whose `depends_on` sets are
  disjoint may not run concurrently — single-process design + per-PR
  cap is the enforcement.
- No plan auto-rewrite. Once a plan YAML is checked in, the planner
  LLM never edits it. Replan = generate a new plan with a different
  `plan_id`. Old plans remain as historical record.
- No LLM-driven plan review. Validation is rule-based; humans (and
  PR review) are the plan reviewer.
- No multi-LLM role specialization. Same planner LLM produces the
  plan; same planner LLM produces per-slice specs (called once per
  slice); same reviewer LLM judges per slice. No agent-to-agent chat.
- No `.ai-cockpit/memory/*` write. Memory continues to flow through
  `memory accept` only (hard rule §3.2).
- No UI / no daemon / no cloud backend / no plugin marketplace / no
  multi-user permissions / no auto email-Slack-PR-comment. (spec §12,
  unchanged.)
- No retroactive plan editing after a slice merges. If slice 3 fails
  in a way that invalidates slice 4, the operator writes a new plan;
  the planner LLM never amends a checked-in plan.

## 10. Rollback plan

If B.6 lands and proves harmful (planner drift not catchable, slices
burn aider tokens without merging, dependency check edge cases, …):

1. Stop using `ai-cockpit plan` and `ai-cockpit plans run`. The
   existing single-slice `run` path is **untouched** and remains the
   default for ad-hoc execution.
2. Delete `docs/plans/*.plan.yaml`. No schema migrations needed; no
   database state to clean.
3. Optionally revert B.6c / B.6b / B.6a PRs (each is small, clean, and
   independently revertible). The `plans` CLI group can be removed by
   reverting B.6c + B.6b; the schema module can be removed by also
   reverting B.6a.
4. The cron's existing Section A workflow remains fully functional and
   unmodified throughout B.6's life cycle — there is no point at which
   "the project depends on B.6 working".

## 11. Authorization & operating rhythm

Per the user-confirmed rhythm of 2026-05-16:

1. **Contract first.** This document and the matching summary in
   `docs/ROADMAP.md` Section B.6 are the only B.6 deliverables of
   the current cron tick.
2. **User open-gate signal.** After reading this contract, the user
   must explicitly say "open-gate B.6a" (or equivalent) before any
   `src/` change for B.6 is allowed. Cron is forbidden from
   self-promoting B.6 into its working queue.
3. **Implementation in three serial PRs.** Once gated, B.6a then B.6b
   then B.6c, one per cron tick (or one per user session). Each
   merges before the next begins.
4. **Plan execution gating after implementation.** Even with B.6
   shipped, cron requires the two-key authorization from §3 Q5
   before advancing any actual `plans run` ticks.

Until step 2 happens, this file is reference material only. The
project's source tree is untouched by B.6.
