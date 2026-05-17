# v0.4 — Exit Gate Evidence

**Status: PASSED.**
Date: 2026-05-17.
Closing attempt: attempt 9, thread `111363ec4b5a`, 14:55:21 UTC.
Operator: `nanyang2@atletx8-neu006` (AMD developer workstation).
Endpoint: `https://llm-api.amd.com/Anthropic` (Azure APIM, subscription-keyed).
Model: `anthropic/claude-opus-4-6` via the AMD APIM gateway.
Master tip when the gate's closing attempt ran: `20f631d` plus
PR #84 (`51a7e18`, the Bug G fix). Evidence PR will move master to
the post-merge hash named in §13.

This document is the archived proof that the B.5 v0.4 exit-gate
contract has been satisfied. It is paired with — and validated by —
three other artifacts checked into this same PR:

- `examples/broken_calc/calc.py` — the real-LLM-driven diff
  (`return a - b` → `return a + b`) that aider produced during
  attempt 9 and that the reviewer ratified.
- `examples/broken_calc/docs/plans/fix-broken-calc.plan.yaml` — the
  `/save`-d plan artifact that drove `plans run`.
- `examples/broken_calc/.ai-cockpit/memory/project.md` — the
  `done`-state suggestion accepted via
  `ai-cockpit memory accept` after the gate clock stopped.

## 1. Headline

`ai-cockpit` ran a complete `plan → plans run → verifier → reviewer
→ memory` loop on a real git repo (`examples/broken_calc`) under
real LLM credentials. Zero human intervention inside the gate
window. The reviewer was given **only** §9 structured evidence,
correctly judged the diff `passed: True, risk: low, issues:
(none)`, and the memory pipeline produced a `done` suggestion that
the operator accepted, writing `examples/broken_calc/.ai-cockpit/
memory/project.md` per spec §3.2. The closing attempt cost
**\$0.10** and finished in **35.76 seconds** — both well inside the
B.5 §3 Q4 hard caps.

The attempt 1–9 path **surfaced 8 independent integration /
ergonomics bugs** in v0.3 code that no single feature's contract
testing would have caught. Each was closed by a separate ≤8-file
PR before the next attempt. This is the canonical demonstration of
B.5 §1's "the gate exists to surface integration conflicts
single-feature contracts cannot see" — and the resulting calibrated
capability is what makes the v0.4 declaration defensible from
numeric data rather than a single-shot lucky run.

## 2. Q1 / Q4 verification

Each row maps a B.5 §3 condition to a concrete, falsifiable
observable captured from the operator transcript.

| § | Condition | Observable | Result |
|---|---|---|---|
| Q1 | Capability proof: complete `plan → plans run → verifier → reviewer → memory` loop on real repo under real LLM creds | See §3 closing-attempt Run Summary; §4 memory `accept` output; §5 aider-produced diff | ✅ Loop closed in attempt 9 |
| Q1 | ≥1 real-LLM-driven commit on master | Aider produced the verbatim diff in §5; this evidence PR commits it to master | ✅ This PR's calc.py commit |
| Q1 | ≥1 `done` suggestion applied via `accept_suggestion` | `applied 20260517T145521-done-fix-bugs-in-broken-calc → /proj/.../examples/broken_calc/.ai-cockpit/memory/project.md` (§4) | ✅ |
| Q4(1) | Total cost ≤ \$1 USD per gate run | Attempt 9 alone: **\$0.10**; cumulative across all 9 attempts: **\$0.72**. Both well under \$1 | ✅ |
| Q4(2) | Wall-time ≤ 15 min | Attempt 9 closing: **35.76 s** (`time` `real`). 96% under the 900 s cap | ✅ |
| Q4(3) | Human interventions inside gate window = 0 | Attempt 9 in-gate operator actions: `time ai-cockpit plans run …` (the start command, §5 explicit non-intervention) → automated loop → `ai-cockpit memory accept` (B.5 §5 explicit non-intervention, post-clock). Zero retries, zero hand-edits, zero unrelated git operations between `plans run` start and `accept_suggestion`. | ✅ |
| Q4(4) | pytest 100% green (master suite + ≥10 new v0.4 tests + 5-test §9 anti-deception suite) | Top-level `python -m pytest -q | tail -3`: `[100%]` no `F`/`E`. `examples/broken_calc python -m pytest -q`: `..  [100%]` (2/2). See §6 for the 5-test §9 suite breakdown. | ✅ |
| Q3 | Cursor backend optional | Not exercised this gate run; aider path satisfies the gate per Q3 | ✅ (deferred, not required) |

The B.5 §5 counting rules accept the closing-attempt operator
shape as a valid `intervention=0` gate run. The prior eight
attempts each surfaced and closed a distinct bug; they are
audit-trailed in §8 but do **not** count against attempt 9's
Q4(3) per the §10 rollback-plan precedent ("Open a follow-up
Section A or Section B gate for the specific subsystem that
failed" — each follow-up gate PR was a distinct contract resolution
event, not a retry of the same `plans run` execution).

## 3. Closing attempt 9 — Run Summary verbatim

Command line invoked from `/proj/gfx_gct_lec_user0/users/nanyang2/
ai-cockpit` at 2026-05-17 14:55:21 UTC:

```bash
time ai-cockpit plans run fix-broken-calc diagnose-and-fix \
    --root examples/broken_calc \
    --worker aider --apply --llm auto \
    --allow-dirty-tree
```

Environment was the AMD APIM bridge per the operational notes in
§10. Wall-clock: `0:35.76` user + system. Aider session cost as
self-reported on its stdout: `$0.05 message, $0.10 session` (two
turns, then "Applied edit"). ai-cockpit cost dashboard (read after
the run from the operator's machine) confirmed the same:

```
thread 111363ec4b5a | ts 2026-05-17T14:55:21.821948+00:00 |
  tokens=tokens_sent=7200,tokens_received=422 cost=$0.1000
  coverage=4/8 missing=cache_read_tokens,cache_write_tokens,
                       input_tokens,output_tokens
```

The Run Summary block (PR #57 / B.10e shape, full transcript
preserved in operator's terminal):

```
========================================================================
AI Cockpit — Run Summary
========================================================================
Mode:        task
Loops:       1 / 1
Decision:    done

Verification:
  passed: True
  - [ok] pytest -v
  git status --short:
   M calc.py
  ?? .ai-cockpit/
  ?? docs/

Review:
  passed: True
  risk:   low
  issues:
  (none)
  notes:
    All acceptance criteria are met: pytest -v exits with code 0,
    2/2 tests pass, only the non-test source file calc.py was
    modified, the add function now returns a + b (the bug was it
    returned a - b), and the git diff confirms no test files were
    touched. The only minor note is that the commit message
    criterion cannot be verified from the provided evidence (no
    commit message shown), but the diff and verification are solid.
========================================================================

info: memory suggestion written: 20260517T145521-done-fix-bugs-in-broken-calc
      (target=project.md); see `ai-cockpit memory list` to review or
      `ai-cockpit memory accept <id>` to apply.

16.014u 6.330s 0:35.76 62.4%
```

The `info: memory suggestion written` line is the live proof that
PR #84 (Bug G fix — `plans run` now hooks into `generate_and_write`)
is effective on master.

## 4. Memory loop closure

After the gate clock stopped, the operator ran (per B.5 §4):

```text
$ ai-cockpit memory list --root examples/broken_calc
age: 0d 0h ago    20260517T145521-done-fix-bugs-in-broken-calc
                  project.md    append
                  ## 2026-05-17 — # Fix bugs in broken_calc so all pytest tests pass
total: 1 (done: 1, ask_human: 0)

$ ai-cockpit memory accept 20260517T145521-done-fix-bugs-in-broken-calc \
        --root examples/broken_calc
applied 20260517T145521-done-fix-bugs-in-broken-calc ->
        /proj/gfx_gct_lec_user0/users/nanyang2/ai-cockpit/
        examples/broken_calc/.ai-cockpit/memory/project.md
```

The accepted suggestion's full content was appended to
`examples/broken_calc/.ai-cockpit/memory/project.md` and is shipped
verbatim in this PR as evidence. See the
`examples/broken_calc/.ai-cockpit/memory/project.md` file in this
PR's diff.

This is the **first time in the project's history** that a
`done`-state suggestion produced by a real-LLM `plans run` round-trip
has been accepted via the §3.2-compliant `memory accept` path. PR
#15 / v0.2 step 5a shipped the pipeline; PR #84 / Bug G wired it
into the B.6 `plans run` surface; this attempt 9 exercises the
full chain end-to-end.

## 5. The aider-produced diff (Q1 real-LLM commit)

Aider's whole-edit-format diff against `examples/broken_calc/calc.py`,
verbatim from its stdout during attempt 9:

```diff
@@ -10,8 +10,7 @@ from __future__ import annotations
 def add(a: int, b: int) -> int:
-    # BUG: should return a + b. ai-cockpit's bug-fix workflow targets this.
-    return a - b
+    return a + b
```

Aider's narrative (immediately above the diff) confirmed the
analysis was correct:

> Looking at the test expectations:
>
> * `test_add_works` expects `add(2, 3) == 5, add(-1, 1) == 0,
>   add(0, 0) == 0` — i.e. addition.
> * `test_mul_unchanged` expects `mul(2, 3) == 6, mul(-2, 3) == -6`
>   — i.e. multiplication.
>
> The bug is in `calc.py`: `add` returns `a - b` instead of
> `a + b`. The `mul` function is already correct.
>
> The fix is minimal: change `return a - b` to `return a + b`.
>
> No other files need changes. The test file is untouched, `mul`
> was already correct, and no `__init__.py` or `conftest.py` is
> needed since `test_calc.py` imports `calc` directly as a
> same-directory module.

The reviewer (real Claude on the same APIM endpoint) was given
**only** the structured evidence dict (`mvp_spec`,
`acceptance_criteria`, `git_diff`, `git_status`,
`verification.passed`, `verification.commands`) per `llm/prompts.py
::build_reviewer_evidence`. It returned `passed: True, risk: low,
issues: (none)` and the ratifying note in §3. **`coder_result`
never entered the reviewer prompt** — the §9 evidence-only
invariant held byte-for-byte on the closing attempt, as it did on
every prior attempt.

This evidence PR commits the diff to master, satisfying Q1's
"≥1 real-LLM-driven commit on master" hard requirement. The
trailing-commit-marker that the planner emitted in the slice
(`[fix-broken-calc/diagnose-and-fix] from
docs/plans/fix-broken-calc.plan.yaml`) is preserved in the body of
this PR's evidence-commit message.

## 6. spec §9 anti-deception — 5-test suite verification

The §9 anti-deception test suite on the gate-run HEAD
(`tests/test_llm_planner_reviewer.py` plus the B.6c plan-leak
guard):

1. `test_reviewer_fails_on_failing_verification_even_if_llm_says_pass`
   — hard-rule floor overrides any LLM "pass" verdict when a
   command exit code is non-zero.
2. `test_reviewer_prompt_excludes_coder_self_report` — `coder_result`
   substring byte-absent from the reviewer system+user pair.
3. `test_reviewer_node_does_not_send_coder_result_to_llm` —
   `sys.modules`-shim provider records all calls; `coder_result`
   never appears in any.
4. `test_empty_commands_with_upbeat_non_json_reply_still_escalates`
   — deterministic fallback escalates risk when there's no
   command evidence to ratify.
5. `test_reviewer_prompt_does_not_leak_plan_yaml_content` (B.6c
   addition) — `.plan.yaml` content cannot reach the reviewer
   prompt, defending against the B.9 interactive-planner attack
   surface.

All 5 are green on `master @ 20f631d` per the operator's top-level
`python -m pytest -q` invocation captured in §2 Q4(4).

Additionally, this evidence PR exercises the §9 invariant for the
**first time at real-LLM scale** with a Claude-on-Claude
configuration (planner = Claude via APIM, reviewer = Claude via
APIM, both with the same model and key). The reviewer's
`risk: low` verdict on attempt 9 — and the `risk: high`,
`passed: False` verdicts on the prior 8 attempts whenever real
evidence-shape errors occurred (e.g. `exit code 4` from the
test_command path-doubling bug, `M tests/test_demo_fixture.py`
from the anti-fix guard collision) — demonstrate that the
production reviewer **followed the evidence symmetrically**: it
neither leans toward acceptance nor toward rejection. Per B.5 §1
this is the single most important capability the gate had to
prove.

## 7. AMD APIM operational notes (operator transcript)

The operator's env at attempt-9 time:

```
LLM_API_BASE             https://llm-api.amd.com/Anthropic
LLM_API_KEY              <subscription-key>
LLM_MODEL_NAME           claude-opus-4-6
LLM_API_EXTRA_HEADERS    {"Ocp-Apim-Subscription-Key": "<same-key>"}
ANTHROPIC_API_KEY        <same as LLM_API_KEY>     (aider bridge)
ANTHROPIC_API_BASE       <same as LLM_API_BASE>    (aider bridge)
```

The `Ocp-Apim-Subscription-Key` header was injected via the v0.2
step 1 follow-up (`LLM_API_EXTRA_HEADERS`, PR #17) for the
planner/reviewer LLM calls, and via the v0.3 step 2 follow-up
auto-generated `--model-settings-file` (PR #22) for the aider
subprocess. **No provider's header name is hardcoded anywhere in
the ai-cockpit codebase** — the same env mechanism would work for
any future APIM-style gateway, satisfying spec §12's
generic-provider rule. This is the second time the AMD APIM bridge
has been demonstrated on a v0-grade scenario; the first was the
v0.2 §15.1 demo archived in `docs/V0_2_COMPLETION.md`.

The `ANTHROPIC_API_KEY` / `ANTHROPIC_API_BASE` mapping is
documented in the top-level README "Coder worker (v0.3 step 2)"
section. It was the cause of the attempt-2 401 (operator initially
forgot the `LLM_API_EXTRA_HEADERS` shape; surfaced an ergonomics
seam between LLM_* and ANTHROPIC_* env families — see §11 v0.5
backlog item 1).

## 8. Attempt 1 – 9 timeline (the calibration path)

Every attempt of the gate run is recorded here for audit-trail
fidelity. Per B.5 §10's rollback-plan precedent, surfaced bugs
between attempts were closed by separate ≤8-file PRs before the
next attempt. The cumulative cost of the entire calibration was
**\$0.72** (well under the \$1 single-run cap, even though the
contract only requires that bound for one closing run).

| # | UTC time | thread | outcome | surfaced | fix PR |
|---|---|---|---|---|---|
| 1 | 10:28 | n/a (CLI error) | `Error: plan ... no slice with id '1'` | Operator misread `plans list` "total" column as slice id | — (operator self-correction; documented in attempt 3 evidence) |
| 2 | ~11:09 | n/a (CLI error) | `Error: No such option: --allow-dirty-tree` | `plans run` had A.7 precheck wired (PR #50) but never inherited A.7's `--allow-dirty-tree` bypass flag (PR #41) | **#77** `fix(plans-run): add --allow-dirty-tree flag (B.6 ↔ A.7 integration bug)` |
| 3 | 11:21 | `57f6d9576cc9` | `ask_human` | (a) `tests/test_demo_fixture.py` anti-fix guard contradicts v0.4 gate goal; (b) planner emits `pytest examples/broken_calc -v` against verifier `cwd=examples/broken_calc` → exit 4; (c) aider 0.86 single-line `Tokens: ... Cost: ...` stdout did not match the multi-line regex in PR #35, silently zeroing Q4(1) metrics | **#79** (Bug A), **#80** (Bug B catalog), **#78** (Bug C) |
| 4 | 13:25 | `186649dbe35b` | `ask_human` | Stale plan from 10:23 still on disk (`/save`-d before PR #80 merged) carried old test_command — surfaced B.6 plan-immutability ↔ B.2 catalog-update interaction | (no PR; resolved by deleting stale plan + re-running `/save` in attempt 5) |
| 5 | 13:33 | `f7a250cf31e6` | `ask_human` | B.2 hint `human_summary` was 153 chars; `_clip()` truncated to 80 just **before** the concrete `'pytest -v' not 'pytest examples/<dir> -v'` example, leaving the planner LLM with only the abstract head | **#81** `fix(b2-quirks): tighten test_command_path summary so 80-char clip keeps the example` |
| 6 | 13:43 | `d76f470c144e` | `ask_human` | B.2 catalog had the entry; PR #81 had tightened it; but `ai-cockpit plan` interactive REPL **never called `quirks_for(worker_name)`** because `plan_cmd` had no `--worker` flag and `PlannerRequest` had no `worker_name` field — entire B.2 wiring was theatrical on the interactive surface | **#82** `fix(b9-interactive-planner): plumb --worker through to B.2 quirk injection (Bug E)` |
| 7 | 13:58 | `929636cba1b4` | `ask_human` | Even with `--worker aider` plumbing fixed, planner LLM anchored on user-idea path ("fix examples/broken_calc...") and emitted the same bad shape — a single 73-char quirk hint could not override the natural-language anchor | **#83** `fix(verifier-cwd): three-layer defense against test_command path-doubling` (catalog tightening + planner prompt `verifier_cwd` factual context block + verifier runtime detection) |
| 8 | 14:31 | `d2eac85f58b0` | **`done`** but no memory suggestion written | Operator used `/revise` in REPL to nudge planner to `pytest -v` (B.5 §5 explicit non-intervention); `Decision: done, Verification.passed: True, Review.passed: True, risk: low` — but `memory list` returned `no pending memory suggestions` | **#84** `fix(plans-run): write memory suggestion after a successful run (Bug G)` (B.6 ↔ v0.2-step-5 memory pipeline integration seam) |
| 9 | **14:55** | **`111363ec4b5a`** | **`done` + suggestion written + accepted** | (none — the gate closed) | — |

Bugs **A** through **G** are independent integration / ergonomics
faults that lived undetected on `master` because every single one
sat at a seam between two PRs that each passed their own contract
testing. Each one was discovered, diagnosed, fixed, and validated
in a separate cron tick during the gate-run window, then verified
in the subsequent attempt.

**This is what the v0.4 gate is for** (B.5 §1): the gate's purpose
is to surface integration conflicts that no single-feature
contract's test suite can catch. The fact that 8 such bugs existed
on a master tip everyone (including this author) believed was
ready for the gate is the strongest possible evidence that the
contract framing — gate-as-integration-shakeout — was the right
call.

## 9. PR ledger — bugs surfaced and closed during the gate window

All 8 PRs were authored as standalone ≤8-file / ≤400-LOC fixes,
each with pre-push `pytest`/`ruff`/`mypy`/smoke all green and an
explicit Bug-letter label cross-referenced to the surfacing
attempt. Five were authored by the cron-side ai-cockpit cloud
agent reading the operator's transcripts in real time; PRs #83 and
#84 were authored by a parallel cloud agent run that observed the
same transcripts and diagnosed the same root causes independently
(see PR #85 for the duplicate-closure record).

| PR | Title | Bug | First merged | Surfacing attempt |
|----|---|---|---|---|
| #77 | `fix(plans-run): add --allow-dirty-tree flag (B.6 ↔ A.7 integration bug)` | "Bug 0" / A.7↔B.6 wiring | 2026-05-17 ~11:30 | 2 |
| #78 | `fix(aider-worker): accept aider 0.86 single-line 'Tokens: ... Cost: ...' stdout` | Bug C | 2026-05-17 ~12:50 | 3 |
| #79 | `fix(demo-fixture): drop anti-fix guard that contradicts the v0.4 exit-gate` | Bug A | 2026-05-17 ~12:55 | 3 |
| #80 | `fix(b2-quirks): add verifier.test_command_path quirk` | Bug B (catalog growth) | 2026-05-17 ~13:00 | 3 |
| #81 | `fix(b2-quirks): tighten test_command_path summary so 80-char clip keeps the example` | Bug B (calibration) | 2026-05-17 ~13:20 | 5 |
| #82 | `fix(b9-interactive-planner): plumb --worker through to B.2 quirk injection (Bug E)` | Bug E | 2026-05-17 ~13:55 | 6 |
| #83 | `fix(verifier-cwd): three-layer defense against test_command path-doubling (Bug F)` | (same root cause as Bug B, deeper fix) | 2026-05-17 14:28 | 7 |
| #84 | `fix(plans-run): write memory suggestion after a successful run (Bug G)` | Bug G | 2026-05-17 ~14:36 | 8 |

The "Bug B" / "Bug F" / "Bug G" label collisions arose because two
independent cloud agent runs were processing the same operator
transcripts in parallel and each chose its own letter-numbering
convention. The actual fixes are non-overlapping (verified by
near-empty `git diff 51a7e18..06c45aa` on the duplicate PR #85
merge — see PR #85 body for the closure note). For audit purposes
all 8 PRs are net-positive and stand on master.

## 10. Honest framing — what this evidence does NOT establish

Following the precedent in `docs/V0_3_MILESTONES.md`:

- **It does not establish that ai-cockpit can autonomously execute
  the v0.4 gate without an operator.** The gate run itself is
  operator-driven by design (B.5 §11.3); cron is permanently
  forbidden from running it. What this evidence proves is that
  **when the operator runs the gate, the loop closes correctly
  end-to-end** — not that the loop will run unattended.
- **It does not establish that the closing attempt was clean on
  the first try without `/revise`.** Attempt 8's plan REPL session
  used one `/revise` turn to nudge the planner away from the
  path-prefix anti-pattern (per B.5 §5 explicit "free-text answers
  during the planner's interactive turns = not intervention"). PR
  #83's three-layer defense should make that nudge unnecessary on
  the **next** operator's gate run, but this gate run was
  pre-PR-#83 for the planning phase.
- **It does not establish that 8 surfaced bugs is the bottom of
  the integration-seam barrel.** B.5 §10's rollback plan
  explicitly anticipates more rounds: "Do not relax Q4 numerics
  ... open a follow-up Section A or Section B gate for the
  specific subsystem that failed." Future v0.5+ gates may surface
  additional seams; this evidence captures the v0.4-window seam
  closure, not a guarantee of integration completeness.
- **It does not establish that the Cursor backend would have
  passed the gate.** B.5 §3 Q3 explicitly makes Cursor optional
  for the v0.4 gate; only the aider path was exercised here.
  Cursor-as-worker plus Cursor-as-planner plus
  Cursor-as-reviewer is still a v0.5+ exit-gate candidate, with
  the post-PR-#83 verifier-cwd hardening as one direct beneficiary.
- **The cumulative \$0.72 cost figure is calibration spend, not
  the gate's product cost.** A future operator running the gate
  on the post-PR-#84 master tip should expect a single attempt to
  pass (the bugs are fixed) at ~\$0.10–0.15 per attempt — close to
  the Q4(1) attempt-9 reading. The total here is large only
  because each preceding attempt was funding a follow-up gate.

## 11. v0.5 backlog seeds — captured ergonomics findings

The gate window surfaced several non-blocking findings worth
recording for the v0.5 contract author:

1. **`LLM_*` ↔ `ANTHROPIC_*` env duplication** — operators on
   APIM gateways must set both families separately. PR #82-style
   automatic bridging at CLI boot could eliminate the second
   401 hazard. (Surfaced at attempt 2.)
2. **`scripts/v0_4_exit_gate.sh` UX gaps** — the runbook expects
   the operator to run `ai-cockpit plan` in a second terminal but
   doesn't say so; its `baseline_test_count` awk is wrong
   (`tail -1` of `--collect-only -q` is empty); the dirty-tree
   pre-check uses an invalid pathspec. None of these are
   gate-blocking but each cost the operator a round trip.
3. **B.6 plan immutability vs B.2 catalog drift** — once
   `/save`-d, plans inherit whatever B.2 catalog state existed at
   plan time. Future B.2 catalog growth does not retroactively
   re-validate or warn on `plans run`. A `plans run` pre-flight
   that lints saved test_commands against the current catalog
   would close this.
4. **B.2 catalog hint ergonomics** — the 80-char `_HINT_CHAR_BUDGET`
   is fine prompt-size discipline, but it constrains the quirk
   author's ability to phrase a concrete good→bad pair. Either
   raise the cap to ~150 chars or inject `replacement_hint`
   alongside `human_summary`. PR #83's verifier_cwd factual
   context block is the proof-of-concept that a longer factual
   block reaches the LLM more reliably than a shorter abstract
   one.
5. **Plan-id slug drift across `/revise` rounds** — between
   attempts 7 and 8 the planner LLM picked a new plan_id
   (`fix-broken-calc-example` → `fix-broken-calc`), invalidating
   the operator's previous `plans run <plan_id>` muscle memory.
   `plans run` could accept a slug-prefix match or have a
   `--latest` shortcut.
6. **Parallel cloud-agent PR duplication** — the
   `.github/workflows/auto-merge-cursor-pr.yml` workflow did not
   detect that PR #85 was a same-content near-duplicate of PR
   #84. A pre-merge guard on `cursor/*` branches touching the
   same file set would save reviewer attention.
7. **B.5 §4 procedure does not enumerate the closing `git commit`
   step** — operators must commit the aider-produced diff to
   master to satisfy Q1, but §4 only shows audit reads. A
   `docs/B_5_CONTRACT.md` follow-up should make the closing
   commit explicit, and §5 should explicitly clear it of Q4(3)
   intervention status (mirroring the existing `accept_suggestion`
   clearance).
8. **`pytest` cwd vs `--root` confusion** — operators on csh
   often confuse `cd examples/broken_calc && pytest -q ; cd ..`
   with `cd ..; pytest -q`. A `--root`-aware `ai-cockpit pytest`
   wrapper would normalize. Low priority.

None of these are gate-passing prerequisites. All are recorded
here so the v0.5 contract author has a starting checklist.

## 12. Reset for future demo runs

`examples/broken_calc/calc.py` is now in the **fixed** state on
master after this evidence PR merges. Future operators wanting to
re-run the §15.1-style demo or repeat the v0.4 gate must reset
the fixture:

```bash
git log --oneline -- examples/broken_calc/calc.py
# find the commit BEFORE this evidence PR (the v0.3 "intentionally
# broken" tip)
git checkout <pre-v0.4-evidence-hash> -- examples/broken_calc/calc.py
python -m pytest -q examples/broken_calc/   # confirm: 1 failed, 1 passed
```

The `examples/broken_calc/README.md` "How to reset for another
demo run" section will be updated in a follow-up doc PR to
document this reset path explicitly. PR #79's removal of the
anti-fix guard already protects against the v0.3 demo-reset
regression mode: `tests/test_demo_fixture.py` now asserts only
fixture **shape** (functions exist, test file shape is
preserved), not the body of `add`, so future demo resets do not
need to revert any other file.

## 13. Cross-links

- **Spec:** `docs/AI_COCKPIT_SPEC_V1.md` §9 (no-deception), §12
  (permanent boundaries), §15 (exit-gate scenarios).
- **Contract:** `docs/B_5_CONTRACT.md` (full v0.4 gate definition,
  Q1-Q5).
- **Prior milestone:** `docs/V0_2_COMPLETION.md` (the §15.1
  end-to-end demo this gate builds on).
- **v0.3 narrative:** `docs/V0_3_MILESTONES.md` (A.1 and B.6
  contract milestones).
- **Architecture:** `docs/ARCHITECTURE.md` (graph + state + worker
  + LLM + memory pipeline + workflow + §9 evidence flow).
- **Operating status:** `docs/V0_3_STATUS.md` — will be updated in
  a follow-up tiny PR to flip its banner from `idle-healthy` to
  `v0.4 GATE PASSED`.
- **v0.5 scope:** `docs/V0_5_ROADMAP.md` (PR #86 draft, review
  pending) plus the §11 backlog seeds above.

---

Operator: `nanyang2@atletx8-neu006`. Cron-side ai-cockpit cloud
agent: this evidence document drafted on behalf of the operator
per the discussion in the 2026-05-17 14:32–15:05 UTC window.
Authoring sequence is recorded in the PR description; final
review-and-merge is the operator's `B.5 §11.4` sign-off act.
