# v0.4 exit-gate evidence (template — operator fills in)

Status: **template only.** No exit-gate run has been recorded yet.
The operator (a human) runs `scripts/v0_4_exit_gate.sh` against an
`ai-cockpit` checkout on master with real LLM credentials and pastes
the resulting metrics into the sections below. Cron MUST NOT fill
this file (B.5 contract §11 + AUTOMATION_PROMPT.md §3.5).

## Run identity

| field             | value                                                |
| ----------------- | ---------------------------------------------------- |
| operator          | <github handle>                                      |
| run_started_utc   | YYYY-MM-DDTHH:MM:SSZ                                 |
| run_finished_utc  | YYYY-MM-DDTHH:MM:SSZ                                 |
| master_tip_sha    | `<short sha at gate start>`                          |
| target_repo       | `examples/broken_calc` (or other)                    |
| worker            | `aider` (gate-blocking) / `cursor` (bonus)           |
| llm_provider      | `anthropic` / `openai` / `<other>`                   |
| model_name        | `<exact model string from cost output>`              |

## Q4 hard metrics (all four must hold AND-style for aider path)

| # | metric                                  | cap        | observed | pass? |
| - | --------------------------------------- | ---------- | -------- | ----- |
| 1 | total cost (USD)                        | ≤ 1.00     | $        | yes/no |
| 2 | wall-time (seconds)                     | ≤ 900      |          | yes/no |
| 3 | human interventions mid-loop            | 0          |          | yes/no |
| 4 | top-level pytest pass / total           | all green  |  /       | yes/no |
| 4 | broken_calc pytest pass / total         | all green  |  /       | yes/no |
| 4 | §9 anti-deception suite (5 tests) green | all green  |  / 5     | yes/no |

`pytest` baseline is **whatever master pytest yields at gate-run
time**, not the prompt-body 236. See B.5 contract §3 Q4 rationale
and OQ-22 in `V0_3_STATUS.md`.

## Q1 capability trace (real-LLM E2E loop)

| stage      | evidence                                                                |
| ---------- | ----------------------------------------------------------------------- |
| plan       | `docs/plans/<plan_id>.plan.yaml` (paste tip line)                       |
| plans run  | command, exit_code, elapsed                                             |
| verifier   | exit_code of test command(s) the planner emitted                        |
| reviewer   | `passed`, `risk_level`, `notes` from final review                       |
| memory     | suggestion ids written + ids reached `done` via `memory accept`         |
| commit(s)  | `git log --oneline` since the gate started — must include real edits   |

## Cursor bonus path (optional, per Q3)

Cursor path runs the same scenario again with `--worker cursor`.
If it exceeds the $1 cap, that is **logged here, not gate-failing**;
the gate's pass/fail is judged on the aider path alone.

| field       | value |
| ----------- | ----- |
| cost (USD)  |       |
| wall-time   |       |
| notes       |       |

## Reviewer §9 audit trail (must be empty for gate to pass)

Paste below the reviewer's final JSON (system prompt + user
evidence dict are NOT to be pasted — those are public). Reviewer
must show `passed: true` AND no `coder_result`-like substring in
any notes / suggested_fix.

```json
{ ... }
```

## OQ findings (informational; do not block gate)

- record any unexpected behaviour or follow-up items here.
- a finding that aligns with §9 or a permanent §12 boundary is a
  **STOP-and-OQ event** and disqualifies the gate run.

## Reset for a re-run

```bash
cd examples/broken_calc
git checkout -- calc.py
rm -rf .aider*
python -m pytest -q   # must fail again before re-running the script
```

## See also

- `scripts/v0_4_exit_gate.sh` — the runbook this template pairs with.
- `docs/B_5_CONTRACT.md` §3 (Q1–Q5), §4 (procedure), §11 (authorization).
- `docs/B_3_CONTRACT.md` §3 (cost dashboard keys + readout format).
- `examples/broken_calc/README.md` — fixture description and reset steps.
