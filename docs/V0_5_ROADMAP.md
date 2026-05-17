# V0.5 ROADMAP — agent-paradigm deficiencies (draft for user review)

Status: **draft for user review.** No source under `src/` or `tests/`
is touched by this PR; it ships only this document. Cron is NOT
authorized to start any v0.5 implementation work until the user
reviews this document, answers the open questions per row, and opens
each gate individually (same protocol B.3 / B.5 contracts followed).

> Sequencing rule (inherited from v0.3 / v0.4): one v0.4 evidence
> document on master first, then this roadmap is the source of
> truth for v0.5. Until `docs/V0_4_EXIT_EVIDENCE.md` is filled in
> by the operator and merged, no v0.5 gate moves past `CONTRACT`.

## 1. Why this document exists

The 2026-05-17 v0.4 exit-gate runs (attempts 1–7) exposed a class of
failures that are **not** "one more bug to fix" — they are
architectural gaps inherited from the v0.1 → v0.4 single-shot
plan-and-execute shape. Bug F (verifier cwd path-doubling) is the
most visible symptom; the structural root is "the planner emits a
plan, and from then on nothing can correct it without operator
intervention".

The 2026-05-17 architecture review identified **9 deficiencies**
spanning the feedback-loop topology, the reviewer→planner channel,
the CI-vs-real-LLM gap, the worker dispatcher, and the memory model.
This document organises all 9 into v0.5 / v0.6 / not-doing buckets,
flags strategic open questions that require user decisions, and
specifies the dependency order. Each row maps 1:1 to a future
`docs/V0_5_<gate>_CONTRACT.md` file once the user opens its gate.

## 2. Hard invariants (cannot be overridden by any v0.5 gate)

These override every row below. If implementing any row requires
violating one, the gate stays CLOSED and a separate spec amendment
is required.

| Invariant | Source | How v0.5 honours it |
| --- | --- | --- |
| §9 evidence-only reviewer | spec §9 | Reviewer LLM never receives `coder_result` narrative. Any v0.5 row that widens the reviewer→graph feedback channel must filter through a `objective_findings` schema whose contents are mechanically derivable from `verification_result` only. The 5-test §9 anti-deception suite stays byte-identical and must remain 100% green on every v0.5 gate. |
| §12 permanent boundaries | spec §12 | No daemon, no UI, no cloud backend, no swarm / A2A, no plugin marketplace, no multi-user, no auto-outbound email / Slack / PR comments. Row #4 (worker router) is deterministic, NOT an LLM-driven manager; row #9 (multi-topology) is workflow-yaml-driven, NOT runtime-decided. |
| §3.2 memory write approval | hard rule §3.2 | Cron never writes to `.ai-cockpit/memory/*`. Row #7 (memory auto-learn) is currently a **spec-amendment proposal**; until the user explicitly amends §3.2, row #7 stays at CONTRACT-DRAFT only and no implementation gate opens. |
| ≤8 files / ≤400 net LOC per PR | EXECUTION_RULES | Each v0.5 row that exceeds this caps splits into A/B/C sub-gates, same pattern as B.10a/b/c/d. |
| Mock-only CI | AUTOMATION_PROMPT §3.5 | Row #3 expands prompt-shape coverage but stays mock-only. The "nightly real-LLM probe" sub-option (3-A) is opt-in by the operator and runs outside CI. |
| Cron must not invent off-roadmap work | AUTOMATION_PROMPT §3.1 | Items not in this roadmap (and not in a follow-up amendment) are off-limits even if they look small. STOP + OQ instead. |

## 3. The 9 deficiencies — bucketed

### Bucket A: v0.5 candidates (high ROI, user-decision pending)

| # | gate slug             | summary                                                                 | files est | LOC est | depends on |
| - | --------------------- | ----------------------------------------------------------------------- | --------- | ------- | ---------- |
| 1 | `planner-replan`      | graph edge `decision → planner` for `replan_then_retry`                 | ≤6        | ≤300    | none       |
| 2 | `reviewer-findings`   | reviewer emits `objective_findings`, next coder turn reads it           | ≤7        | ≤350    | #1 (recommended)        |
| 3 | `prompt-coverage`     | golden-prompt CI + optional nightly real-LLM probe                      | ≤6        | ≤300    | none       |
| 5 | `planner-self-check`  | deterministic static lint on planner output before coder runs — **CONTRACT LOCKED** at `docs/V0_5_ROW_5_PLANNER_SELF_CHECK_CONTRACT.md` | ≤4        | ≤200    | none       |
| 6 | `plan-cwd-context`    | `Plan.assumed_cwd` field + mismatch warning at `plans run`              | ≤4        | ≤120    | none       |

### Bucket B: v0.6 candidates (defer, need v0.5 evidence first)

| # | gate slug             | summary                                                                 | files est | LOC est | why deferred |
| - | --------------------- | ----------------------------------------------------------------------- | --------- | ------- | ------------ |
| 4 | `worker-router`       | deterministic `WorkerRouter`; CLI `--worker` becomes hint, not override | ≤5        | ≤250    | needs v0.5 cost data to define routing thresholds |
| 9 | `workflow-topology`   | workflow YAML can pick graph topology (bug-fix vs new-feature vs refactor)  | ≤8        | ≤400    | depends on row #1 + #2 stabilising the per-topology contracts |

### Bucket C: requires spec amendment (do NOT start without explicit user signal)

| # | gate slug             | summary                                                                 | blocker |
| - | --------------------- | ----------------------------------------------------------------------- | ------- |
| 7 | `memory-auto-promote` | `done`-state low-risk suggestions auto-promote to memory                | requires explicit user amendment of spec §3.2 hard rule |

### Bucket D: explicitly NOT doing

| # | gate slug             | summary                                                                 | reason |
| - | --------------------- | ----------------------------------------------------------------------- | ------ |
| 8 | `worker-observability` | structured tap into aider/cursor internal ReAct traces                  | trade-off: less coupling vs less observability. Cron's prior architecture review recommended **keeping the opaque boundary** because (a) it would either duplicate aider/cursor's internals or create a parser-dependency on their stdout formats, (b) reviewer evidence already captures the post-hoc facts (git_diff + verification_result), and (c) it adds a §9 leak surface. If the operator wants more observability, the answer is `--verbose` on aider/cursor themselves, not an in-graph layer. |

## 4. Row-by-row — what, why, and what you need to decide

Each row below has the same structure: **what** (one paragraph),
**why** (tied to v0.4 evidence or a foreseeable failure mode),
**open questions** (numbered, each requires your decision before
the contract is written), and **provisional scope** (file/LOC
estimates; refined in the contract).

---

### Row #1 — `planner-replan` (Bucket A)

**What.** Add a graph edge from `decision` back to `planner` for
`replan_then_retry`. When `verification_result.passed == False` AND
`replan_count < replan_max`, the graph routes to `planner` (not
`coder`); planner receives the previous slice + verification result
and emits a corrected plan. `coder` retry remains available for
cases where the slice is correct but the worker fluked.

**Why.** The 2026-05-17 v0.4 attempt 7 was the canonical example:
the planner emitted `pytest -v examples/broken_calc` (wrong cwd
assumption), and the only feedback path was `coder retry` — which
ran the same wrong plan again. Operator had to stop, edit the
plan yaml by hand, and re-run. With `planner-replan` in place, the
graph would self-correct on the second loop without operator
intervention. Bug F is the canonical failure mode.

**Open questions (need user decision before contract is written):**

| Q  | question                                            | cron recommendation                      | your answer |
| -- | --------------------------------------------------- | ---------------------------------------- | ----------- |
| Q1 | `replan_max` default                                | `1` (cost-conservative under B.5 Q4 \$1) |             |
| Q2 | replan tokens count against B.5 \$1 cap?            | yes, same bucket                         |             |
| Q3 | what does replan see?                               | prev slice + verification_result; NOT `coder_result` |   |
| Q4 | replan output scope                                 | slice + test_commands only; criteria locked |          |
| Q5 | exhaustion path when `replan_count == replan_max`   | `ask_human` (matches existing retry exhaustion)  |   |

**Scope:** see Bucket A table.

---

### Row #2 — `reviewer-findings` (Bucket A, depends on #1)

**What.** Extend the reviewer schema with `objective_findings:
list[str]` — short factual statements mechanically derivable from
`verification_result` (e.g. `"command 'pytest -v examples/broken_calc'
exited 4; stderr contains 'no such file or directory'"`). The next
coder turn (or replan, if #1 is in) reads `objective_findings` as
context. **Reviewer narrative (`notes`, `suggested_fix`) does NOT
flow into any prompt — only `objective_findings` does.** A new
schema-level validator asserts `objective_findings` contents are
substrings of `verification_result` text (no §9 leak path).

**Why.** Today the reviewer's high-quality diagnostic
(`"git_status shows calc.py modified at repo root, not under
examples/broken_calc — file appears to be in the wrong location"`)
is consumed only by the **operator reading the summary**. The
graph itself is blind to it. retry / replan run with no idea what
the last attempt got wrong.

**Open questions:**

| Q  | question                                          | cron recommendation                                | your answer |
| -- | ------------------------------------------------- | -------------------------------------------------- | ----------- |
| Q1 | schema shape                                      | `list[str]` for v0.5, evolve later                 |             |
| Q2 | §9 strictness: strict (literal substring of `verification_result`) vs permissive (no `coder_result` substring) | strict for v0.5; permissive deferred to v0.6 if too rigid |  |
| Q3 | who consumes findings: replan only, or also next coder retry? | both, gated by `replan_count > 0`        |             |
| Q4 | next coder still hidden from prior `coder_result`? | yes — §9 boundary stays symmetric                  |             |

**Scope:** see Bucket A table.

---

### Row #3 — `prompt-coverage` (Bucket A)

**What.** Two complementary mitigations for the mock-only CI gap:

- **Sub-option B (recommended baseline):** golden-prompt CI. Every
  time the prompt builder, B.2 catalog, or B.4 override loader
  changes, CI dumps the rendered prompt for ~5 canned scenarios
  (one per worker × one per task type) into
  `tests/prompts/golden/*.txt`. PR validation fails if the diff
  isn't human-reviewed and committed. This catches Bug F-class
  "PR #80 → #81 calibration drift" before merge.
- **Sub-option A (opt-in operator-driven):** a nightly cron on the
  operator's machine (NOT the cloud cron VM) runs
  `scripts/v0_5_real_llm_probe.sh` against a ≤\$0.50 budget on the
  same 5 scenarios. Asserts structural properties of the LLM reply
  (e.g. "no test_command starts with `<project_root.name>/`").
  Operator pastes a per-run row into `docs/V0_5_PROBE_LOG.md`.

**Why.** 4 of 6 PRs in the Bug F chase (#80/#81/#82/#83) shared
one root cause: the prompt-builder chain has 5 layers and only
end-to-end LLM runs exercise it. Mock tests passed every time.

**Open questions:**

| Q  | question                                          | cron recommendation                                | your answer |
| -- | ------------------------------------------------- | -------------------------------------------------- | ----------- |
| Q1 | A (real-LLM probe), B (golden CI), or both?       | B unconditionally; A opt-in for operators          |             |
| Q2 | if A: budget?                                     | \$0.50/night, \$5/week cap, skip if today's spend ≥ \$0.40 |     |
| Q3 | if B: PR review must visually approve golden diffs? | yes — that friction is the whole point             |           |
| Q4 | canned scenario count + mix                       | 5: bug-fix×aider, new-feature×aider, refactor×aider, bug-fix×cursor, refactor×cursor |  |

**Scope:** see Bucket A table.

---

### Row #5 — `planner-self-check` (Bucket A)

**What.** A new `planner_self_check` graph node between `planner`
and `coder`. Runs **deterministic Python lints** on the planner
output (no second LLM call):

- Each `test_command` parsed via `shlex`; warn if any token starts
  with `project_root.name + '/'` (the Bug F pattern).
- Warn if any `dod` bullet contains "no other files modified" or
  "exact N-file diff" when the worker is `aider` (B.2 quirk
  matches at runtime instead of just in the prompt).
- Warn if `files_budget` × `loc_budget` exceeds the operator's
  active workflow defaults.

By default lints are **warnings**, not errors (graph proceeds).
Operator can pass `--strict-planner` to convert to errors.

**Why.** Cheap belt-and-suspenders for Bug F-class issues. Layer
3 of PR #83 already does cwd-doubling detection at the verifier
side; this catches the same pattern at the planner side, **before**
the slice burns coder tokens.

**Open questions:**

| Q  | question                                          | cron recommendation                                | your answer |
| -- | ------------------------------------------------- | -------------------------------------------------- | ----------- |
| Q1 | initial lint set                                  | 3 above; open to additions                         |             |
| Q2 | warn or error by default?                         | warn; `--strict-planner` flag to escalate          |             |
| Q3 | where do warnings surface?                        | stderr + replan context (if #1 ships)              |             |

**Scope:** see Bucket A table.

---

### Row #6 — `plan-cwd-context` (Bucket A, smallest)

**What.** `Plan` schema gains optional `assumed_cwd: str | None`
(absolute path string). `ai-cockpit plan` writes
`str(project_root.resolve())` into the plan when saving. `ai-cockpit
plans run` resolves `--root`, compares to `Plan.assumed_cwd`, and
emits a `click.echo(warning)` (not error) if they differ.

**Why.** Replaying a plan with `--root different_path` silently
breaks when the planner's emitted commands assumed the original
cwd. Bug F's plan would have been re-runnable safely if this had
been recorded. Very small, very contained, useful immediately.

**Open questions:**

| Q  | question                                          | cron recommendation                                | your answer |
| -- | ------------------------------------------------- | -------------------------------------------------- | ----------- |
| Q1 | warn or block on mismatch?                        | warn only (don't break existing workflows)         |             |
| Q2 | pre-v0.5 plans without the field                  | silently skip check                                |             |

**Scope:** see Bucket A table.

---

### Row #4 — `worker-router` (Bucket B, defer to v0.6)

**What.** Deterministic `WorkerRouter` class: `select(slice: Slice,
workflow: Workflow) -> WorkerName`. Rules live in the workflow
yaml (`router: {rules: [{when: {files_budget: '<=2'}, use: aider}, ...]}`).
CLI `--worker` becomes a hint that the router may override (with
warning); `--worker-force <name>` disables routing.

**Why.** v0.4 evidence will show whether aider's per-run cost is
predictable enough to write routing rules. Without that data, any
rule we write now is a guess.

**Open questions (deferred — answer after v0.4 evidence):**

1. **Routing dimensions.** Files? LOC? `dod` keyword matching?
2. **Fallback.** Router picks aider, aider fails — auto-try cursor?
3. **Cost-vs-capability matrix.** Need v0.4 + v0.5 evidence.

Cron will not draft this contract until v0.4 evidence is on master
and the v0.5 Bucket A is at ≥80% DONE.

---

### Row #9 — `workflow-topology` (Bucket B, defer)

**What.** Workflow yaml gains a `topology` field; supported values
in v0.6: `bug-fix` (current intake→planner→coder→verifier→reviewer→
decision), `new-feature` (adds an extra `design-review` node between
planner and coder), `refactor` (adds a `pre-test-snapshot` node before
coder to record baseline behaviour). Default = `bug-fix` (current).

**Why deferred.** Each new topology needs a contract of its own.
Premature topology splitting is worse than no splitting. v0.5
should ship rows #1+#2+#5 first so the per-topology contracts can
share the replan / findings / self-check primitives.

**Open questions (deferred):**

1. **Topology taxonomy.** What are the actual task types worth
   distinguishing? `bug-fix` vs `new-feature` vs `refactor` is
   one cut; `tests-first` vs `impl-first` is another.
2. **Topology inference.** Operator declares via workflow yaml,
   or planner infers from idea string?

Cron will not draft this contract in v0.5.

---

### Row #7 — `memory-auto-promote` (Bucket C, blocked by spec §3.2)

**What.** `done`-state low-risk suggestions auto-promote into
`.ai-cockpit/memory/*` without operator `accept_suggestion`.
Currently §3.2 forbids this.

**Why blocked.** §3.2 hard rule: *"Never edit
`.ai-cockpit/memory/*` automatically; the system may suggest
diffs but a human must accept."* This row inverts the second
clause — requires user-signed amendment in
`docs/AI_COCKPIT_SPEC_V1.md` BEFORE cron writes any contract.

**Gate-opening protocol (only):** (1) you amend §3.2 in a PR you
sign; (2) amendment specifies the "low-risk" predicate (cron
suggests: descriptive-fact only, no prompt-modifying language,
≤200 chars, no `coder_result` substring); (3) THEN cron is
authorised to draft the row #7 contract.

**Q → are you willing to amend §3.2 in v0.5?** Cron
recommendation: not in v0.5; revisit after rows #1+#2 expose
where memory learning would actually help.

---

### Row #8 — `worker-observability` (Bucket D, NOT doing)

A tap into aider/cursor internal traces surfaced into
`verification_result` / a new `worker_trace` state field. **NOT
doing**, three reasons: (a) duplicates aider/cursor's own
`--verbose`; (b) every new state field is a permanent §9 audit
surface; (c) no demonstrated need from v0.4 evidence ("I wish I
could see aider's intermediate thought" has not been a recurring
complaint). Workaround for today: pass `--verbose` through
`AiderWorker` extra-args or shell-redirect aider stdout.
Reopening requires a fresh user signal that names a specific
observation impossible to get any other way.

## 5. Sequencing

**Phase 0 (blocking):** `docs/V0_4_EXIT_EVIDENCE.md` filled in and
merged. Until then no v0.5 row moves past CONTRACT.

**Phase 1 — contracts** (one PR per row, ≤2 files / ≤350 LOC each):
in any order, but #2 depends on #1. Cron drafts each only after
the user opens that row's gate AND answers its §4 open questions.

**Phase 2 — implementations** (one PR per row). Suggested order
(maximises early Bug F-class prevention with smallest blast
radius first):

1. #6 plan-cwd-context (smallest, immediately useful, isolated)
2. #5 planner-self-check (cheap belt-and-suspenders for Bug F)
3. #1 planner-replan (biggest leverage)
4. #2 reviewer-findings (depends on #1 to be useful)
5. #3 prompt-coverage (process change, independent)

**Phase 3 — v0.5 exit gate.** Sketch (full contract is its own
gate, analogous to B.5): a real-LLM end-to-end run on
`examples/broken_calc` where the planner's first attempt has a
known cwd-doubling-style flaw, and the graph self-corrects (via
replan + findings + self-check) **without operator intervention**,
within the same B.5 Q4 caps (\$1, 15 min, 0 human interventions).

**Phase 4 — v0.6 candidates** (#4 router, #9 multi-topology):
contracts drafted only after v0.5 exit gate signed off.

## 6. Open-gate protocol

```text
open-gate v0.5-row-6-plan-cwd-context             # smallest; no
                                                  # open Q dependency
open-gate v0.5-row-5-planner-self-check           # answer §4 Q1–Q3
open-gate v0.5-row-3-prompt-coverage              # answer §4 Q1–Q4
open-gate v0.5-row-1-planner-replan               # answer §4 Q1–Q5
open-gate v0.5-row-2-reviewer-findings            # answer §4 Q1–Q4
                                                  # (after row 1)

open-gate v0.6-row-4-worker-router                # NOT until v0.4 +
                                                  # v0.5 evidence
open-gate v0.6-row-9-workflow-topology            # NOT until v0.5
                                                  # rows 1+2 stable

open-gate v0.5-row-7-memory-auto-promote          # NEVER without
                                                  # explicit user
                                                  # amendment of
                                                  # spec §3.2

open-gate v0.5-row-8-worker-observability         # NEVER GRANTED;
                                                  # spec §9 + §12
                                                  # rationale; see §4
                                                  # row 8 above.
```

Each future `open-gate v0.5-row-N-<slug>` signal must reference
the row number AND confirm the answers to that row's §4 open
questions (or accept cron's recommendations verbatim). Without
that, cron treats the signal as ambiguous and stops with an OQ
entry.

## 7. PR scope

This PR adds this document + one pointer in `docs/ROADMAP.md`. It
does NOT touch source / test, lock any open question, authorise
any v0.5 implementation gate, or amend any hard rule. Per-row
contracts are separate PRs (B.2 / B.3 / B.4 / B.5 pattern).
