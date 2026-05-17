# B.5 — v0.4 exit-gate definition (contract v0.1)

Status: **contract authored, awaiting user open-gate signal for the
actual gate run.** This document is the locked specification for what
"v0.4 is done" means. It is a pure-documentation deliverable: no source
under `src/` and no test fixture is modified by it. The matching summary
in `docs/ROADMAP.md` §B.5 is updated to point here.

> Until the user explicitly says "open-gate B.5 exit run" (or the
> equivalent — see §15 for the exact signal shape), cron is NOT
> authorized to execute the gate run itself, only to land contract
> and dashboard preparation gates (queue items #6 and #7).

## 1. Why

v0.3 shipped Section A (8/8), Section B's required set (B.6 3/3,
B.9 3/4, B.10 required 4/4 plus the optional B.10e Writer), and the
B.10pty hardening (queue items #1 and #2 of the current 72h window).
Master tip at contract authoring time: `ba1a1b9`. The project has all
the pieces — planner, plans, worker, verifier, reviewer, memory,
suggestions, accept_suggestion — and four backends (`stub`, `aider`,
`cursor`, builtin LLM) but has never been asked to **drive a single
end-to-end real-LLM loop on a real repository with zero human
intervention**. v0.4's job is exactly that.

v0.2's exit gate was prose-grade ("scenarios 1 and 3 from spec §15
demonstrably save human time"). v0.4 needs to be numeric and
falsifiable so cron can decide "gate passed" without inviting "small
extra improvement" temptation.

## 2. Hard invariants (cannot be overridden)

These override everything in §3–§15 of this contract, override the
v0.4 evidence document, and override any "we are close, let us
relax one rule" judgement at gate-run time.

| Invariant | Source | How B.5 honors it |
| --- | --- | --- |
| §12 permanent boundaries | spec §12 | The exit gate run executes only on a local repo. No daemon, no UI, no cloud backend, no multi-repo, no outbound email/Slack/PR comments, no plugin marketplace, no agent-to-agent swarm. |
| §9 evidence-only reviewer | spec §9 | Reviewer prompt must contain only `mvp_spec`, `acceptance_criteria`, `git_diff`, `git_status`, `verification_result`. The anti-deception suite (5 tests after B.6c) must be 100% green on the gate run's HEAD. Cursor reviewer backend (if exercised) must respect the same shape — pinned by B.10d's tests. |
| §3.2 memory write approval | hard rule §3.2 | The memory `done` suggestion that closes the loop must be applied via `ai-cockpit memory accept`. No direct write to `.ai-cockpit/memory/*`. Cron is not authorized to run `memory accept` for the gate — it is a human action and counts against "human interventions" if performed by the user mid-run. |
| ≤8 files / ≤400 net LOC per PR | EXECUTION_RULES | This is a documentation-only PR. No source touched, no test added, no schema migrated. Contract is itself ≤2 files / ≤350 net LOC (queue row #5). |
| One gate per cron tick | AUTOMATION_PROMPT §3.3 | This PR is queue item #5; queue items #6 and #7 (B.3 contract and B.3 implement) follow on subsequent ticks. The actual v0.4 exit-gate run is **not** a cron action — see §11. |
| No real LLM in CI | AUTOMATION_PROMPT §3.5 | The gate run is operator-driven, not CI-driven. CI continues to run on mocks only; the gate run lives in `docs/V0_4_EXIT_EVIDENCE.md` as a human-witnessed artifact. |

## 3. Resolved design decisions (Q1–Q5, locked 2026-05-17 03:57 UTC)

The five questions raised in the 2026-05-17 prompt body were resolved
by the user as follows. Each row records the final decision plus the
rationale that makes it not arbitrary. These answers are **immutable
for the 72h authorization window** (ends 2026-05-20 03:57 UTC); any
deviation observed at gate-run time is a STOP-and-OQ event, not a
self-resolve event.

| # | Question | Decision | Rationale |
| --- | --- | --- | --- |
| Q1 | What capability must v0.4 prove? | `ai-cockpit` runs a complete `plan → plans run → verifier → reviewer → memory` loop on a real git repo (default `examples/broken_calc`) under real LLM credentials. Planner emits `.plan.yaml`. `plans run` invokes the chosen worker per slice. Verifier runs real tests. Reviewer follows the §9 evidence-only path. Memory pipeline produces ≥1 `done`-state suggestion accepted via `accept_suggestion`. Zero human intervention. Zero §9 deception. | This is the smallest end-to-end proof that the whole system works as designed. Anything smaller (e.g., "just check planner runs") fails to exercise the integration surface and would let regressions through. |
| Q2 | Is real-LLM E2E evidence required? | Yes. Minimum reproducible path: set `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`, run `ai-cockpit plan "<idea>"` → `/save` → `ai-cockpit plans run <plan_id> <slice_id> --worker aider --apply --llm auto`. Master must end with ≥1 real-LLM-driven commit. `.ai-cockpit/suggestions/` must end with ≥1 `done` suggestion. The run, the prompt, token / cost telemetry, reviewer verdict, and the post-run `git log` slice are all archived to `docs/V0_4_EXIT_EVIDENCE.md`. | Mock-LLM CI proves shape, not capability. Without a real run, "v0.4 works" is unfalsifiable. Evidence-in-repo is the single source of truth — chat transcripts decay, repos persist. |
| Q3 | Is the Cursor backend required for the gate? | Optional. The aider + builtin-LLM path alone must satisfy the gate. Cursor backend is a bonus that runs the same scenario again with `--worker cursor` and documents results in the same evidence file. If the bonus cursor run exceeds the Q4 cost cap, that is recorded (not failed); the gate's pass/fail is judged on the aider path. B.10pty (queue items #1 and #2) is the prerequisite for the cursor bonus to be runnable at all. | Two independent worker backends de-risk a single-backend failure mode, but forcing both to pass would over-constrain the gate. Cursor's default workspace scan is ~19k input tokens/turn — known cost item, properly addressed in v0.5+ optimization, not v0.4 hard caps. |
| Q4 | What are the hard pass/fail metrics? | All four must hold simultaneously (AND): **(1)** total cost ≤ $1 USD for a single exit-gate run; **(2)** total wall-time ≤ 15 minutes; **(3)** human interventions = 0 (any operator action other than starting the run = failure); **(4)** test suite 100% green = the existing 259 tests on master at contract time **plus** ≥10 new v0.4 tests, plus the 5-test §9 anti-deception suite 100% green. Cursor path exceeding $1 is logged in evidence, not gate-failing (aider passing alone = gate green per Q3). | Each metric has a falsifiable observable. Cost bounds blast radius. Wall-time forces real graph efficiency (not "leave it running overnight"). Zero-intervention is the actual product claim. Test coverage prevents regressions slipping in alongside the headline E2E. Numbers come from current operating state (236 baseline cited in 2026-05-17 prompt; cron's local pytest count at this contract = 259 after B.10pty-bugfix added 5; gate-run baseline shall be whatever master pytest yields at gate-run time). |
| Q5 | What is explicitly excluded from v0.4? | Out of scope for v0.4 exit gate: cost auto-optimization, prompt auto-tuning, any daemon / UI / web app shape, multi-repo parallel run, agent-to-agent swarm / A2A protocols, automatic outbound email / Slack / PR comments, browser automation, real-LLM call-budget auto-expansion. Of these, daemon / UI / cloud / swarm / auto-outbound are already permanent §12 boundaries; the remainder (cost auto-tune, prompt auto-tune, multi-repo, browser, budget auto-expand) are deferred to v0.5+ as separate gated items. | Scope discipline. Each excluded item could pass for "small extra improvement" during v0.4 but each is a known scope-creep vector with no v0.4-grade evidence backing it. Naming them explicitly converts ambiguity into a STOP+OQ trigger. |

## 4. Concrete gate-run procedure

The user (or a human operator under user-supervision) runs the
following at gate time. Cron does **not** execute these steps; cron
only authors this contract, lands B.3 (the cost dashboard that
backs the Q4 cost reading), and observes the resulting evidence
file once it merges.

```bash
cd <ai-cockpit checkout>
git checkout master
git pull --ff-only origin master
source .venv/bin/activate

export ANTHROPIC_API_KEY=...      # or OPENAI_API_KEY
export AICKPT_PROVIDER=auto       # builtin LLM resolves provider

cd examples/broken_calc
git status                        # must be clean

ai-cockpit plan "fix broken_calc so pytest passes end-to-end" \
  --root . --llm auto             # interactive; user types /save when ready

ai-cockpit plans list             # confirm <plan_id> and <slice_id>

time ai-cockpit plans run <plan_id> <slice_id> \
  --worker aider --apply --llm auto --root .

# verifier + reviewer + memory run inside plans run.
# expected: ≥1 real commit, ≥1 done suggestion in .ai-cockpit/suggestions/.

ai-cockpit memory list            # confirm suggestion id
ai-cockpit memory accept <suggestion_id>

ai-cockpit cost --since today     # Q4 (1): total ≤ $1 (uses B.3 dashboard)
git log --since=00:00 --oneline   # Q4 evidence: real-LLM-driven commit(s)
pytest                            # Q4 (4): full suite green
```

Capture all of the above into `docs/V0_4_EXIT_EVIDENCE.md`: command
lines verbatim, timestamps, cost reading, `git log` slice, reviewer
verdict JSON, suggestion JSON, final pytest summary. Add the run's
master HEAD before and after.

## 5. Definition of "human intervention" (Q4 metric 3)

Counting rules for the zero-intervention claim:

- **Not an intervention:** starting the run (typing the commands in
  §4), pressing Enter / typing free-text answers during the planner's
  interactive turns (planning is the human approval step — the gate
  measures execution intervention), typing `/save` once.
- **Is an intervention:** any retry of a failed `plans run`; any
  hand-edit of `.plan.yaml`, source files, or `.ai-cockpit/suggestions/`
  between the `plans run` start and the final `accept_suggestion`;
  any manual `git` operation other than the post-run audit reads in §4.
- `accept_suggestion` itself is the closing human approval, by design
  of §3.2. It is run after the gate clock has stopped — it is not part
  of the wall-time or cost budget and is not a Q4 (3) violation.

## 6. File budget (queue row #5)

This contract: 2 files / ≤350 net LOC.

- `docs/B_5_CONTRACT.md` (this file, new).
- `docs/ROADMAP.md` (one §B.5 paragraph replaces the old stub and
  points at this contract).

No source under `src/`, no test, no fixture, no workflow YAML.

The gate run itself (§4) generates `docs/V0_4_EXIT_EVIDENCE.md` —
that is a separate, operator-authored PR after the gate run, not
part of this contract's budget.

The B.3 cost dashboard contract (queue item #6) and implementation
(queue item #7) are separately budgeted in their own contract files
and are not part of B.5's LOC count.

## 7. Threat model

| Threat | Mitigation |
| --- | --- |
| Operator runs gate, reports "looks fine", forgets evidence file | §4 explicitly requires `docs/V0_4_EXIT_EVIDENCE.md`. PR review by the user is the gate. Without the evidence PR merged to master, v0.4 is not declared done — full stop. |
| Cost reading is gamed by selecting a tiny window | B.3 contract (queue #6) pins `ai-cockpit cost` to the checkpoint-DB metrics aggregator and a `--since` argument; the gate-run uses `--since today`, computed at run time, and the raw checkpoint DB rows are archived alongside the cost number. Tampering is visible. |
| Wall-time gamed by pre-warming caches | The gate run starts from a clean `examples/broken_calc/` working tree and a clean LLM-provider session. `time` wraps the single `plans run` invocation; cache pre-warm is a §4 violation. |
| Reviewer fooled by worker self-report | §9 invariant: anti-deception tests 1–5 must be green on the gate-run HEAD. Test #3 specifically pins that `coder_result` is byte-absent from the reviewer prompt. B.10d added the same pin for the Cursor reviewer backend. |
| Cursor bonus path leaks past the optional boundary | Q3 is explicit: cursor path failing cost ≤ $1 is logged, not gate-failing. Evidence doc must label the two runs separately so the reader cannot confuse them. |
| Hidden human intervention | §5 counting rules are exhaustive; if an undefined operator action arises, the operator must STOP and OQ before continuing. Evidence doc requires a verbatim shell transcript, which makes hidden interventions visible. |
| Real-LLM call escapes cron VM | Hard rule §3.5: cron never runs the gate. Only the operator runs the gate on their own machine with their own keys. The cron VM has no production keys configured. |
| Memory suggestion is fabricated | The memory pipeline only emits suggestions backed by recorded run state in the checkpoint DB; the suggestion's `created_at` and the linked checkpoint row both have to align with the gate run window. Evidence doc archives the suggestion JSON unmodified. |
| §12 boundary crossed during the gate run | Q5 names the exclusions byte-for-byte. Any new flag or behavior observed during the gate that touches a §12 area is a STOP+OQ, not a "small fix and continue". |

## 8. DoD — what "B.5 contract done" vs "v0.4 gate done"

B.5 contract is **done** (this gate, queue item #5) when:

1. `docs/B_5_CONTRACT.md` (this file) is merged to master.
2. `docs/ROADMAP.md` §B.5 stub is replaced with a pointer to this
   contract plus a one-line summary of Q4's four metrics.
3. Pre-push 4 checks pass: `pytest`, `ruff check .`, `mypy .`,
   `ai-cockpit "smoke b5-contract" --max-loops 1 --dry-run --llm none
   --no-checkpoint`.

v0.4 gate is **done** (separate, operator-authored milestone) when:

1. A real-LLM E2E run on `examples/broken_calc` is captured in
   `docs/V0_4_EXIT_EVIDENCE.md` and merged to master.
2. All four Q4 metrics observably hold for that run (or the Cursor
   bonus row is labelled and excluded per Q3).
3. The §9 anti-deception suite (5 tests) plus the new v0.4 tests
   (≥10) plus the existing test count baseline are all green on
   the post-run master tip.
4. ROADMAP and `V0_3_STATUS.md` flip to a `v0.4 GATE PASSED` header,
   and a v0.5 plan is opened.

## 9. Out of scope for B.5 (do not let scope creep in)

- This contract does not add new tests. Test additions live with the
  components they cover (e.g., new v0.4 tests are added by the gates
  that introduce new behavior between now and the gate run).
- This contract does not change CLI surface. The §4 procedure uses
  commands that already exist on master after queue items #1, #2,
  and #7 land (B.3's `ai-cockpit cost`).
- This contract does not declare any v0.5 features. Q5 explicitly
  defers cost auto-optimization, prompt auto-tuning, multi-repo,
  browser automation, and real-LLM-budget auto-expansion to v0.5+
  as separate gates; v0.5 scope authoring happens after the v0.4
  gate passes.
- This contract does not change spec §12. The Q5 exclusion list is
  policy, not boundary erosion.

## 10. Rollback plan

If the v0.4 gate run repeatedly fails despite this contract being
honored:

1. Do not relax Q4 numerics. Cost > $1 means the loop is too
   expensive — fix the loop, not the threshold.
2. Do not split the gate into "aider-only good enough, ship". The
   Q1-Q4 definition is the v0.4 product claim. Splitting equals
   shipping a weaker product under the v0.4 label.
3. Open a follow-up Section A or Section B gate for the specific
   subsystem that failed (e.g., "planner produces unrunnable
   slices on `examples/broken_calc`" becomes a planner-prompt
   audit gate).
4. The contract itself (this file) is immutable for the 72h window;
   amendments require a fresh user-locked decision.

## 11. Authorization & operating rhythm

Per the 2026-05-17 03:57 UTC user-locked authorization:

1. **Contract first.** This document and the matching `docs/ROADMAP.md`
   §B.5 paragraph are the only B.5 deliverables of the current cron
   tick (queue item #5).
2. **B.3 next.** Queue item #6 (B.3 contract) and queue item #7
   (B.3 implementation, the `ai-cockpit cost` subcommand) land on
   subsequent ticks because Q4 metric (1) reads from the B.3
   dashboard.
3. **Operator runs the gate.** Cron never runs the v0.4 exit gate.
   The user (or a human operator under user supervision) executes
   §4 with their own LLM credentials on their own machine.
4. **Evidence PR.** The operator opens a PR that adds
   `docs/V0_4_EXIT_EVIDENCE.md`. That PR is reviewed by the user;
   cron may comment on validation status only.
5. **Declaration.** Once the evidence PR merges and §8 v0.4-gate
   conditions hold, the user (not cron) flips `V0_3_STATUS.md` to
   `v0.4 GATE PASSED` and authors the v0.5 contract.

Until step 3 happens, this file is reference material only. The
project's source tree is untouched by B.5.

## 15. Open-gate protocol

B.5 is specified but the actual gate run is not open for cron.

Open-gate sequence (user-issued, in user message, not via PR or
commit signal):

```text
open-gate B.5 contract               # already implicitly granted by the
                                     # 2026-05-17 prompt body; this PR
                                     # is the deliverable.
open-gate B.5 exit run               # human-only; cron must reject if
                                     # it sees this in a non-user
                                     # channel.
```

Each step requires an explicit user instruction. Opening "B.5
contract" does not implicitly open "B.5 exit run". Opening "B.5 exit
run" does not implicitly open any v0.5 work; v0.5 begins with a
separate contract following the same pattern.
