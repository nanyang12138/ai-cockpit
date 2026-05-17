# B.3 — real-LLM cost dashboard (contract v0.1)

Status: **contract authored, implementation gate (queue item #7)
already authorized by the 2026-05-17 03:57 UTC user-locked
72h window.** This document is the locked specification for the
`ai-cockpit cost` subcommand that backs B.5 Q4 metric (1) (single
exit-gate run total cost ≤ $1 USD). It is a pure-documentation
deliverable: no source under `src/` and no test fixture is
modified by it. The matching summary in `docs/ROADMAP.md` §B.3
is updated to point here.

> Implementation lives in a separate, follow-up PR (queue item
> #7, branch `cursor/v0_4-b3-impl`, ≤5 files / ≤350 net LOC).
> This contract is the binding spec for that PR.

## 1. Why

A.3 (PR #34) extracts `tokens_sent / tokens_received /
cost_message_usd / cost_session_usd` from aider stdout into
`WorkerResult.metrics`. B.10pty-session (PR #58 → `b144848`)
introduced a parallel `last_usage` dict on the Cursor RPC
session (`input_tokens / output_tokens / cache_read_tokens /
cache_write_tokens`).

What is missing: (a) `WorkerResult.metrics` is dropped on the
floor by `make_coder_node` — only `result.summary` reaches
`TaskState.coder_result`, so the numeric signal never reaches
the checkpoint DB; (b) no CLI exposes the aggregate, so the
B.5 §4 operator cannot observe Q4 (1) ≤ $1 without ad-hoc grep.

B.3 closes both gaps with the minimum surface: one optional
`TaskState.metrics` field, one coder-node propagation line, one
CLI subcommand, and one aggregator over the existing
checkpoint DB.

## 2. Hard invariants (cannot be overridden)

These override §3, override later "small extra improvement"
temptation at implementation time, and override any judgement
call during the queue-#7 PR.

| Invariant | Source | How B.3 honors it |
| --- | --- | --- |
| §12 permanent boundaries | spec §12 | Local read-only CLI subcommand only. No daemon, no web dashboard, no upload, no telemetry export, no marketplace, no multi-user. |
| §9 evidence-only reviewer | spec §9 | Metrics never enter the reviewer prompt. The evidence shape (`mvp_spec`, `acceptance_criteria`, `git_diff`, `git_status`, `verification_result`) is byte-for-byte unchanged. No new anti-deception test required — no new prompt input. |
| §3.2 memory write approval | hard rule §3.2 | `ai-cockpit cost` is read-only. Never writes `.ai-cockpit/memory/*`, `.ai-cockpit/suggestions/*`, or the checkpoint DB. |
| ≤8 files / ≤400 net LOC per PR | EXECUTION_RULES | Contract (queue #6): 2 files / ≤300. Implementation (queue #7): ≤5 / ≤350. |
| No real LLM in CI | AUTOMATION_PROMPT §3.5 | Aggregator runs on fixture checkpoint DBs built in-process. CI never opens a production DB. |
| Backward compatibility | EXECUTION_RULES | `TaskState` stays `total=False`. Pre-B.3 checkpoints decode with `metrics` absent; aggregator treats absence as "unknown", never as zero, and reports a coverage count. |
| One gate per cron tick | AUTOMATION_PROMPT §3.3 | This PR is queue #6. Implementation lands in queue #7 on a subsequent tick. |

## 3. Resolved design decisions (Q1–Q6, locked 2026-05-17)

These answers are derived deterministically from the 2026-05-17
03:57 UTC prompt body (queue row #6 + #7 wording) plus the
existing A.3 + B.10pty-session shapes already on master.
Anything ambiguous at implementation time that is not covered
here is a STOP-and-OQ event, not a self-resolve event.

| # | Question | Decision | Rationale |
| --- | --- | --- | --- |
| Q1 | Aggregation source | LangGraph SqliteSaver checkpoint DB at `.ai-cockpit/history/checkpoints.sqlite` (overridable via `--checkpoint-db`). Walked read-only via `SqliteSaver.list`; the aggregator decodes `state.get("metrics", {})` per checkpoint. | Prompt body says verbatim "聚合 checkpoint DB 中的 metrics". DB already exists and survives multi-process runs. No new persistence surface. Sidecar JSONL was considered and rejected — it would duplicate state. |
| Q2 | CLI shape | `ai-cockpit cost [--root PATH] [--checkpoint-db PATH] [--since DATE] [--format text\|json]`. `--since` accepts `today`, `YYYY-MM-DD`, or ISO-8601 datetime; default = all-time. Top-level `cost` only (no subcommand group). | Single flat command keeps the surface tiny. `--since` is required for the B.5 Q4 (1) per-run check. JSON mode lets the v0.4 evidence doc embed numbers programmatically. `memory list/show/accept` precedent argues against a group when only one verb exists. |
| Q3 | Metric keys covered | Aider worker (A.3): `tokens_sent`, `tokens_received`, `cost_message_usd`, `cost_session_usd`. Cursor worker (B.10pty): `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`. Aggregator sums every numeric key it sees; missing keys are reported as a coverage count (treated as "unknown", never zero). | Both shapes are already production keys. Naming them here pins the schema so a future worker backend cannot silently introduce a third convention. Honest-under-partial-coverage is more important than convenience. |
| Q4 | Per-run vs. cumulative | Both. `text` emits per-thread rows (latest checkpoint per thread) plus a grand-total row. `json` emits `{"threads": [...], "totals": {...}}`. `--since` filters threads by their latest-checkpoint timestamp. | B.5 Q4 (1) needs the per-run number (the operator picks the thread for the exit-gate run from `git log`); long-term cost trend wants the total. Returning both costs ~20 LOC; splitting would be more surface and more flags. |
| Q5 | Persistence change | Add one optional field to `TaskState`: `metrics: dict[str, float]` (typed-dict, `total=False`). `make_coder_node` writes `result.metrics` into state after each worker run. No schema migration; pre-B.3 checkpoints decode as if `metrics` were absent, which the aggregator already handles. | `total=False` keeps the addition backward-compatible. The propagation site is `make_coder_node` only — one line. No other node touches `metrics`. |
| Q6 | Cost cap enforcement | None. `ai-cockpit cost` is **read-only**: it does not refuse on threshold; it does not warn out-of-band; it does not write a flag file. The B.5 Q4 (1) ≤ $1 check is operator-evaluated against the printed total. | v0.3 ships no LLM cost cap (B.6 §3 Q6). Adding one here would duplicate that decision and create a §12-adjacent autonomous-budget mechanism that B.5 Q5 explicitly excludes (both "auto-expansion" and its inverse). |

### Note on cursor planner / reviewer `last_usage` (OQ-20)

B.10pty-session attaches `last_usage` to the `_RpcSession`
inside `CursorPlannerBackend` and `CursorReviewerBackend`, but
those backends do not write into `TaskState` (planner is
interactive; reviewer writes only `ReviewResult`). Wiring
planner / reviewer usage into `state["metrics"]` is **out of
B.3 scope** — OQ-20 (v0.5 candidate). The dashboard's keys
auto-cover planner / reviewer metrics once that lands, with no
further CLI change required.

## 4. CLI surface

`ai-cockpit cost` — read-only cost aggregator:

```
ai-cockpit cost [--root PATH] \
                [--checkpoint-db PATH] \
                [--since DATE] \
                [--format text|json]
```

Behavior:

1. Resolve the checkpoint DB: `--checkpoint-db` wins; else
   `<root>/.ai-cockpit/history/checkpoints.sqlite`. If the file
   does not exist, print `no checkpoint db found at <path>` to
   stderr and exit 0 (a fresh repo legitimately has no runs).
2. Open via `open_checkpoint_saver` (existing `checkpoint.py`
   helper). Walk every checkpoint tuple. For each `thread_id`,
   keep the **latest** checkpoint by `checkpoint["ts"]`.
3. Decode `state.get("metrics", {})` for each kept checkpoint.
   Sum each numeric key separately. Skip non-numeric values
   silently.
4. Apply `--since` as a filter on the latest-checkpoint
   timestamp. `today` resolves to `00:00:00 UTC` today; other
   values parse through `datetime.fromisoformat`.
5. Emit output per `--format`:
   - `text` (default): per-thread block (`thread <id> | ts
     <iso> | tokens=… cost=$… coverage=…`), then a grand-total
     block with `threads_matched`.
   - `json`: a single object `{"threads": [...], "totals":
     {...}, "schema_version": 1}`. Each thread carries
     `thread_id`, `ts`, the union of A.3 + B.10pty keys
     (missing absent), and `keys_missing: [str]`.

Exit codes: `0` on success (including "no checkpoint DB"); `2`
on Click argument-parse error; non-zero on unreadable DB.
**Never** non-zero because the aggregate exceeded a threshold —
see §3 Q6.

## 5. Data model

`TaskState` gains one optional field:

```python
class TaskState(TypedDict, total=False):
    ...
    metrics: dict[str, float]
```

`make_coder_node` propagates `result.metrics` into state
post-worker. No other node writes `metrics`. Aggregator key
allow-list (unknown numeric keys are summed but flagged):

| key | source | unit |
| --- | --- | --- |
| `tokens_sent` | aider stdout (A.3) | integer count |
| `tokens_received` | aider stdout (A.3) | integer count |
| `cost_message_usd` | aider stdout (A.3) | USD (per-message snapshot) |
| `cost_session_usd` | aider stdout (A.3) | USD (cumulative session) |
| `input_tokens` | cursor envelope (B.10pty) | integer count |
| `output_tokens` | cursor envelope (B.10pty) | integer count |
| `cache_read_tokens` | cursor envelope (B.10pty) | integer count |
| `cache_write_tokens` | cursor envelope (B.10pty) | integer count |

`total_cost_usd` display uses aider's `cost_session_usd`
(native cumulative). Cursor envelopes do not carry a dollar
cost; the dashboard reports `cost=N/A (tokens-only)` in `text`
mode and omits `cost_session_usd` from cursor-only threads in
`json` mode.

## 6. File budget

**Contract (queue #6, this PR):** 2 files / ≤300 net LOC —
`docs/B_3_CONTRACT.md` (new) + `docs/ROADMAP.md` (§B.3 stub →
contract pointer). No source under `src/`, no test, no fixture.

**Implementation (queue #7, separate PR):** ≤5 files / ≤350
net LOC.

- `src/ai_cockpit/cost.py` (new — walk + aggregate; ~150 LOC).
- `src/ai_cockpit/state.py` (mod — `metrics` field; ~5 LOC).
- `src/ai_cockpit/nodes/coder.py` (mod — propagate metrics; ~3).
- `src/ai_cockpit/cli.py` (mod — `cost` subcommand; ~50).
- `tests/test_cost.py` (new — fixture DB, aggregation,
  `--since`, JSON shape, empty DB, malformed metrics; ~140).
- README delta is optional within the same PR.

## 7. Threat model

| Threat | Mitigation |
| --- | --- |
| Aggregator silently drops a metric due to a key typo | Keys read via a constant set (`KNOWN_METRIC_KEYS`); `keys_missing` reported per thread; unknown numeric keys summed but flagged. Pinned by tests. |
| Cost number gamed by truncating the DB | DB path printed in `text` output and recorded in `json` output. `--checkpoint-db PATH` is part of the evidence so the reader can re-run on the same file. |
| Background run inflates tokens during the gate | `--since today` filters per-thread by latest-checkpoint timestamp; operator picks the gate-run row. B.5 Q4 (1) is evaluated per-thread, not global total. |
| Stale checkpoint DB schema after a LangGraph upgrade | Aggregator uses the supported `SqliteSaver.list` API; private msgpack layout is **not** assumed. Public-API regressions surface in tests. |
| Cursor planner / reviewer cost leaks into the reading | Planner / reviewer `last_usage` is **not** in `TaskState.metrics` today (OQ-20). Dashboard reports worker cost only; worker is the dominant v0.4 cost contributor. |
| Concurrent reads racing a live run | DB opened read-only with `check_same_thread=False`. Partial latest-checkpoint values for an in-flight thread are the truthful state, not a bug. |
| Privacy — token leakage via checked-in evidence | The dashboard never writes anywhere; `docs/V0_4_EXIT_EVIDENCE.md` is operator-authored opt-in. No automatic upload (§12). |
| §9 deception via metrics | Metrics are state-level only and never enter any prompt. The 5-test anti-deception suite remains green; no new prompt input → no new anti-deception test required. |

## 8. DoD

**Contract done (queue #6) when:**

1. `docs/B_3_CONTRACT.md` is merged to master.
2. `docs/ROADMAP.md` §B.3 stub is replaced with a pointer to
   this contract plus a one-line §4 CLI surface summary.
3. Pre-push 4 checks pass: `pytest`, `ruff check .`, `mypy .`,
   `ai-cockpit "smoke b3-contract" --max-loops 1 --dry-run
   --llm none --no-checkpoint`.

**Implementation done (queue #7, separate PR) when:**

1. `src/ai_cockpit/cost.py` ships the aggregator (read-only).
2. `TaskState.metrics` added (`total=False`); `make_coder_node`
   propagates `WorkerResult.metrics`.
3. `ai-cockpit cost --since today --format json` returns a
   well-formed object on a fixture DB carrying one aider-style
   and one cursor-style metrics blob.
4. 5-test §9 anti-deception suite still green (no new test
   required — no new prompt input).
5. Pre-push 4 checks pass; ≤5 / ≤350 budget respected.

## 9. Out of scope for B.3

- No daemon / UI / web dashboard / upload — §12, permanently.
- No automatic cost cap enforcement — see §3 Q6.
- No retention policy (DB pruning, log rotation) — operator
  owns `.ai-cockpit/history/*` lifecycle.
- No multi-currency support — USD only (aider stdout is USD).
- No real-time / streaming readout — point-in-time snapshot.
- No SQL view / external BI integration — JSON is the
  programmatic surface.
- No cursor planner / reviewer cost propagation in this gate —
  deferred to OQ-20 (v0.5 candidate).
- No `TaskState.metrics` consumer **other than** the
  aggregator. Graph nodes do not branch on metrics; the
  reviewer does not see metrics; cron does not branch on
  metrics. Adding a consumer requires its own contract.

## 10. Rollback

If the implementation PR proves harmful (slow walks, fixture
breakage):

1. Revert the implementation PR. Contract (this file) stays as
   historical record.
2. Existing runs are unaffected: removing `TaskState.metrics`
   from pre-B.3 checkpoints is a no-op because `total=False`
   makes absence and emptiness observationally identical.
3. The B.5 exit-gate operator falls back to grepping
   `cost_session_usd` from `coder_result` stdout transcripts —
   uglier, but demonstrably worked through v0.3.

## 11. Authorization & operating rhythm

Per the 2026-05-17 03:57 UTC user-locked authorization:

1. **Contract first.** This document and the `docs/ROADMAP.md`
   §B.3 pointer are the only B.3 deliverables of the current
   cron tick (queue item #6).
2. **Implementation next.** Queue item #7 (`ai-cockpit cost`
   subcommand) lands on a subsequent tick, on branch
   `cursor/v0_4-b3-impl`, within the ≤5 / ≤350 budget.
3. **One tick, one gate.** Cron must not ship contract and
   implementation in the same tick — that would skip the
   per-PR review gate.
4. **No operator action required.** Unlike B.5 §11, B.3 is a
   fully cron-shippable gate. The B.5 exit-gate operator
   consumes B.3's CLI surface after both PRs merge.

## 15. Open-gate protocol

Both the B.3 contract gate (this PR) and the B.3 implementation
gate (queue item #7) are pre-authorized under the 2026-05-17
03:57 UTC 72h window — no further user signal is required.

```text
open-gate B.3 contract               # implicitly granted by the
                                     # 2026-05-17 prompt body;
                                     # this PR is the deliverable.
open-gate B.3 implementation         # implicitly granted by the
                                     # same prompt body (queue
                                     # row #7); the next cron
                                     # tick after this PR merges
                                     # may ship it.
open-gate B.3 planner+reviewer cost  # NOT GRANTED — OQ-20
                                     # follow-up, v0.5 candidate.
```

Each step still respects the per-tick "one gate" rule. Opening
"B.3 contract" did not implicitly open "B.3 implementation" as
a same-tick deliverable; the queue's ordinal-#7 placement is
what gates that. The planner+reviewer cost extension requires a
fresh user signal and a separate contract amendment.
