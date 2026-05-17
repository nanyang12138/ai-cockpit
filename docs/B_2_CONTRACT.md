# B.2 — planner prompt awareness of worker quirks (contract v0.1, DRAFT)

Status: **draft contract only.** The 2026-05-17 03:57 UTC queue
authorizes cron to *write this contract*; it explicitly does
**not** authorize any change to planner prompt source, allow-list,
or other implementation surface. The user must post-review this
draft before an implementation PR may be opened.

> Queue position: item #8 of the v0.3 Cursor hardening + v0.4
> startup window. Branch `cursor/v0_4-b2-contract`. Pure-
> documentation deliverable: 2 files / ≤300 net LOC. No code
> under `src/`, no tests touched.

## 1. Why

The §15.1 first real-LLM run was rejected on aider's habit of
auto-appending `.aider*` entries to the project `.gitignore` on
every invocation. The reviewer evidence then carried a "modified
`.gitignore`" that no planner-spec asked for, and the
acceptance-criterion "no other files modified" failed. PR #24
silenced that specific quirk at the worker level by passing
`--no-gitignore` to aider (see `src/ai_cockpit/workers/
aider_worker.py:111` and the surrounding comment block). That
fix is correct **for that quirk** but it does not generalize:

- The next worker quirk (aider auto-creating
  `.aider.tags.cache*`, cursor agent stamping a session-id
  file, an APIM bridge that injects a header echo) will hit the
  same failure mode and require another worker-level workaround.
- The planner has no way to know that a criterion like "no other
  files modified", "exact 1-file diff", or "diff size ≤ N lines"
  is *risky* against the active worker backend. It happily emits
  brittle criteria and the reviewer (correctly, per §9) fails
  the run.
- v0.4 (B.5) demands a zero-human-intervention end-to-end run on
  `examples/broken_calc` within ≤ $1 and ≤ 15 min. Each round of
  planner-spec → reviewer reject burns budget and risks tripping
  the §9 anti-deception suite if a future worker tries to "fix"
  noise by patching evidence (forbidden, see §9 below).

B.2 closes the structural gap by teaching the **planner** about
the worker backend selected for the run, so it produces criteria
the worker can plausibly satisfy. It deliberately does **not**
relax any reviewer-side guarantee.

## 2. Hard invariants (cannot be overridden at implementation time)

These override §3, override "small extra improvement" temptation
at implementation time, and override any judgement call inside
the future implementation PR. If the implementation must violate
one, the gate stays CLOSED and a new contract amendment is
required.

| Invariant | Source | How B.2 honors it |
| --- | --- | --- |
| §9 evidence-only reviewer | spec §9 | The reviewer prompt is **unchanged**. The 5-test anti-deception suite (`tests/test_anti_deception.py`) is treated as a hard regression gate. Worker-quirk hints flow into the *planner* prompt only — never into reviewer evidence, never into the reviewer system message, never into the verification command stdout. |
| §3.2 memory write approval | hard rule §3.2 | B.2 does not write `.ai-cockpit/memory/*` or `.ai-cockpit/suggestions/*`. Worker-quirk knowledge is **static** (compiled into source), not learned from memory. |
| §12 permanent boundaries | spec §12 | No daemon, no UI, no upload, no marketplace, no multi-user, no auto-outbound. The hint catalog ships as a Python dict in source. |
| ≤8 files / ≤400 net LOC per PR | EXECUTION_RULES | Contract (this PR): 2 files / ≤300. Implementation (future PR, separate authorization): ≤5 / ≤300. |
| No real LLM in CI | AUTOMATION_PROMPT §3.5 | All planner tests use the existing `LLMProvider` stub plus a fake worker-quirks catalog. CI never opens an LLM connection. |
| Worker-level safety net stays | EXECUTION_RULES | `--no-gitignore` (and any other worker-level guardrail already on master) is **kept**. B.2 is defense-in-depth, not a replacement. If the planner emits a brittle criterion anyway, the worker-level flag still suppresses the symptom. |
| One gate per cron tick | AUTOMATION_PROMPT §3.3 | This contract PR is queue item #8. Implementation is **not** pre-authorized — it requires a fresh user signal after post-review. |

## 3. Resolved design decisions (Q1–Q5, draft)

These are the **proposed** answers. Unlike the B.3 contract, they
are not user-locked yet; the user must signal acceptance during
post-review. Any item flagged "DEFERRED" stays out of the future
implementation PR until a follow-up contract amendment.

| # | Question | Draft decision | Rationale |
| --- | --- | --- | --- |
| Q1 | Where does the planner learn about worker quirks? | A static Python catalog: `src/ai_cockpit/workers/quirks.py` exposing `WORKER_QUIRKS: dict[str, list[WorkerQuirk]]` keyed by worker name (`"aider"`, `"cursor"`, `"stub"`). Each `WorkerQuirk` carries `id`, `human_summary`, `criteria_to_avoid` (≤3 strings), and `replacement_hint` (≤1 string). | Static beats dynamic for §9: the planner cannot be lied to via memory injection. The shape is small, reviewable in a single PR, and grep-friendly. Discovering quirks at runtime (e.g. running aider with `--dry-run` and parsing output) is rejected as out of scope — it adds a network/subprocess dependency the planner does not need. |
| Q2 | How does the catalog reach the planner prompt? | `build_planner_messages(...)` (both `src/ai_cockpit/llm/prompts.py` and `src/ai_cockpit/planner_interactive/prompts.py`) gains an optional `worker_hints: list[str] \| None = None` kwarg. When non-empty, a labeled subsection is appended to the user message: `"Worker quirks to design around (current backend: <name>):\n- <hint 1>\n- <hint 2>"`. Hints are clipped to ≤6 bullets, ≤80 chars each. | Optional kwarg keeps every existing call site green (default `None` → no behavior change). Two builders need the update — the v0.2 one-shot path and the B.9 interactive path. The clip discipline mirrors B.9 tool output clipping. |
| Q3 | Where is the worker name decided per run? | The CLI already selects the worker via `--worker <name>` (A.x). The `--worker` argument resolves to a name string; both `ai-cockpit plan` and `ai-cockpit plans run` flow that name into the planner builder. A new helper `quirks_for(worker_name: str) -> list[str]` returns the human-summary strings or `[]` for unknown / "none" workers. | The selection point already exists; B.2 only needs to thread it through. The "stub" worker maps to `[]` (no quirks). An unknown worker name does **not** raise — it returns `[]` and logs an INFO line. This is forward-compatible with B.1 successors. |
| Q4 | What is the catalog seed content? | One entry to start, matching the §15.1 failure mode: `aider.gitignore` — "aider edits `.gitignore` on each run; avoid criteria like 'no other files modified' or 'diff exactly 1 file'." Plus one `cursor.workspace_scan` placeholder entry describing the ≈19k input-token cost of cursor agent's workspace scan, with the replacement hint "avoid acceptance criteria that demand token-bounded turns under the cursor backend; the v0.4 budget is enforced per-run by B.3, not per-turn by the planner". | Seeding one entry per shipped worker proves the wiring without over-promising. New quirks are added in follow-up PRs (each ≤2 files / ≤80 LOC). DEFERRED: enumerating every aider auto-edit; that grows organically. |
| Q5 | How is the change *verified* without real LLM in CI? | Two test layers: (a) catalog round-trip — `quirks_for("aider")` returns a non-empty list, `quirks_for("stub") == []`, unknown name returns `[]`; (b) prompt-shape — `build_planner_messages(..., worker_hints=quirks_for("aider"))` includes each hint verbatim and is correctly bounded by the clip rule. The 5-test §9 anti-deception suite must still pass byte-identical (no new test, no test removed). | Static catalog plus prompt-shape assertion is a sufficient regression net. Real-LLM behavior is observed only when the user runs the B.5 exit gate (`docs/V0_4_EXIT_EVIDENCE.md`). |

### Why no `Q6` cost/cap question

B.2 carries no cost-cap surface. It only mutates a prompt
template; the runtime cost shift per call is bounded by the
hint clip (≤6 × ≤80 chars ≈ 500 chars ≈ 130 tokens). B.3's
dashboard already shows the per-run total if the operator wants
to verify the impact empirically.

## 4. CLI surface

**No CLI change in B.2 implementation.** The user-facing flags
(`ai-cockpit plan --worker <name>`, `ai-cockpit plans run
<plan> <slice> --worker <name>`) already exist. B.2 only changes
what the planner builder receives internally.

If a future amendment needs to disable the hint injection, the
proposed escape hatch is an env var `AI_COCKPIT_NO_WORKER_HINTS=1`
(not part of this draft; flagged for the post-review pass).

## 5. Data model

```python
@dataclass(frozen=True)
class WorkerQuirk:
    id: str                       # e.g. "aider.gitignore"
    human_summary: str            # one-line description used in the prompt
    criteria_to_avoid: tuple[str, ...]   # examples (informational, ≤3)
    replacement_hint: str         # short positive instruction

WORKER_QUIRKS: dict[str, tuple[WorkerQuirk, ...]] = { ... }

def quirks_for(worker_name: str) -> list[str]:
    """Return the human_summary strings for the named worker, or []."""
```

Note `tuple` over `list` keeps the catalog immutable at the module
level, matching the immutability of `DEFAULT_AIDER_ARGS`.

## 6. File budget

**Contract (this PR):** 2 files / ≤300 net LOC.

- `docs/B_2_CONTRACT.md` (new) — this document.
- `docs/ROADMAP.md` (mod) — §B.2 stub replaced with a pointer
  to this contract plus a one-line summary.

**Implementation (separate PR, NOT pre-authorized):** ≤5 files /
≤300 net LOC.

- `src/ai_cockpit/workers/quirks.py` (new — catalog + helper;
  ~80 LOC).
- `src/ai_cockpit/llm/prompts.py` (mod — `worker_hints` kwarg
  + clipped subsection; ~25 LOC).
- `src/ai_cockpit/planner_interactive/prompts.py` (mod —
  identical kwarg + subsection; ~25 LOC).
- `src/ai_cockpit/cli.py` (mod — thread the `--worker` name
  into the planner builder; ~20 LOC).
- `tests/test_worker_quirks.py` (new — catalog round-trip +
  prompt-shape assertions; ~80 LOC).

`tests/test_anti_deception.py` must remain **byte-identical**.

## 7. Threat model

| Threat | Mitigation |
| --- | --- |
| Planner hint sneaks into reviewer prompt and influences the verdict (§9 deception) | The hint is appended **only** to the planner system+user pair via the existing `build_planner_messages`. The reviewer builder (`build_reviewer_messages`) is untouched. A dedicated test asserts the reviewer evidence dict contains no `worker_hints` key and the reviewer system+user pair contains no quirk substring. The 5-test anti-deception suite remains the hard gate. |
| Future worker plugin injects a malicious quirk hint at import time | Catalog is a module-level constant in the ai-cockpit package; plugins (Section C) are permanently out of scope per §12. Any future expansion to load quirks from a plugin requires its own contract. |
| Hints grow unbounded and crowd the prompt | Hard clip: ≤6 bullets, ≤80 chars each (tested). New quirk PRs must remove a stale entry if the catalog would exceed the per-worker cap. |
| Quirk catalog drifts from worker behavior (e.g. PR drops `--no-gitignore`) | The aider quirk's `criteria_to_avoid` is a comment-style hint, not a hard assertion. Worker-level `--no-gitignore` stays the primary defense; if it is ever removed, a separate contract must justify that. |
| Operator runs with `--worker stub` (deterministic) and expects matching hints | `quirks_for("stub")` returns `[]`. The stub worker produces deterministic output that never trips planner criteria, so empty is correct. |
| The planner is overly conservative and refuses to emit any criterion | Hint phrasing is **avoidance**, not refusal: "avoid criteria like X" — the planner is still asked to produce 3-6 criteria per B.6. The fixture catalog is reviewed for tone before merge. |
| §3.5 budget grows because each call now sends ~130 extra tokens | One sentence appended is far under the existing memory_context block. B.3's dashboard shows the actual impact. If the per-run cost crosses B.5 Q4 (1)'s $1 budget, the operator can set `AI_COCKPIT_NO_WORKER_HINTS=1` (proposed in §4) and re-run. |

## 8. DoD

**Contract done (this PR) when:**

1. `docs/B_2_CONTRACT.md` is merged to master.
2. `docs/ROADMAP.md` §B.2 stub is replaced with a pointer to
   this contract plus a one-line summary.
3. Pre-push 4 checks pass: `pytest`, `ruff check .`, `mypy .`,
   `ai-cockpit "smoke b2-contract" --max-loops 1 --dry-run
   --llm none --no-checkpoint`.
4. No source under `src/` modified; no test added/removed.

**Implementation done (future, separate PR after user signal) when:**

1. `src/ai_cockpit/workers/quirks.py` ships the catalog +
   `quirks_for` helper.
2. Both prompt builders (`llm/prompts.py` +
   `planner_interactive/prompts.py`) accept and inject
   `worker_hints` correctly.
3. The CLI passes `--worker <name>` into the planner builder
   for both `plan` and `plans run` flows.
4. 5-test §9 anti-deception suite remains byte-identical and
   green.
5. New `tests/test_worker_quirks.py` covers catalog round-trip
   + prompt-shape + reviewer isolation.
6. Pre-push 4 checks pass; ≤5 / ≤300 budget respected.

## 9. Out of scope for B.2

- No reviewer-prompt modification — permanent §9 boundary.
- No real-time worker discovery (running `aider --help`,
  spawning a probe). Static catalog only.
- No plugin marketplace for community quirks — §12 boundary.
- No memory-driven quirk learning. The planner does not write
  to memory based on reviewer rejects.
- No per-criterion validator that pre-rejects the planner's
  output before the worker runs — that would be a second §9
  surface and is rejected. The planner self-regulates via
  hints; the reviewer remains the only authority.
- No auto-fix for an already-saved plan that violates a hint.
  Plans on disk are immutable evidence per B.6.
- No cursor worker quirk catalog expansion beyond the seed
  `cursor.workspace_scan` placeholder — added incrementally
  as B.10pty + B.5 exit-gate evidence accumulates.

## 10. Rollback

If the implementation PR proves harmful:

1. Revert the implementation PR. Contract (this file) stays as
   historical record.
2. Existing planner calls continue to work: the `worker_hints`
   kwarg defaults to `None` and is opt-in; reverting removes
   it cleanly.
3. The §15.1 failure mode stays suppressed by the existing
   `--no-gitignore` worker-level flag (PR #24), which is
   independent of B.2.

## 11. Authorization & operating rhythm

Per the 2026-05-17 03:57 UTC user-locked authorization:

1. **Contract draft only.** This document and the
   `docs/ROADMAP.md` §B.2 pointer are the only B.2 deliverables
   of the current cron tick (queue item #8). Source under
   `src/` MUST NOT be touched in this PR.
2. **Implementation is NOT pre-authorized.** Unlike B.3, B.2
   requires a separate user signal after post-review of this
   draft. Cron must STOP and OQ if it sees an implementation
   PR open against this contract without that signal.
3. **One tick, one gate.** Even after the user opens the
   implementation gate, cron ships it on a later tick (queue
   item promotion, not same-tick chaining).

## 15. Open-gate protocol

```text
open-gate B.2 contract (draft)        # granted by the 2026-05-17
                                      # 03:57 UTC prompt body;
                                      # this PR is the deliverable.
open-gate B.2 implementation          # NOT granted — requires a
                                      # fresh user signal after
                                      # post-reviewing this draft.
open-gate B.2 reviewer-side change    # NEVER GRANTED — §9 boundary;
                                      # any reviewer-prompt edit
                                      # needs a separate contract.
open-gate B.2 plugin-loaded quirks    # NEVER GRANTED — §12 boundary.
```

A future `open-gate B.2 implementation` signal must reference the
specific Q-row in §3 that the implementation addresses (and any
that it explicitly defers). Without that reference, cron treats
the signal as ambiguous and stops with an OQ entry.
