# V0.5 Row #3 — `prompt-coverage` contract (v0.1, LOCKED)

Status: **contract locked.** User authorised the Q-answers on
2026-05-17 15:08 UTC, including the cost-not-a-constraint
modifier on Q1 (**both A AND B**, A no longer opt-in only).
Implementation gate double-blocked on V0_4 evidence + explicit
`open-gate v0.5-row-3-impl` signal.

> Pure-documentation deliverable: 2 files / ≤350 net LOC. No code
> under `src/`, no tests touched.

## 1. Why

The 2026-05-17 Bug F chase (PRs #80 → #81 → #82 → #83) burnt 4
PRs on one root issue. Each PR fixed one layer of a 5-layer
prompt-plumbing chain:

```
CLI flag (--worker)
  → Click handler
    → run_interactive_planner kwarg
      → PlannerRequest.worker_name
        → BuiltinPlannerBackend
          → build_planner_messages(worker_hints=...)
            → format_worker_hints_block (≤80-char clip)
              → LLM input
```

Each PR's mock tests passed. The next operator real-LLM run
surfaced the next layer's failure. The structural cause: **mock-
only CI cannot exercise the end-to-end string the LLM actually
receives**, so PR #80's well-intentioned 153-char `human_summary`
that got clipped to 80-chars-without-the-example wasn't caught
until PR #81. PR #82's "the wire is connected" wasn't caught
until the user ran v0.4 attempt 7.

Row #3 closes that gap with two complementary mitigations:

1. **Golden-prompt CI (B)** — every PR that touches the prompt
   builder, B.2 catalog, B.4 override loader, or any related
   layer regenerates a set of canned planner-prompt dumps. The
   diff against the committed golden files MUST be human-reviewed
   in the PR. PR #80's 153→80-clip would have shown up as "the
   example string disappeared from the golden file" in PR review.

2. **Nightly real-LLM probe (A)** — once per night on the cron VM
   (now possible since cost is not a constraint per user statement
   2026-05-17 15:05 UTC), call the planner with a canned scenario
   set, assert structural properties of the reply (no
   `<cwd_basename>/` prefix in `test_commands`, etc.), log per-run
   row into `docs/V0_5_PROBE_LOG.md`. Catches "the LLM
   misinterprets even the corrected prompt" before an operator
   runs the v0.4/v0.5 exit gate.

Together: B catches drift before merge, A catches LLM-prior-
overriding-prompt before the operator does.

## 2. Hard invariants (cannot be overridden at implementation time)

| Invariant | Source | How row #3 honours it |
| --- | --- | --- |
| §9 evidence-only reviewer | spec §9 | Golden files include reviewer prompt dumps; CI assertion includes "no `coder_result` substring leaks". The 5-test anti-deception suite stays byte-identical and additionally extends to assert that every new golden file is `coder_result`-free. |
| §3.5 no real LLM in CI | AUTOMATION_PROMPT | Sub-option B (golden prompts) is mock-only — the "real" LLM call is replaced by `_ScriptedLLM` capturing the prompt and writing it to disk. Sub-option A (nightly probe) runs OUTSIDE CI — it's a cron VM scheduled job triggered by the cron-pr-automation, NOT part of any PR validate workflow. |
| §3.2 memory write approval | hard rule §3.2 | `docs/V0_5_PROBE_LOG.md` is a normal documentation file under `docs/`, NOT under `.ai-cockpit/memory/`. Probe results are evidence, not memory. |
| §12 permanent boundaries | spec §12 | No daemon, no UI, no swarm. The probe is a one-shot cron job, not a long-running service. |
| Cost monitoring | row #3 §3 Q2 | Probe has hard caps (\$2/night, \$15/week) implemented by reading `ai-cockpit cost --since today` BEFORE spending. Skips if `today's spend ≥ $0.40` (per row #3 Q2 cron rec). |
| Operator review of golden diffs is mandatory | row #3 §3 Q3 | CI workflow fails if `git diff tests/prompts/golden/` is non-empty after running the dumper but the PR description doesn't acknowledge the diff. (Mechanism: PR template field; reviewer asserts manually if template path is too brittle.) |
| ≤8 files / ≤400 net LOC per PR | EXECUTION_RULES | Contract (this PR): 2 files / ≤350. Implementation: ≤6 / ≤300. |

## 3. Resolved decisions (user-locked 2026-05-17 15:08 UTC)

| # | Question | User decision | Rationale |
| --- | --- | --- | --- |
| Q1 | A only / B only / both? | **Both.** A is now default-on, not opt-in (user said cost is not a constraint 2026-05-17 15:05 UTC). | B catches prompt drift in PR review (cheap, deterministic). A catches LLM-prior-overrides-prompt before the operator does (the exact Bug F failure mode). Both are needed for full coverage; B alone misses Bug F-class issues, A alone is reactive instead of preventive. |
| Q2 | A budget? | **\$2/night nominal, \$15/week cap, skip if today's `ai-cockpit cost --since today ≥ $0.40`** (refines cron's pre-cost-relaxed \$0.50/night). | At \$2/night × 7 = \$14/week, room for the \$15 cap. The "skip if already spent" rule prevents the nightly probe + operator-driven v0.4/v0.5 exit-gate runs from over-spending in a single day. |
| Q3 | B: PR review of golden diffs accepted as process friction? | **Yes.** Reviewer's job in any prompt-touching PR is to read the `tests/prompts/golden/*.txt` diff alongside the source diff. | The friction is the point — it forces a human eye on the actual string the LLM sees. Without it, drift is invisible until a real run. |
| Q4 | Canned scenario set | **5 scenarios**: (a) `broken_calc` bug-fix with `--worker aider`, (b) new-feature with `--worker aider` (canned new-feature fixture under `examples/`), (c) refactor with `--worker aider`, (d) `broken_calc` bug-fix with `--worker cursor`, (e) refactor with `--worker cursor`. | Covers both workers, both worker-quirk shapes (B.2 aider.gitignore + cursor.workspace_scan), and three task types (bug-fix, new-feature, refactor). Scenario (b) requires a new tiny fixture under `examples/`; (c) and (e) require canned plan inputs but no fixture changes. |

## 4. Sub-option B — golden-prompt CI

### 4.1 Dumper

`scripts/dump_prompts.py` (new):

```python
"""Render planner + reviewer prompts for the canned scenarios and
write them to tests/prompts/golden/<scenario>.txt.

Run by CI as `python scripts/dump_prompts.py --check`, which
re-renders + fails if `git diff tests/prompts/golden/` is non-
empty. Run by developers as `python scripts/dump_prompts.py`
(no flag) to regenerate after intentional prompt changes.
"""
```

Five canned scenarios per Q4. Each produces one
`tests/prompts/golden/<scenario>.txt` file containing the
serialised `system + "\n" + user` strings as the
`_ScriptedLLM` captured them. Files are checked into git.

### 4.2 CI workflow

`.github/workflows/validate.yml` gains a step:

```yaml
- name: prompt-coverage golden files
  run: |
    source .venv/bin/activate
    python scripts/dump_prompts.py --check
```

`--check` mode exits non-zero if the regenerated files differ
from the checked-in ones. Reviewer then must either approve the
diff (commit the new versions) or fix the prompt builder.

### 4.3 Tests

`tests/test_prompts_golden.py` (new): structural assertions on
the golden files (each contains the expected scenario sentinel
substring, no `coder_result` leaks, etc.). Run on every PR
regardless of whether any prompt source touched.

## 5. Sub-option A — nightly real-LLM probe

### 5.1 Script

`scripts/v0_5_real_llm_probe.sh` (new):

```bash
#!/usr/bin/env bash
# Nightly probe: real-LLM smoke against 5 canned scenarios.
# Asserts STRUCTURAL properties of replies (no $cwd_basename/
# prefix in test_commands, no `coder_result` substring in any
# reviewer reply, etc.). Writes one row per run into
# docs/V0_5_PROBE_LOG.md. Caps cost per row #3 Q2.
#
# Trigger: nightly cron on the same Cloud Agent VM as the
# existing cron-pr-automation. NOT triggered by any PR push.
```

### 5.2 Budget gate (precondition before LLM calls)

```bash
TODAY_SPEND=$(ai-cockpit cost --since today --format json | jq -r '.total_usd // 0')
if [[ $(echo "$TODAY_SPEND >= 0.40" | bc) -eq 1 ]]; then
  echo "skip: today's spend $TODAY_SPEND >= 0.40; preserving budget"
  exit 0
fi

WEEK_SPEND=$(ai-cockpit cost --since "7 days ago" --format json | jq -r '.total_usd // 0')
if [[ $(echo "$WEEK_SPEND >= 15.00" | bc) -eq 1 ]]; then
  echo "skip: week's spend $WEEK_SPEND >= 15.00; cap reached"
  exit 0
fi
```

### 5.3 Probe assertions

Per scenario, after the planner returns:

1. Each `slice.test_commands[*]` token — no `<cwd_basename>/`
   prefix (Bug F regression sentinel).
2. `acceptance_criteria` does NOT contain the literal phrase
   "from the repo root" when `--root` is a subdirectory
   (Bug F prior-overrides-prompt signal).
3. Reply parses as valid JSON matching `PLAN_DRAFT_SCHEMA`.

Any assertion failure produces a PROBE-FAILED row in the log,
exits non-zero. cron-pr-automation can pick that up as a "real-
LLM drift" alert.

### 5.4 Probe log file

`docs/V0_5_PROBE_LOG.md` (new): markdown table, one row per
probe run, columns: `date_utc`, `scenario_passed`,
`scenario_failed`, `cost_usd`, `notes`. Operator can grep this
to spot regressions over time.

## 6. CLI surface

**No new CLI flags.** Both sub-options are CI workflow / nightly
cron jobs; the existing `ai-cockpit cost` subcommand (B.3) is
reused for the budget gate.

## 7. File budget

**Contract (this PR):** 2 files / ≤350 net LOC.

- `docs/V0_5_ROW_3_PROMPT_COVERAGE_CONTRACT.md` (new — this).
- `docs/V0_5_ROADMAP.md` (mod — flip row #3 status to "CONTRACT
  LOCKED").

**Implementation (separate PR, NOT pre-authorised):** ≤6 files /
≤300 net LOC.

- `scripts/dump_prompts.py` (new — dumper for B; ~80 LOC).
- `scripts/v0_5_real_llm_probe.sh` (new — nightly probe runner
  for A; ~80 LOC).
- `tests/prompts/golden/<5 scenarios>.txt` (new — committed
  golden files; not LOC-counted as they're data, not code).
- `tests/test_prompts_golden.py` (new — structural assertions
  on golden files; ~40 LOC).
- `docs/V0_5_PROBE_LOG.md` (new — empty header table for A
  output; ~15 LOC).
- `.github/workflows/validate.yml` (mod — add `python
  scripts/dump_prompts.py --check` step; ~10 LOC).

Plus optionally one tiny fixture: `examples/new_feature_seed/`
(for scenario (b)). If adding pushes file count over 6, scenario
(b) deferred to row #3b.

## 8. Threat model

| Threat | Mitigation |
| --- | --- |
| Real-LLM probe runs without budget guard, spends $$ | Hard caps in script (§5.2). `ai-cockpit cost --since today` is read BEFORE any LLM call. Without `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` set, the LLM build returns None and the probe skips with a clear log entry. |
| Probe creds leak via probe log | `docs/V0_5_PROBE_LOG.md` carries only structural booleans + dollar amounts + a notes string. NEVER prompt content, NEVER LLM reply content. The script does NOT log raw responses. |
| Golden file diff is approved without anyone reading it | Same risk as any other test file. Mitigation is process (reviewer culture), not technical. The friction of HAVING to commit the diff makes accidental "rubber stamp" harder than accidental drift. |
| Golden file rot — scenarios become obsolete as prompt evolves | Each scenario is small (≤2KB after canned fixture). Adding/removing scenarios is its own row-#3b gate to prevent drift. |
| Probe assertion #2 ("no 'from the repo root'") is brittle to prompt phrasing changes | Acceptable. If the planner LLM phrases the same idea differently, that itself is drift worth reviewing. Assertion can be relaxed in a follow-up gate IF real evidence shows false positives. |
| Probe runs on a Cloud Agent VM that the operator can't see | Probe writes to `docs/V0_5_PROBE_LOG.md` via a normal PR (one PR per probe run, auto-merged by cursor-pr-automation), so operator sees results in git history. NOT pushed silently. |
| §3.5 violation: real-LLM call ends up in CI | The probe script lives in `scripts/`, NOT under `.github/workflows/`. CI workflows never invoke it. Belt-and-suspenders: the script's first line refuses to run if `CI=true` or `GITHUB_ACTIONS=true` env vars are set. |
| Golden files include sensitive paths (`/home/user/...`) | Dumper writes path placeholders (e.g. `<PROJECT_ROOT>`) by replacing the resolved `--root` with a literal sentinel before writing. Path text is functionally equivalent but doesn't leak operator filesystem layout. |

## 9. DoD

**Contract done (this PR) when:**

1. `docs/V0_5_ROW_3_PROMPT_COVERAGE_CONTRACT.md` merged.
2. `docs/V0_5_ROADMAP.md` row #3 entry points here by filename.
3. Pre-push 4 checks pass.
4. No source / test touched.

**Implementation done (future, separate PR after user signal) when:**

1. `scripts/dump_prompts.py` ships and produces 5 golden files.
2. `tests/prompts/golden/*.txt` committed.
3. `tests/test_prompts_golden.py` covers structural assertions.
4. CI workflow runs the dumper in `--check` mode.
5. `scripts/v0_5_real_llm_probe.sh` ships with budget gate + 3
   assertions per §5.3. Refuses to run under `CI=true`.
6. `docs/V0_5_PROBE_LOG.md` exists with header table only
   (operator-writable, cron-PR-appendable).
7. Optional: `examples/new_feature_seed/` fixture for scenario
   (b); if not, row #3b gates it.
8. 5-test anti-deception suite stays byte-identical and green.
9. Pre-push 4 checks pass; ≤6 / ≤300 budget respected.

## 10. Out of scope for row #3

- No CI workflow that runs the real-LLM probe (§3.5 hard rule).
- No alerting beyond the log file (no email, no Slack — §12).
- No probe of B.10 cursor backend in nightly schedule (cursor is
  ~19k input tokens/turn; would burn the \$2/night cap in 2
  scenarios). Cursor coverage is the operator-driven v0.4 / v0.5
  exit-gate runs.
- No probe of arbitrary user prompts; the scenarios are canned.
- No fuzz testing.
- No auto-fix on probe failure; failures are reported, fixes are
  separate PRs.

## 11. Rollback

If the implementation PR proves harmful:

1. Revert the implementation PR.
2. CI workflow reverts to pre-row-#3 (no golden check step).
3. Probe script reverts (was opt-in to begin with via the
   nightly cron schedule).
4. Probe log file remains in git history as evidence; can be
   left or deleted.

## 12. Authorisation & operating rhythm

Per the 2026-05-17 15:08 UTC user-locked authorisation:

1. **Contract draft only.** This PR ships this file + ROADMAP
   pointer.
2. **Implementation gated by Phase 0 + explicit
   `open-gate v0.5-row-3-impl`**.
3. **Probe activation is a separate sub-gate.** Even after row
   #3 impl ships, the nightly cron schedule for sub-option A
   needs explicit operator activation (the script will sit
   uninvoked until then). This is intentional: the operator
   decides when to start spending real-LLM budget on probes.

## 15. Open-gate protocol

```text
open-gate v0.5-row-3-contract           # granted 2026-05-17 15:08 UTC;
                                        # this PR is the deliverable.
open-gate v0.5-row-3-impl               # NOT granted — requires V0_4
                                        # evidence + explicit signal.
open-gate v0.5-row-3-probe-activate     # NOT granted — operator
                                        # must explicitly say "start
                                        # the nightly probe" AFTER
                                        # impl PR merges.
open-gate v0.5-row-3-real-llm-in-CI     # NEVER GRANTED — \xc2\xa73.5
                                        # hard rule.
open-gate v0.5-row-3-alerting           # NEVER GRANTED in v0.5 —
                                        # \xc2\xa712 boundary on
                                        # auto-outbound.
open-gate v0.5-row-3-cursor-nightly     # NEVER GRANTED in v0.5 —
                                        # cursor's per-turn token
                                        # cost too high for nightly
                                        # cadence under any budget cap.
```

A future `open-gate v0.5-row-3-impl` must (a) confirm V0_4
evidence on master AND (b) accept Q1+Q2+Q3+Q4 as locked.
`open-gate v0.5-row-3-probe-activate` (separate signal) is
required to start the nightly cron AFTER impl PR ships.
