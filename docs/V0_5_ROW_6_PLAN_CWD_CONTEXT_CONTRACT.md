# V0.5 Row #6 — `plan-cwd-context` contract (v0.1, LOCKED)

Status: **contract locked.** User authorised the Q-answers on
2026-05-17 15:08 UTC ("采纳所有 cron 推荐"). This document is the
implementation gate; a future `open-gate v0.5-row-6-impl` signal
plus a merged `docs/V0_4_EXIT_EVIDENCE.md` are jointly required
before cron drafts the implementation PR.

> Pure-documentation deliverable: 2 files / ≤350 net LOC. No code
> under `src/`, no tests touched.

## 1. Why

The 2026-05-17 v0.4 exit-gate attempts 1–7 surfaced **Bug F**
(verifier cwd path-doubling). One root contributor: the saved
`.plan.yaml` did not record the cwd assumption baked into its
`test_commands`. The plan emitted by `ai-cockpit plan --root
examples/broken_calc` was implicitly anchored to "cwd =
examples/broken_calc" at planning time, but `plans run --root
<other_path>` would silently re-execute the same `test_commands`
in a different cwd, breaking in non-obvious ways.

Row #6 closes the smallest part of that gap: record the assumption
in the plan artefact and warn (NOT block) when a later `plans run`
invocation contradicts it. This is the lowest-blast-radius v0.5
row; it ships before #1/#2/#3/#5 because (a) it's self-contained,
(b) it enables clearer evidence on every subsequent v0.5 row's
real-LLM probe, and (c) it costs ≤4 files / ≤120 LOC.

## 2. Hard invariants (cannot be overridden at implementation time)

These override §3, override "small extra improvement" temptation
at implementation time, and override any judgement call inside
the future implementation PR. If the implementation must violate
one, the gate stays CLOSED and a new contract amendment is
required.

| Invariant | Source | How row #6 honours it |
| --- | --- | --- |
| §9 evidence-only reviewer | spec §9 | `assumed_cwd` is plan-side metadata only; it never reaches `build_reviewer_messages`. The 5-test anti-deception suite stays byte-identical. |
| §3.2 memory write approval | hard rule §3.2 | No memory write. `assumed_cwd` lives only in `.plan.yaml` and in the in-memory `Plan` instance during a run. |
| §12 permanent boundaries | spec §12 | No daemon, no UI, no auto-outbound. Pure local file metadata. |
| Backwards compatibility | EXECUTION_RULES | Pre-row-#6 plans (those merged on master before this gate ships) have no `assumed_cwd` key. Implementation MUST treat absent field as "no assumption recorded; skip the check"; loader MUST NOT raise. |
| Warn, never block | user answer to §3 Q1 | Mismatch is `click.echo(..., err=True)` only, never `raise`. Operator can always proceed. |
| ≤8 files / ≤400 net LOC per PR | EXECUTION_RULES | Contract (this PR): 2 files / ≤350. Implementation (future PR, separate authorisation): ≤4 / ≤120. |

## 3. Resolved decisions (user-locked 2026-05-17 15:08 UTC)

| # | Question | User decision | Rationale |
| --- | --- | --- | --- |
| Q1 | Warn or block on cwd mismatch at `plans run` time? | **Warn only.** `click.echo` to stderr with severity prefix; `plans run` proceeds normally. | Blocking would break operator workflows that legitimately change `--root` (e.g. running the same plan against a sibling checkout). Warning surfaces the risk without trapping the operator. |
| Q2 | Pre-row-#6 plans (no `assumed_cwd` field) — behaviour? | **Silently skip the check.** Loader does not warn or raise on absent field. | Hard-failing on absent field would block every existing `docs/plans/*.plan.yaml`. Silent skip preserves existing behaviour; new plans gain the check automatically. |

## 4. Data model

### 4.1 `Plan` schema change (B.6-compatible)

`src/ai_cockpit/plans/schema.py`:

```python
@dataclass(frozen=True)
class Plan:
    schema_version: int
    plan_id: str
    created_at: str
    idea: str
    acceptance_criteria: list[str]
    slices: list[Slice]
    # NEW — row #6:
    assumed_cwd: str | None = None
```

`assumed_cwd` is the absolute path string (post-`Path.resolve()`)
of the directory the planner was invoked with as `--root`. It is
serialised under the same key in the YAML form.

### 4.2 YAML round-trip example

```yaml
schema_version: 1
plan_id: fix-broken-calc
created_at: '2026-05-17T14:18:13+00:00'
idea: Fix examples/broken_calc so that pytest passes end-to-end
assumed_cwd: /home/user/ai-cockpit/examples/broken_calc   # NEW
acceptance_criteria:
  - All tests under examples/broken_calc pass ...
slices:
  - id: diagnose-and-fix
    ...
```

### 4.3 Validation surface

The loader (`load_plan_from_yaml`) MUST:
- Accept `assumed_cwd` as optional (absent → `None`).
- If present, validate it is a non-empty string. Otherwise raise
  `PlanSchemaError` with the typed reason.
- NOT call `Path(value).exists()` at load time. The path may be
  on a different machine; existence check is irrelevant at load.

The saver (`save_plan_atomic`) MUST:
- If `Plan.assumed_cwd` is not `None`, write it to the YAML.
- If `Plan.assumed_cwd` is `None`, omit the key entirely (don't
  write `assumed_cwd: null`).

## 5. CLI surface

**No new flags.** `ai-cockpit plan` already takes `--root`. Behaviour
changes:

- `ai-cockpit plan --root <path>`: when saving, sets
  `Plan.assumed_cwd = str(Path(path).resolve())`.
- `ai-cockpit plans run --root <path>`: after loading the plan,
  compares `str(Path(--root path).resolve())` to `Plan.assumed_cwd`:
  - if `assumed_cwd is None`: silent (pre-v0.5 plan, Q2 behaviour);
  - if equal: silent (matches);
  - if different: print a single-line warning to stderr like:
    ```
    warning: plan assumed_cwd ('/abs/A') differs from --root
             ('/abs/B'); test_commands in this plan were written
             against the original cwd and may not compose with the
             new --root. Proceeding anyway (warn-only, not blocking).
    ```

## 6. File budget

**Contract (this PR):** 2 files / ≤350 net LOC.

- `docs/V0_5_ROW_6_PLAN_CWD_CONTEXT_CONTRACT.md` (new — this file).
- `docs/V0_5_ROADMAP.md` (mod — flip row #6 from "Bucket A draft"
  status note to "CONTRACT LOCKED at
  docs/V0_5_ROW_6_PLAN_CWD_CONTEXT_CONTRACT.md").

**Implementation (separate PR, NOT pre-authorised):** ≤4 files /
≤120 net LOC.

- `src/ai_cockpit/plans/schema.py` (mod — add `assumed_cwd` field
  + YAML round-trip; ~20 LOC).
- `src/ai_cockpit/planner_interactive/types.py` (mod —
  `PlanDraft.to_dict()` writes `assumed_cwd =
  str(request.project_root.resolve())`; ~10 LOC).
- `src/ai_cockpit/cli.py` (mod — `plans_run_cmd` warning logic;
  ~25 LOC).
- `tests/test_plan_schema.py` (mod — round-trip + absent-field +
  mismatch-warn coverage; ~50 LOC).

## 7. Threat model

| Threat | Mitigation |
| --- | --- |
| Operator on a different machine sees absolute path from another machine and is confused | Warning message names both paths explicitly ("plan assumed_cwd '/abs/A' differs from --root '/abs/B'"); operator can decide. Plan saver records the resolved absolute path on the original machine; this is documented in the warning text. |
| `Path.resolve()` traverses a symlink and the saved path doesn't match operator expectations | `resolve()` is the same one used by `--root` resolution elsewhere; consistent. Operator can always inspect `assumed_cwd` directly in the YAML. |
| `assumed_cwd` leaks PII (home directory paths in shared repos) | The plan YAML is the operator's artefact; they control whether they commit it. Same risk profile as any path string in `.plan.yaml` today (`title`, `why`, etc. can already mention paths). No new exposure surface. |
| Plan portability across operators degrades | This is the *intent* of the warning — surface the portability problem rather than let it cause silent breakage. |
| Implementation accidentally reads `assumed_cwd` into a prompt | `assumed_cwd` is never passed to any prompt builder. The implementation test suite asserts the reviewer prompt does not contain the `assumed_cwd` substring (parametrised with a known value). |

## 8. DoD

**Contract done (this PR) when:**

1. `docs/V0_5_ROW_6_PLAN_CWD_CONTEXT_CONTRACT.md` is merged to
   master.
2. `docs/V0_5_ROADMAP.md` Bucket A row #6 entry points to this
   contract file by name.
3. Pre-push 4 checks pass: `pytest`, `ruff check .`, `mypy .`,
   `ai-cockpit "smoke v0_5-row-6-contract" --max-loops 1 --dry-run
   --llm none --no-checkpoint`.
4. No source under `src/` modified; no test added/removed.

**Implementation done (future, separate PR after user signal) when:**

1. `Plan.assumed_cwd: str | None` field shipped; YAML round-trips
   under both `None` and string values.
2. `PlanDraft.to_dict()` writes `assumed_cwd` from the planner
   request's resolved project_root.
3. `plans run` emits the mismatch warning (text matching §5
   above); absence of field is silent.
4. New tests cover (a) round-trip with field, (b) round-trip
   without field (absent in YAML, `None` on load), (c)
   `plans run` warning text when mismatched, (d) `plans run`
   silence when matched, (e) `plans run` silence when field is
   absent (Q2 behaviour), (f) reviewer prompt asserts no leak
   of `assumed_cwd` substring.
5. Pre-push 4 checks pass; ≤4 / ≤120 budget respected.

## 9. Out of scope for row #6

- No `assumed_cwd_resolves_today` runtime check (don't `Path.exists()`).
- No automatic `--root` correction. Operator decides.
- No rewriting of plan `test_commands` to remove the cwd-prefix
  pattern; row #5 (planner-self-check) handles that proactively;
  PR #83 Layer 3 verifier hint handles it reactively.
- No multi-machine plan portability beyond the warning.
- No PII scrubbing on `assumed_cwd`; operator-managed.
- No env-var or config override of `assumed_cwd`; the field is the
  literal resolved path at `plan` time.
- No CLI flag like `--ignore-cwd-mismatch`; warn-only means
  operator can always proceed silently.

## 10. Rollback

If the implementation PR proves harmful:

1. Revert the implementation PR. Contract (this file) stays as
   historical record.
2. Existing plan YAML files with `assumed_cwd` written are still
   valid YAML; loader from pre-row-#6 will silently ignore the
   unknown key (verify in test).
3. `plans run` returns to pre-row-#6 silent behaviour.

## 11. Authorisation & operating rhythm

Per the 2026-05-17 15:08 UTC user-locked authorisation:

1. **Contract draft only.** This PR ships this file + the
   ROADMAP pointer. No source under `src/` is touched.
2. **Implementation is gated by Phase 0.** Per
   `docs/V0_5_ROADMAP.md` §5, no v0.5 row moves past CONTRACT
   until `docs/V0_4_EXIT_EVIDENCE.md` is filled in by the
   operator and merged to master. Cron MUST refuse the
   implementation PR until both conditions hold:
   - `docs/V0_4_EXIT_EVIDENCE.md` merged on master with operator
     identity recorded; AND
   - explicit user signal `open-gate v0.5-row-6-impl`.
3. **One tick, one gate.** Implementation PR is one cron tick.

## 15. Open-gate protocol

```text
open-gate v0.5-row-6-contract       # granted 2026-05-17 15:08 UTC;
                                    # this PR is the deliverable.
open-gate v0.5-row-6-impl           # NOT granted — requires
                                    # (a) V0_4 evidence on master AND
                                    # (b) explicit user signal.
open-gate v0.5-row-6-block-mode     # NEVER GRANTED — Q1 locked
                                    # "warn only". Changing to block
                                    # requires a contract amendment.
open-gate v0.5-row-6-into-prompt    # NEVER GRANTED — §9 boundary;
                                    # assumed_cwd stays out of every
                                    # prompt builder.
```

A future `open-gate v0.5-row-6-impl` signal must (a) confirm the
V0_4 evidence is merged on master (cron will verify) and (b)
confirm acceptance of Q1+Q2 answers as locked. Without (a), cron
stops with an OQ. Without (b), cron treats as ambiguous and stops
with an OQ.
