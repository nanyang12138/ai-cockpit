# V0.5 Row #1 — `planner-replan` contract (v0.1, LOCKED)

Status: **contract locked.** User authorised the Q-answers on
2026-05-17 15:08 UTC ("采纳所有 cron 推荐, #1 Q1 选 2, #1 Q5 选
ask_human"). Implementation gate double-blocked on V0_4 evidence
+ explicit `open-gate v0.5-row-1-impl` signal.

> Pure-documentation deliverable: 2 files / ≤350 net LOC. No code
> under `src/`, no tests touched.

## 1. Why

The 2026-05-17 v0.4 exit-gate attempt 7 was the canonical
demonstration: the planner emitted `test_commands: [pytest -v
examples/broken_calc]` (wrong cwd assumption baked in), aider
correctly applied the bug fix, verifier failed with exit 4 (Bug
F), and the graph's only available recourse was `decision →
retry → coder`. retry ran the same bad slice again — same
failure. After `max_loops` exhaustion, the graph emitted
`ask_human` and stopped. **No layer in the graph was capable of
correcting the planner's mistake.**

Plan-and-Execute as a paradigm (LangChain 2023) allows
**replan-on-failure**: when execute fails, feed the structured
observation back to the planner for a corrected plan. ai-cockpit
v0.1–v0.4 implemented only "plan once, execute, retry-same"; row
#1 closes the gap by adding a `decision → planner` edge gated on
`replan_count < replan_max`.

Critically, this does NOT violate §9. The replan input is
`verification_result` (structured fact: exit codes, stderr, git
status, git diff) plus the previous slice (the planner's own
prior output). **`coder_result` narrative is never fed to
replan** — the §9 boundary is preserved.

## 2. Hard invariants (cannot be overridden at implementation time)

| Invariant | Source | How row #1 honours it |
| --- | --- | --- |
| §9 evidence-only reviewer | spec §9 | replan input contains `verification_result` (structured) + previous slice (planner's own output). `coder_result` is NOT in the replan input. Reviewer prompt is unchanged. The 5-test anti-deception suite stays byte-identical. |
| §9 symmetry (extended for row #1) | row #1 §3 Q3 | Replan planner does NOT see prior `coder_result` — even though replan is the planner, not the reviewer. This is deliberate: the §9 boundary stays symmetric across both critic-role nodes. |
| Bounded loops | row #1 §3 Q1 | `replan_count` field on `TaskState`; hard cap = 2 (user-locked). After `replan_count == 2` AND still failing → graph goes to `ask_human` per Q5. |
| ask_human on exhaustion | row #1 §3 Q5 | Consistent with existing retry-exhaustion behaviour. NO `stub_plan` fallback (that would produce a misleading deterministic plan after a real-LLM failure). NO hard `exit 1` (operator running interactively wants to see the state, not just exit code). |
| Criteria locked | row #1 §3 Q4 | Replan can rewrite `implementation_slice` and `test_commands`. Replan CANNOT rewrite `acceptance_criteria` or `mvp_spec` — those stay anchored to the user's original idea. Goal-shifting is forbidden by construction. |
| §3.2 memory write approval | hard rule §3.2 | No memory write. Replan input is composed in-memory from `TaskState`. |
| §12 permanent boundaries | spec §12 | No daemon, no UI, no swarm. Single-process graph, deterministic loop bound. |
| Cost is no longer a hard constraint | user statement 2026-05-17 15:05 UTC | Q2 dropped (replan tokens count whatever they count). v0.4 Q4 (1) ≤ $1 stays B.5-contract-locked but does NOT propagate as a row #1 constraint. |
| ≤8 files / ≤400 net LOC per PR | EXECUTION_RULES | Contract (this PR): 2 files / ≤350. Implementation: ≤6 / ≤300. |

## 3. Resolved decisions (user-locked 2026-05-17 15:08 UTC)

| # | Question | User decision | Rationale |
| --- | --- | --- | --- |
| Q1 | `replan_max` default | **2** | Bug F-class chains often need more than one self-correction; one replan after the first failure may itself fail (e.g. planner over-corrects). Two replans give the loop one extra chance before ask_human. Cost is not a constraint per user 15:05 UTC. |
| Q2 | Replan tokens count against B.5 Q4 (1) \$1? | **N/A — dropped.** | User stated cost is not a constraint. v0.4 B.5 \$1 cap stays a B.5-locked observation, not a row #1 design pressure. |
| Q3 | What does replan see? | **previous slice + `verification_result`. NOT `coder_result`.** | Structured-fact-only input preserves §9 symmetry. The planner can see what it previously emitted (its own slice) plus what the verifier observed (exit codes, stderr, git status/diff). Worker narrative stays out. |
| Q4 | Replan output scope | **slice + test_commands only. acceptance_criteria + mvp_spec locked.** | Anchoring goal at user-idea level prevents "move the goalposts" — replan cannot redefine success to make a failure look acceptable. Slice + test_commands are the legitimate authorship surface. |
| Q5 | Exhaustion path | **`ask_human`** | Same as existing retry exhaustion. Operator gets a coherent state to inspect. `stub_plan` would produce deterministic-but-wrong output; `exit 1` is unfriendly for interactive use. |

## 4. Graph topology change

### 4.1 Before (current master)

```
intake → planner → coder → verifier → reviewer → decision
                                                    ├─ retry → coder
                                                    └─ done / ask_human → summary → END
```

### 4.2 After (row #1)

```
intake → planner → coder → verifier → reviewer → decision
                                                    ├─ replan_then_retry → planner (with prev_attempt context)
                                                    ├─ retry → coder
                                                    └─ done / ask_human → summary → END
```

`decision` routing logic gains a 3-way branch:

```python
def route_after_decision(state) -> str:
    if state["decision"] == "done":
        return "summary"
    # Failure case
    if state["replan_count"] < state["replan_max"]:
        return "planner"  # replan_then_retry
    if state["loop_count"] < state["max_loops"]:
        return "coder"    # plain retry, same slice
    return "summary"      # ask_human exhaustion
```

Replan is **preferred over plain retry** when both budgets remain.
Rationale: if the verifier failed and the planner can self-correct,
that's a higher-quality recovery than re-running the same coder on
the same slice.

## 5. Data model

### 5.1 `TaskState` additions (`total=False`)

```python
class TaskState(TypedDict, total=False):
    # ... existing fields ...
    replan_count: int           # incremented each time replan fires
    replan_max: int             # default 2 from row #1 Q1
    previous_slices: list[dict] # the slices replan has rejected
    # ^ each entry: {"slice": {...}, "verification_result": {...}}
```

`previous_slices` is the replan-input context. Each entry pairs
the slice the planner emitted with the verification observation
that justified rejecting it.

### 5.2 Planner input on replan turn

When the planner is invoked as a result of `replan_then_retry`,
its user message gains a new structured block (after the existing
`Worker quirks` + Bug F `Verifier execution context` blocks):

```
Previous attempt(s) that failed verification:

Attempt 1:
  Slice emitted:
    {... slice as JSON ...}
  Verification result (FACTUAL, the only ground truth):
    {... verification_result as JSON, same shape as reviewer evidence ...}

[Attempt 2: ...]

Emit a corrected plan that addresses these verification failures.
You MAY rewrite implementation_slice and test_commands. You MUST
NOT rewrite acceptance_criteria or mvp_spec (those are anchored
to the user's original idea).
```

The JSON shape of `verification_result` matches the existing
reviewer evidence dict (per `build_reviewer_evidence`) — same §9
filtering applies (no `coder_result`).

## 6. CLI surface

New optional flag on both `ai-cockpit` top-level and `ai-cockpit
plans run`:

```text
--replan-max <int>
    Maximum number of replan-then-retry cycles before falling
    back to plain coder retry. Default: 2 (row #1 Q1). 0 disables
    replan entirely (pre-row-#1 behaviour). Range [0, 5].
```

Rationale for `[0, 5]` upper bound: replan_count > 5 in practice
means the planner is stuck in a local loop and operator
intervention is more valuable than more LLM calls. Hard upper
bound prevents accidental `--replan-max 999`.

## 7. File budget

**Contract (this PR):** 2 files / ≤350 net LOC.

- `docs/V0_5_ROW_1_PLANNER_REPLAN_CONTRACT.md` (new — this).
- `docs/V0_5_ROADMAP.md` (mod — flip row #1 status to "CONTRACT
  LOCKED").

**Implementation (separate PR, NOT pre-authorised):** ≤6 files /
≤300 net LOC.

- `src/ai_cockpit/state.py` (mod — add `replan_count`,
  `replan_max`, `previous_slices` fields; ~15 LOC).
- `src/ai_cockpit/graph.py` (mod — `replan_then_retry` edge +
  3-way decision routing; ~40 LOC).
- `src/ai_cockpit/nodes/planner.py` (mod — accept `previous_slices`
  in state; pass to message builder; ~25 LOC).
- `src/ai_cockpit/llm/prompts.py` (mod — `build_planner_messages`
  gains `previous_slices` kwarg, renders the block in §5.2; ~30
  LOC).
- `src/ai_cockpit/nodes/decision.py` (mod — update logic for
  `replan_then_retry` route; increment `replan_count`; ~20 LOC).
- `src/ai_cockpit/cli.py` (mod — `--replan-max` flag on `run` +
  `plans run`, threaded into `run_graph`; ~30 LOC).
- `tests/test_planner_replan.py` (new — happy path, replan
  exhaustion → ask_human, criteria lock enforcement, §9 isolation
  test asserting `coder_result` does not appear in replan prompt;
  ~80 LOC).

(7 files. If this exceeds ≤6 at implementation time, the test
file moves into the existing `tests/test_workflow.py`.)

## 8. Threat model

| Threat | Mitigation |
| --- | --- |
| Replan rewrites `acceptance_criteria` and "moves the goalposts" | Q4 locks criteria + mvp_spec. The replan planner message explicitly tells the LLM "you MUST NOT rewrite acceptance_criteria or mvp_spec". A validator in `make_planner_node` rejects any replan response that mutates either field (assertion against state's prior values); if mutated, the rejected fields are reverted and a warning logged. |
| `coder_result` leaks into replan input | The §5.2 message template is constructed in `build_planner_messages` from `previous_slices` (which contains slice + verification_result only) and never references `coder_result`. A dedicated test parametrises with `coder_result` set to a sentinel and asserts the sentinel does NOT appear in the replan planner prompt. |
| Replan loop becomes infinite (cost spiral even though cost-not-constraint) | `replan_count < replan_max` hard cap. Default 2. Upper bound 5 even with operator override. |
| Plain retry stops being reachable (replan always preferred) | The 3-way `decision` logic checks `replan_count < replan_max` first; if false, falls through to plain retry; if both exhausted, ask_human. Test coverage exercises all 3 paths. |
| §3.2 violation via replan writing memory | Replan is a planner invocation; planner does not write memory. No new memory surface. |
| Pre-row-#1 `TaskState` instances missing `replan_count` field | `total=False` plus default-on-read. `decision` reads `state.get("replan_count", 0)` and `state.get("replan_max", 2)`. Pre-row-#1 checkpoints decode cleanly. |
| Replan triggered after a flaky verifier (network blip) wastes a planner call | Acceptable trade-off. Without distinguishing transient vs persistent failure, we err on the side of replan (which produces a better plan if persistent; harmless if transient since the new slice resembles the old one). |
| Operator wants pre-row-#1 behaviour | `--replan-max 0` disables replan entirely; graph behaves exactly as v0.4. |

## 9. DoD

**Contract done (this PR) when:**

1. `docs/V0_5_ROW_1_PLANNER_REPLAN_CONTRACT.md` merged.
2. `docs/V0_5_ROADMAP.md` row #1 entry points here by filename.
3. Pre-push 4 checks pass.
4. No source / test touched.

**Implementation done (future, separate PR after user signal) when:**

1. `TaskState` gains `replan_count`, `replan_max`,
   `previous_slices` fields; existing checkpoints load cleanly.
2. `build_graph` wires the `decision → planner` edge; 3-way
   routing as in §4.2.
3. `build_planner_messages` accepts `previous_slices` kwarg and
   renders the §5.2 block when non-empty.
4. `--replan-max <int>` flag exposed on `run` + `plans run`.
5. `make_planner_node` enforces the criteria-lock invariant
   (rejects mutations to `acceptance_criteria` / `mvp_spec` on
   replan turns).
6. New `tests/test_planner_replan.py` covers happy path,
   exhaustion, criteria-lock, and §9 isolation (sentinel
   `coder_result` does not leak).
7. 5-test anti-deception suite stays byte-identical and green.
8. Pre-push 4 checks pass; ≤6-or-7 / ≤300 budget respected.

## 10. Out of scope for row #1

- No replan on `done` (replan only fires on verification failure).
- No replan triggered by the reviewer alone (e.g. high `risk_level`
  with `passed=True`) — that's a separate gate.
- No partial-slice replan (replan emits a whole slice; no
  "rewrite just the test_commands of this slice" surface).
- No replan input enrichment beyond §5.2 (e.g. no log files, no
  worker stdout) — keeps the §9 boundary trivially auditable.
- No multi-thread parallel replan (single-process, serial loop).
- No replan-driven memory writes (memory pipeline untouched).
- No replan budget tied to cost — Q2 dropped per user.

## 11. Rollback

If the implementation PR proves harmful:

1. Revert the implementation PR.
2. Operators using `--replan-max 0` already experienced
   pre-row-#1 behaviour, so the rollback is non-breaking for
   them.
3. Checkpoints written post-row-#1 still decode under pre-row-#1
   schema because `total=False` (extra keys ignored).
4. Contract (this file) stays as historical record.

## 12. Authorisation & operating rhythm

Per the 2026-05-17 15:08 UTC user-locked authorisation:

1. **Contract draft only.** This PR ships this file + ROADMAP
   pointer.
2. **Implementation gated by Phase 0** (V0_4 evidence merged) AND
   explicit `open-gate v0.5-row-1-impl` signal.
3. **One tick, one gate.**

## 15. Open-gate protocol

```text
open-gate v0.5-row-1-contract       # granted 2026-05-17 15:08 UTC;
                                    # this PR is the deliverable.
open-gate v0.5-row-1-impl           # NOT granted — requires
                                    # (a) V0_4 evidence on master AND
                                    # (b) explicit user signal.
open-gate v0.5-row-1-replan-sees-coder-result   # NEVER GRANTED;
                                    # §9 boundary; Q3 locked.
open-gate v0.5-row-1-criteria-rewrite           # NEVER GRANTED;
                                    # Q4 locked; would enable
                                    # goal-shifting.
open-gate v0.5-row-1-stub-plan-fallback         # NEVER GRANTED;
                                    # Q5 locked ask_human; stub
                                    # would produce deterministic
                                    # but misleading plan after
                                    # real-LLM failure.
```

A future `open-gate v0.5-row-1-impl` signal must (a) confirm V0_4
evidence merged on master AND (b) accept Q1+Q3+Q4+Q5 as locked
(Q2 already N/A). Without (a), cron stops with an OQ. Without
(b), cron treats as ambiguous and stops with an OQ.
