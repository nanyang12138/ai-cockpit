# V0.5 Row #2 — `reviewer-findings` contract (v0.1, LOCKED)

Status: **contract locked.** User authorised the Q-answers on
2026-05-17 15:08 UTC ("采纳所有 cron 推荐, #2 Q2 选 strict").
Implementation gate double-blocked on V0_4 evidence + explicit
`open-gate v0.5-row-2-impl` signal, AND additionally depends on
row #1 (`planner-replan`) being implementation-DONE on master
for full value (the gate can ship before row #1 impl, but the
replan integration test is skipped/xfail until row #1 ships).

> Pure-documentation deliverable: 2 files / ≤350 net LOC. No code
> under `src/`, no tests touched.

## 1. Why

Today (master tip post-v0.4) the reviewer emits high-quality
diagnostics in `notes` / `suggested_fix` fields:

> "git_status shows calc.py modified at repo root, not under
> examples/broken_calc — file appears to be in the wrong
> location."

These strings are valuable. But the graph itself is **blind to
them**: only an operator reading the run summary ever consumes
them. Specifically:
- `decision_node` reads only `review.get("passed")`.
- retry runs the same coder with no additional context.
- Even after row #1 ships, replan will get
  `verification_result` (raw) but **not** the reviewer's
  structured interpretation of *why* that result is a failure.

Row #2 closes that loop: the reviewer emits a new
`objective_findings: list[str]` field — short factual statements
derived literally from `verification_result` text — and the next
turn (coder retry OR replan, gated by `replan_count > 0`) reads
that field as additional input context. **The reviewer's
narrative `notes` and `suggested_fix` still do NOT flow into any
prompt; only `objective_findings` does.**

Critically, §9 hardness is **strengthened**, not weakened: a new
schema-level validator asserts every char of every
`objective_findings` string is literally present in
`verification_result` text (strict mode, per user Q2). LLM
paraphrasing is rejected. This is a stricter constraint than
even the current `coder_result`-exclusion rule — the validator
proves at runtime that no new authorship has slipped in.

## 2. Hard invariants (cannot be overridden at implementation time)

| Invariant | Source | How row #2 honours it |
| --- | --- | --- |
| §9 evidence-only reviewer | spec §9 | Reviewer prompt unchanged. The new `objective_findings` field is emitted by the reviewer LLM, then **validated server-side** to be literal substrings of `verification_result`. If validation fails, findings are dropped (logged as a warning) and the graph proceeds as if row #2 wasn't present. |
| §9 strict mode (Q2 user-locked) | row #2 §3 Q2 | Validator: every char of every finding must appear, in order, as a substring of `json.dumps(verification_result, sort_keys=True)`. Zero LLM authorship in findings. Permissive mode is explicitly deferred to v0.6 if strict turns out too rigid in practice. |
| §9 symmetry (Q4 user-locked) | row #2 §3 Q4 | Next coder turn (whether plain retry or replan) does NOT see prior `coder_result`. Even on retry, coder gets `objective_findings` (filtered fact-only) but never its own prior narrative. This keeps the §9 boundary symmetric across all role transitions. |
| `coder_result` never in `objective_findings` | row #2 §3 implicit | Validator additionally rejects any finding that contains any substring of `coder_result`. Even if the literal-substring check passes against `verification_result`, a `coder_result` overlap drops the finding. (verification_result and coder_result are typically disjoint, so this is belt-and-suspenders.) |
| Reviewer narrative (`notes`, `suggested_fix`) NEVER fed to a prompt | row #2 §1 | Only `objective_findings` flows into the next turn's prompt. `notes` + `suggested_fix` continue to be operator-visible summary output only. Test asserts `notes` content does NOT appear in any subsequent planner / coder prompt. |
| Bounded findings size | row #2 §4 | At most 6 findings per review turn; each finding ≤ 200 chars. The validator drops anything exceeding either cap. |
| §3.2 memory write approval | hard rule §3.2 | No memory write. Findings live only in `TaskState.review_result.objective_findings`. |
| §12 permanent boundaries | spec §12 | No daemon, no UI, no swarm. Single-process. |
| ≤8 files / ≤400 net LOC per PR | EXECUTION_RULES | Contract (this PR): 2 files / ≤350. Implementation: ≤7 / ≤350. |

## 3. Resolved decisions (user-locked 2026-05-17 15:08 UTC)

| # | Question | User decision | Rationale |
| --- | --- | --- | --- |
| Q1 | Schema shape: `list[str]` vs `list[{source, fact}]` | **`list[str]`** | Simplest schema for v0.5; evolve to structured form in v0.6 only if real-LLM evidence shows the bare strings are insufficient. Avoids YAGNI. |
| Q2 | §9 strictness: strict literal-substring vs permissive | **Strict.** Every char of every finding must appear in `verification_result` serialised text. | Safest §9 posture. The whole point of row #2 is that the reviewer's narrative DOESN'T cross into prompts; only verified facts do. Permissive mode opens an LLM authorship channel that would defeat the design. Permissive is deferred to v0.6 if strict turns out too rigid in real operator runs. |
| Q3 | Coupling to row #1: who consumes findings? | **Both**, gated by `replan_count > 0`. | First-attempt coder gets a clean prompt (no findings, no prior attempt history). After first failure: retry coder gets findings; replan planner gets findings. This keeps the "no prior history pollutes a fresh attempt" property while ensuring the loop has memory of failures. |
| Q4 | Next coder turn still hidden from prior `coder_result`? | **Yes — still hidden.** | §9 boundary stays symmetric across all turns. Self-narrative is treated the same as other-narrative: forbidden. The fact-only `objective_findings` is the only retrospective signal. |

## 4. Schema additions

### 4.1 `ReviewResult` extension

`src/ai_cockpit/state.py`:

```python
class ReviewResult(TypedDict, total=False):
    # existing fields:
    passed: bool
    issues: list[str]
    risk_level: Literal["low", "medium", "high"]
    suggested_fix: str
    notes: str
    # NEW (row #2):
    objective_findings: list[str]
```

`total=False` keeps pre-row-#2 checkpoints loading.

### 4.2 Reviewer prompt schema delta

`src/ai_cockpit/llm/prompts.py::REVIEWER_SCHEMA` gains one entry:

```python
REVIEWER_SCHEMA = {
    # ... existing entries ...
    "objective_findings": (
        "array of short factual statements (≤6 items, each ≤200 "
        "chars). Each statement MUST quote substrings of the "
        "verification evidence verbatim — no paraphrasing, no "
        "interpretation, no causal speculation. The graph will "
        "REJECT any finding that is not literally a substring of "
        "the verification_result text."
    ),
}
```

The prompt instruction is itself a §9-flavoured constraint:
the LLM is told the validator will reject paraphrased text. This
shapes the LLM output to be valid in the first place.

### 4.3 Validator

`src/ai_cockpit/llm/prompts.py::validate_objective_findings`:

```python
def validate_objective_findings(
    findings: list[str],
    verification_result: dict,
    coder_result: str = "",
) -> tuple[list[str], list[str]]:
    """Return (accepted, rejected_with_reason)."""
    serialised = json.dumps(verification_result, sort_keys=True)
    accepted: list[str] = []
    rejected: list[str] = []
    for finding in findings[:6]:                       # cap 6
        if len(finding) > 200:
            rejected.append(f"too-long:{finding[:50]}...")
            continue
        if finding not in serialised:                  # strict substring
            rejected.append(f"not-in-verification:{finding[:50]}...")
            continue
        if coder_result and any(
            chunk in finding
            for chunk in _ngrams(coder_result, n=20)   # 20-char shingles
        ):
            rejected.append(f"coder-result-overlap:{finding[:50]}...")
            continue
        accepted.append(finding)
    return accepted, rejected
```

Validation runs in `make_reviewer_node` AFTER the LLM call,
BEFORE the result is committed to `TaskState`. Rejected findings
are logged at INFO level (operator-visible if `--verbose`) but
never reach prompts.

## 5. CLI surface

**No new flags.** Row #2 is invisible at the CLI layer; the
findings flow is internal to the graph.

If `--verbose` is set on `plans run`, INFO-level logs from the
validator surface to stderr so operators can see which findings
were rejected and why.

## 6. File budget

**Contract (this PR):** 2 files / ≤350 net LOC.

- `docs/V0_5_ROW_2_REVIEWER_FINDINGS_CONTRACT.md` (new — this).
- `docs/V0_5_ROADMAP.md` (mod — flip row #2 status to "CONTRACT
  LOCKED").

**Implementation (separate PR, NOT pre-authorised):** ≤7 files /
≤350 net LOC.

- `src/ai_cockpit/state.py` (mod — `objective_findings` on
  `ReviewResult`; ~10 LOC).
- `src/ai_cockpit/llm/prompts.py` (mod — `REVIEWER_SCHEMA` entry
  + `validate_objective_findings` helper; ~80 LOC).
- `src/ai_cockpit/nodes/reviewer.py` (mod — run validator
  post-LLM; ~30 LOC).
- `src/ai_cockpit/nodes/coder.py` (mod — read findings on
  retry; gated by `replan_count > 0` per Q3; ~25 LOC).
- `src/ai_cockpit/nodes/planner.py` (mod — read findings on
  replan; gated by `replan_count > 0`; ~25 LOC). Only
  meaningful after row #1 ships; before then, this branch is
  unreachable.
- `tests/test_reviewer_findings.py` (new — validator unit tests
  + integration with retry + §9 isolation tests; ~120 LOC).
- `tests/test_anti_deception.py` (existing, stays byte-
  identical per §2).

## 7. Threat model

| Threat | Mitigation |
| --- | --- |
| Reviewer LLM paraphrases findings, slipping new authorship into prompts | Strict validator (§4.3): every char of every finding must literally appear in `verification_result` serialised text. Paraphrased findings are dropped before reaching `TaskState`. |
| Reviewer LLM lifts substrings from `coder_result` (which IS in `state` even though not in reviewer prompt) | 20-char shingle overlap check rejects findings that share ≥20 contiguous chars with `coder_result`. Belt-and-suspenders. |
| Findings grow unbounded and crowd the next turn's prompt | Cap ≤6 findings, each ≤200 chars (≈1200 chars total worst case ≈ 300 tokens — small compared to existing user message). |
| Validator rejects all findings on a given turn | Acceptable: graph proceeds with empty `objective_findings`. Effective behaviour = pre-row-#2 (retry runs with clean prompt). Logged at INFO so operator can observe. |
| Coupling to row #1 creates a hidden dependency | The replan-input path (`nodes/planner.py` change in §6) is dead code until row #1's `decision → planner` edge exists. Test marked `xfail` until row #1 impl is merged. |
| `notes` / `suggested_fix` content sneaks into a prompt via developer error | Dedicated test asserts that for a reviewer output with `notes="SENTINEL"`, the SENTINEL substring does NOT appear in either (a) the next coder prompt, (b) the next planner replan prompt. Test runs on master always. |
| Validator becomes a §9 bypass surface (someone weakens it) | The strict-substring check is the smallest possible kernel — five lines, easy to audit. Permissive mode is explicitly an out-of-scope item (Q2 "deferred to v0.6 if strict too rigid") and would require its own contract amendment naming the relaxation. |
| `verification_result` itself contains sensitive data (e.g. API keys in stderr) and findings echo them | This risk exists today: `verification_result` already reaches the reviewer prompt. Row #2 doesn't widen that surface, only narrows the propagation. Operator-side `--verbose` reveals validator decisions; operator can audit. |

## 8. DoD

**Contract done (this PR) when:**

1. `docs/V0_5_ROW_2_REVIEWER_FINDINGS_CONTRACT.md` merged.
2. `docs/V0_5_ROADMAP.md` row #2 entry points here by filename.
3. Pre-push 4 checks pass.
4. No source / test touched.

**Implementation done (future, separate PR after user signal) when:**

1. `ReviewResult.objective_findings: list[str]` field exists,
   `total=False`, checkpoints load cleanly.
2. `REVIEWER_SCHEMA` gains the entry (text matches §4.2).
3. `validate_objective_findings` ships, with strict
   substring + ≤6 + ≤200 chars + 20-char `coder_result` overlap
   rejection rules.
4. `make_reviewer_node` runs validator post-LLM, writes only
   accepted findings to `TaskState`, logs rejections at INFO.
5. Coder retry consumes findings when `replan_count > 0`.
6. Planner replan consumes findings (dead code until row #1
   ships; integration test xfail until then).
7. New `tests/test_reviewer_findings.py` covers validator
   acceptance + rejection per rule + §9 isolation (with
   sentinels for `notes` AND `coder_result`).
8. 5-test anti-deception suite stays byte-identical and green.
9. Pre-push 4 checks pass; ≤7 / ≤350 budget respected.

## 9. Out of scope for row #2

- No structured findings schema (Q1 locks `list[str]`).
- No permissive mode (Q2 locks strict; permissive is a separate
  v0.6 gate IF strict turns out too rigid in real-operator
  evidence).
- No reviewer `notes` / `suggested_fix` in any prompt — ever.
- No multi-turn finding aggregation (each review turn produces
  its own findings; they don't accumulate across turns; row #1
  replan input shows the most recent turn's findings only).
- No memory-driven finding learning.
- No operator override to force-include a rejected finding.

## 10. Rollback

If the implementation PR proves harmful:

1. Revert the implementation PR.
2. Existing checkpoints with `objective_findings` populated will
   still load under the reverted schema (the field is ignored).
3. Reviewer prompt is unchanged pre/post — schema entry removal
   reverts the LLM instruction.
4. Test suite returns to pre-row-#2 baseline.

## 11. Authorisation & operating rhythm

Per the 2026-05-17 15:08 UTC user-locked authorisation:

1. **Contract draft only.**
2. **Implementation gated by Phase 0 + explicit
   `open-gate v0.5-row-2-impl`**. Cron MUST refuse implementation
   without both.
3. **Row #1 IMPL precedence**: implementation can ship before
   row #1 implementation, but the replan-input path is then
   dead code (test marked `xfail`). Sequencing both impls in
   the same operator window is preferred.

## 15. Open-gate protocol

```text
open-gate v0.5-row-2-contract           # granted 2026-05-17 15:08 UTC;
                                        # this PR is the deliverable.
open-gate v0.5-row-2-impl               # NOT granted — requires
                                        # (a) V0_4 evidence on master AND
                                        # (b) explicit user signal.
open-gate v0.5-row-2-permissive-mode    # NEVER GRANTED in v0.5;
                                        # Q2 locked strict; relaxation
                                        # requires a v0.6 contract
                                        # naming the specific failure
                                        # case strict mode can't handle.
open-gate v0.5-row-2-notes-in-prompt    # NEVER GRANTED — §9 spine;
                                        # would defeat the entire
                                        # design of row #2.
open-gate v0.5-row-2-coder-result-in    # NEVER GRANTED — Q4 locked;
                                        # §9 symmetry hard rule.
```

A future `open-gate v0.5-row-2-impl` signal must (a) confirm V0_4
evidence on master AND (b) accept Q1+Q2+Q3+Q4 as locked.
Implementation order relative to row #1 is operator's choice;
test xfail covers the dependency cleanly.
