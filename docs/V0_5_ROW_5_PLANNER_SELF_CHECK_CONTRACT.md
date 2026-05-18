# V0.5 Row #5 — `planner-self-check` contract (v0.1, LOCKED)

Status: **contract locked.** User authorised the Q-answers on
2026-05-17 15:08 UTC ("采纳所有 cron 推荐"). Implementation gate
double-blocked on `docs/V0_4_EXIT_EVIDENCE.md` + explicit user
signal.

> Pure-documentation deliverable: 2 files / ≤350 net LOC. No code
> under `src/`, no tests touched.

## 1. Why

PR #83 shipped a three-layer defence for Bug F (verifier cwd
path-doubling): Layer 1 (B.2 quirk hint), Layer 2 (literal cwd
context block in the planner prompt), Layer 3 (verifier runtime
detection that injects a hint into stderr **after** the failed
command runs). Layer 3 is reactive — by the time it fires, the
operator has already spent worker tokens, and the failure looks
like a verification failure rather than a planner authoring bug.

Row #5 adds a **deterministic Python lint** that runs on the
planner output **before** the coder node starts. The lint catches
the same class of issues at the cheapest possible point in the
graph: zero extra LLM tokens, sub-millisecond runtime, and the
operator-visible message names "the planner output X which looks
suspicious" rather than "the verifier exited with code Y after the
worker spent Z tokens".

This is belt-and-suspenders by design. PR #83 already shipped two
layers of defence; row #5 closes the prevention/detection
asymmetry by catching the planner-authoring bug at planner-output
time, not at verifier-failure time.

## 2. Hard invariants (cannot be overridden at implementation time)

These override §3, override "small extra improvement" temptation
at implementation time, and override any judgement call inside
the future implementation PR. If the implementation must violate
one, the gate stays CLOSED and a new contract amendment is
required.

| Invariant | Source | How row #5 honours it |
| --- | --- | --- |
| §9 evidence-only reviewer | spec §9 | Lints fire in the planner→coder path, never reach the reviewer prompt. The 5-test anti-deception suite stays byte-identical. |
| No second LLM call | row #5 §3 Q-recommendation | Lints are pure Python (shlex, str matching, integer comparisons). Zero token cost; deterministic. |
| Default warn, not block | user answer to §3 Q2 | Default behaviour MUST be `click.echo(warning, err=True)` then proceed to coder. Only `--strict-planner` flag converts to `click.UsageError`. |
| Lints are catalogable | row #5 §3 Q1 | The initial 3 lints ship as named Python functions in `src/ai_cockpit/nodes/planner_self_check.py`, callable individually. Adding a 4th lint is a small follow-up gate, not a rewrite. |
| §3.2 memory write approval | hard rule §3.2 | No memory write. Lint catalogue is static Python source. |
| §12 permanent boundaries | spec §12 | No daemon, no UI. Local Python check, runs in-process. |
| ≤8 files / ≤400 net LOC per PR | EXECUTION_RULES | Contract (this PR): 2 files / ≤350. Implementation: ≤4 / ≤200. |

## 3. Resolved decisions (user-locked 2026-05-17 15:08 UTC)

| # | Question | User decision | Rationale |
| --- | --- | --- | --- |
| Q1 | Initial lint set | **3 lints**: (a) cwd-doubling — any test_command argv token equals or starts with `project_root.name + '/'`; (b) brittle aider criteria — any `dod` bullet matches `/no other files modified/i` or `/exact \d+-file diff/i` when `worker_name == "aider"`; (c) budget overrun — `files_budget * loc_budget > workflow.defaults.files_loc_product`. Adding more lints later is a row-#5b gate. | (a) directly addresses Bug F at the planner side, before tokens are spent; (b) matches the B.2 `aider.gitignore` quirk at runtime in case the prompt-side hint was ignored; (c) cheap sanity check, fires on copy-paste-from-larger-plan mistakes. |
| Q2 | Warn or block by default? | **Warn**. Default `--no-strict-planner`. New flag `--strict-planner` (on `plans run` only) escalates every warn into `click.UsageError`. | Warn-default lets operators experiment without being trapped by an over-cautious lint. `--strict-planner` is the CI / cron / v0.5-exit-gate option. Symmetric with B.4's `_load_prompt_override` fail-closed pattern when the operator explicitly opts in. |
| Q3 | Where do warnings surface? | **stderr + replan context** (the latter only if row #1 ships). For v0.5 phase-1 (this row may land before row #1's implementation), only stderr. After row #1 implementation merges, lint warnings auto-flow into the `replan` planner's input context as a structured `previous_self_check_warnings: list[str]` field. | stderr is the irreducible surface (operator always sees it). Replan context lets the next planner pass act on the warning automatically, completing the prevent→detect→correct loop. |

## 4. Lint catalogue (initial, per Q1)

### 4.1 `lint_cwd_doubling(slice, project_root) -> list[str]`

For each `cmd in slice.test_commands`:
- Parse with `shlex.split(cmd)`. If parse fails → skip silently
  (operator-visible cmd, they'll see the error elsewhere).
- For each token: if `token == project_root.name` OR
  `token.startswith(project_root.name + "/")`, emit a warning:
  ```
  planner self-check: slice '<slice.id>' test_command '<cmd>'
  contains token '<token>' which prefixes the verifier cwd basename
  '<project_root.name>'. Verifier runs the command with cwd=--root;
  this token will be relative to --root, not to repo root. Drop the
  prefix (e.g. 'pytest -v' not 'pytest <project_root.name>/ -v').
  ```

### 4.2 `lint_brittle_aider_criteria(slice, worker_name) -> list[str]`

Only fires when `worker_name == "aider"`. For each bullet in
`slice.dod`:
- If matches `re.search(r"no other files modified", bullet, re.I)`
  OR `re.search(r"exact[ -]?\d+[ -]?file diff", bullet, re.I)`:
  emit warning naming the bullet text + the B.2 quirk
  (`aider.gitignore`).

### 4.3 `lint_budget_overrun(slice, workflow_defaults) -> list[str]`

If `slice.files_budget * slice.loc_budget > workflow.defaults
.files_loc_product` (default workflow product = 8 × 400 = 3200):
emit warning naming the product and the workflow default.

If no `workflow.defaults.files_loc_product` is configured: skip
the lint (don't infer a default).

## 5. CLI surface

New flag on `ai-cockpit plans run` only (NOT on `ai-cockpit run`
top-level, NOT on `ai-cockpit plan` REPL):

```text
--strict-planner / --no-strict-planner
    Default: --no-strict-planner (warn-only on lint hits).
    With --strict-planner, any non-empty lint result raises
    click.UsageError before coder runs. Exit non-zero, no LLM
    call made.
```

Rationale for `plans run`-only: the REPL `ai-cockpit plan` is
interactive — lints there are noise during exploration. `plans
run` is the execution surface where strict mode matters
(CI, cron, v0.5 exit gate).

## 6. File budget

**Contract (this PR):** 2 files / ≤350 net LOC.

- `docs/V0_5_ROW_5_PLANNER_SELF_CHECK_CONTRACT.md` (new — this).
- `docs/V0_5_ROADMAP.md` (mod — flip row #5 status to "CONTRACT
  LOCKED").

**Implementation (separate PR, NOT pre-authorised):** ≤4 files /
≤200 net LOC.

- `src/ai_cockpit/nodes/planner_self_check.py` (new — 3 lint
  functions + a `run_all_lints(slice, ctx) -> list[str]`
  aggregator; ~90 LOC).
- `src/ai_cockpit/graph.py` (mod — insert `planner_self_check`
  node between planner and coder; route warn → coder, error →
  raise; ~25 LOC).
- `src/ai_cockpit/cli.py` (mod — `--strict-planner` flag on
  `plans run`, thread to graph; ~20 LOC).
- `tests/test_planner_self_check.py` (new — per-lint unit tests
  + integration test asserting warn-by-default vs strict-by-flag;
  ~60 LOC).

## 7. Threat model

| Threat | Mitigation |
| --- | --- |
| Lint false-positive blocks a legitimate plan (e.g. operator deliberately wants `pytest tests/ -v` from repo root with `--root .`) | Warn-by-default. `--strict-planner` is opt-in. False-positive in strict mode is a contract amendment trigger, not silent suppression. |
| Lint catalogue grows unbounded and slows planner→coder | Each lint is pure Python, microsecond-scale. Catalogue cap: ≤6 lints in v0.5 (one slot per worker bucket × 2 plus 4 generic). Adding lint #7 requires a separate gate that justifies the budget. |
| Lint reaches reviewer prompt (§9 leak) | Lint output stays in `TaskState.planner_self_check_warnings: list[str]` (`total=False`). The reviewer-evidence dict (`build_reviewer_evidence`) does not extract this field. A dedicated test asserts the reviewer prompt contains none of the lint warning strings even when warnings exist. |
| `--strict-planner` blocks first attempt but operator wants to proceed | Operator can re-run without `--strict-planner`. The flag is per-invocation, not persisted. |
| Lint catches Bug F at the planner side, masking the prompt-engineering issue we should fix | Lint warnings list the **prompt-side** quirks they expect (e.g. "B.2 quirk verifier.test_command_path_relative_to_root should have prevented this"). The warning text itself documents that this is a backstop, not the primary fix. |
| Workflow defaults change and the budget lint stops firing | Lint reads workflow defaults at run time, not at planner time. If the operator picks a workflow with no `files_loc_product`, the lint silently skips (per §4.3). |

## 8. DoD

**Contract done (this PR) when:**

1. `docs/V0_5_ROW_5_PLANNER_SELF_CHECK_CONTRACT.md` is merged.
2. `docs/V0_5_ROADMAP.md` row #5 entry points here by filename.
3. Pre-push 4 checks pass: `pytest`, `ruff check .`, `mypy .`,
   `ai-cockpit "smoke v0_5-row-5-contract" --max-loops 1
   --dry-run --llm none --no-checkpoint`.
4. No source under `src/` modified; no test added/removed.

**Implementation done (future, separate PR after user signal) when:**

1. `src/ai_cockpit/nodes/planner_self_check.py` ships the 3
   named lints + `run_all_lints` aggregator.
2. `build_graph` inserts the new node between `planner` and
   `coder`; node returns `{planner_self_check_warnings: [...]}`
   into `TaskState`.
3. CLI `plans run --strict-planner` raises `click.UsageError`
   with the joined warning text if any warning fires; without
   the flag, the warnings print to stderr and the run proceeds.
4. New `tests/test_planner_self_check.py` covers all 3 lints
   (positive + negative case each), the warn-vs-strict CLI
   behaviour, and the §9-isolation test (reviewer prompt does
   not carry warning substrings even when `TaskState
   .planner_self_check_warnings` is non-empty).
5. 5-test anti-deception suite remains byte-identical and green.
6. Pre-push 4 checks pass; ≤4 / ≤200 budget respected.

## 9. Out of scope for row #5

- No LLM-based self-critique. Pure deterministic Python only.
- No automatic plan rewriting on lint hit; operator decides.
- No environment / external lint surfaces (e.g. checking
  network reachability, dependency versions).
- No lint on `acceptance_criteria` (B.5 contract Q4 said
  criteria stay anchored to user idea; row #5 doesn't second-
  guess them).
- No lint on `worker_name` validity; that's CLI-flag-validation
  territory and already exists.
- No memory persistence of "this lint fired N times" — out of
  v0.5 scope, considered for v0.7+ memory analytics.
- No row #5b (lint catalogue expansion) in this gate. Each new
  lint is its own row-#5b-<N> gate after row #5 ships.

## 10. Rollback

If the implementation PR proves harmful:

1. Revert the implementation PR. Contract (this file) stays as
   historical record.
2. Existing `plans run` invocations continue to work; without
   the new `planner_self_check` node, the graph is exactly
   pre-row-#5 shape.
3. Row #1 (replan) does not break — if row #1 ships first, it
   handles a missing `planner_self_check_warnings` field as
   `[]` (absence is informational).

## 11. Authorisation & operating rhythm

Per the 2026-05-17 15:08 UTC user-locked authorisation:

1. **Contract draft only.** This PR ships this file + ROADMAP
   pointer. No source under `src/` is touched.
2. **Implementation is gated by Phase 0** (V0_4 evidence merged)
   AND explicit `open-gate v0.5-row-5-impl` signal. Cron MUST
   refuse the implementation PR until both hold.
3. **One tick, one gate.** Implementation is one cron tick.

## 15. Open-gate protocol

```text
open-gate v0.5-row-5-contract       # granted 2026-05-17 15:08 UTC;
                                    # this PR is the deliverable.
open-gate v0.5-row-5-impl           # NOT granted — requires
                                    # (a) V0_4 evidence on master AND
                                    # (b) explicit user signal.
open-gate v0.5-row-5b-<lint-name>   # follow-up gate per new lint.
open-gate v0.5-row-5-llm-critic     # NEVER GRANTED — row #5 is
                                    # explicitly deterministic-Python;
                                    # LLM critique is a separate
                                    # contract (and would conflict
                                    # with §3.5 mock-only CI).
open-gate v0.5-row-5-block-default  # NEVER GRANTED — Q2 locked
                                    # "warn default"; flipping it
                                    # requires a contract amendment.
```

A future `open-gate v0.5-row-5-impl` signal must confirm V0_4
evidence is on master AND accept Q1+Q2+Q3 answers as locked.
Without (a), cron stops with an OQ. Without (b), cron treats as
ambiguous and stops with an OQ.
