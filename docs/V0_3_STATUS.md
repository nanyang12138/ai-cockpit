# v0.3 — Operating Status (in-repo snapshot / fallback)

**Status as of 2026-05-17 ~08:51 UTC, master tip `338d668`:**
`idle-healthy`. Section A is 8/8 complete. Section B's required set
is delivered **plus B.2 implementation (PR #66)**; only B.4
implementation remains gated. The v0.4 exit-gate operator runbook
and evidence template shipped (PR #73); the gate run itself is still
operator-driven and has not been executed. No `active_plan_id` is
set; cron is NOT authorized to execute any `plans run` slice.

## 1. What this file is

`V0_3_STATUS.md` is the **cron operating contract** for the v0.3
window. Historically it lived only in the cron agent's
AutomationMemory and was never checked into the repository. That made
the file invisible to:

- A fresh cron VM that starts without a hydrated AutomationMemory.
- Any non-cron contributor (human or AI) reading the docs cold.
- The B.6 §3 Q5 two-key authorization model, which depends on this
  file naming `active_plan_id` — but had no in-tree fallback if the
  AutomationMemory copy was lost.

This file is an **in-repo snapshot** of the same operating contract,
maintained so the source tree alone is sufficient to answer "what
should cron do on the next tick?". When the AutomationMemory copy
exists, it remains the canonical source of truth and may move ahead
of this file between merges; this snapshot is updated by ordinary PRs
when the operating mode changes (idle ↔ active, new open-gate signal,
v0.4 gate pass, etc.).

The file is hand-maintained: it is never written by an LLM during a
graph run, so it cannot be self-modified by a jailbroken planner. This
property is what makes it suitable as the second key in the B.6 §3 Q5
authorization model.

## 2. Current mode

```
mode:              idle-healthy
master_tip:        338d668
last_section_a:    A.8 (PR #42, 2026-05-16) — Section A 8/8 complete
last_section_b:    B.2 implement (PR #66, 2026-05-17)
last_v0_4_prep:    operator runbook + evidence template (PR #73, 2026-05-17)
active_plan_id:    (none)
v0.4_exit_gate:    NOT RUN — operator action required, see B_5_CONTRACT §4
                   and scripts/v0_4_exit_gate.sh
open_section_b:    B.5 contract (done), B.3 contract+impl (done),
                   B.2 contract+impl (done; PRs #63 + #66),
                   B.4 contract (done, impl not open-gated)
```

Per `docs/ROADMAP.md` "How cron should consume this file" §5:

> If the entire Section A list is exhausted, the cron returns to
> `idle-healthy` and waits for the user to authorize Section B work
> explicitly. Do NOT pick a Section B item without the user
> answering in their next session.

Cron's authorized action set this tick is therefore limited to:

- `idle-healthy` health checks (`pytest`, `ruff`, `mypy`, smoke).
- Documentation-only follow-ups inside the v0.3 doc-resync window
  (PRs #67–#70 plus this one; see §6 below).
- Updating this file itself, when the operating mode changes.

Cron is **not** authorized to:

- Open a new Section B implementation gate without an explicit user
  "open-gate B.X" signal.
- Run any `plans run` slice (B.6 §3 Q5 second key absent —
  `active_plan_id` is unset).
- Execute the v0.4 exit gate (B.5 §11.3: operator-only).
- Touch any `src/` file unless required by the open contract.

## 3. Section A — closed (8/8)

All items have a corresponding `✅ DONE` marker in
`docs/ROADMAP.md`. Cross-reference table:

| Item | PR | Commit | Banner in ROADMAP |
|------|----|--------|-------------------|
| A.1 status subcommand | #31 | (squash `7a903ab`) | ✅ DONE |
| A.2 memory list QOL | #34 | `d0a6c03` | ✅ DONE |
| A.3 aider token/cost | #35 | `578fbec` | ✅ DONE |
| A.4 workflows list/validate | #38 | `bbf29fc` | ✅ DONE |
| A.5 anti-deception edges | #39 | `474d048` | ✅ DONE |
| A.6 ARCHITECTURE.md | #40 | `a450586` | ✅ DONE |
| A.7 dirty-tree precheck | #41 | `c4a5ccd` | ✅ DONE |
| A.8 gitignore .aider.* | #42 | `072b25f` | ✅ DONE |

## 4. Section B — open / deferred summary

Tracked in full in `docs/ROADMAP.md` Section B; this is the
cron-actionable summary:

| Item | Contract | Impl | Authorization |
|------|----------|------|---------------|
| B.1 second worker | superseded by B.10c | n/a | closed |
| B.2 planner quirks | done (PR #63) | done (PR #66, `src/ai_cockpit/workers/quirks.py` + `tests/test_worker_quirks.py`) | closed |
| B.3 cost dashboard | done (PR #61) | done (PR #62) | closed |
| B.4 --system-prompt FILE | done (PR #64) | not started | needs explicit open-gate |
| B.5 v0.4 exit gate | done (PR #60) | operator runbook + evidence template shipped (PR #73, `scripts/v0_4_exit_gate.sh`, `docs/V0_4_EXIT_EVIDENCE.md`); exit run itself still pending | operator-only (B.5 §11.3) |
| B.6 multi-step planner | done | a/b/c shipped | closed (Q5 second key unset) |
| B.9 interactive planner | done | a/b/c shipped; d superseded by B.10b | closed |
| B.10 Cursor role backends | done | a/b/c/d/e shipped | closed |

When the user opens a gate (B.2 impl, B.4 impl, v0.4 exit gate, or a
new section item), this file's §2 `mode` field and §5 active queue
must be updated **in the same PR** that opens the gate, before any
code lands.

## 5. Active queue (zero items)

```
queue: []
```

When the user posts an "open-gate X" signal, the cron self-update
discipline is:

1. Append the gate to `queue` here, citing the user message verbatim.
2. Set `mode: start-next-step`.
3. Run the gate. Honour ≤8 files / ≤400 net LOC.
4. Land the implementation PR.
5. On merge, pop the gate from `queue`, return `mode` to
   `idle-healthy` (or the next queued gate), and update this file in
   the next tick before any other action.

## 6. v0.3 doc-resync window (2026-05-17) — **CLOSED**

The 2026-05-17 doc-resync that produced this file was authorized by
the user message "好好的分析一下 / … 可以" on 2026-05-17 ~08:03 UTC.
It was a **documentation-only** window and produced no `src/` changes.
All six PRs merged to master by 2026-05-17 ~08:51 UTC:

| PR | Branch | Subject | Status |
|----|--------|---------|--------|
| #67 | `cursor/roadmap-mark-a2-a8-done-de7a` | ROADMAP A.2–A.8 ✅ DONE markers | merged (`f0b7d23`) |
| #68 | `cursor/readme-v03-resync-de7a` | README v0.1 → v0.3 resync | merged (`752da03`) |
| #69 | `cursor/pyproject-bump-v03-de7a` | pyproject.toml version 0.1.0 → 0.3.0 | merged (`b3be6ab`) |
| #70 | `cursor/architecture-test-count-de7a` | ARCHITECTURE.md 16 → 17 test count | merged (`e1d3716`) |
| #72 | `cursor/v03-status-snapshot-de7a` | this file (initial commit) | merged (`b5469d8`) |
| #74 | `cursor/automation-prompt-v03-de7a` | AUTOMATION_PROMPT.md v0.2 → v0.3 | merged (`338d668`) |

Two **parallel** Section-B PRs merged inside the same window without
being part of it (user-authorized independently):

| PR | Subject | Status |
|----|---------|--------|
| #66 | B.2 implement: planner worker-quirk catalog + prompt hint injection | merged (`ab62ba7`) |
| #73 | v0.4 exit-gate operator runbook script + evidence template | merged (`0171697`) |

After the window closed, `mode` returned to `idle-healthy` and cron is
waiting for the next user signal (typically "open-gate B.5 exit run"
or "open-gate B.4 impl"; B.2 impl is now closed).

## 7. Permanent boundaries (carried verbatim from spec §12)

Cron's authorized action set is bounded by §12 regardless of any
queue / open-gate state:

- No UI, web app, daemon process, long-running background service.
- No cloud execution backend, multi-user / team permissions.
- No swarm, plugin marketplace, generic agent platform.
- No automatic emails / Slack / PR comments outside the agent's own PR.

Any proposal touching these is a STOP-and-OQ event, not a self-
resolve. See `AUTOMATION_PROMPT.md` §4 for the STOP protocol.

## 8. Relationship to AutomationMemory

If both this file and a hydrated AutomationMemory copy of
`V0_3_STATUS.md` exist, **the AutomationMemory copy wins** for mode /
queue / `active_plan_id` reads, because it is the live operational
state. This file is a fallback for the case where AutomationMemory is
absent (fresh VM, lost state, non-cron reader). When the two diverge,
cron's first action on any tick is to reconcile: read both, prefer
AutomationMemory if it exists, and open a doc-resync PR for this file
if its content is stale.

If only this file exists, cron treats it as authoritative until the
user clarifies otherwise.
