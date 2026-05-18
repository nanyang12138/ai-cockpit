# V0.5 Row #11 — `chat-mode` contract (v0.1, DRAFT — Q-table pending user lock)

Status: **draft, NOT locked.** §3 Q1–Q8 record cron's recommendations;
user must lock (per row or "accept all cron recommendations") before
this document becomes the implementation gate.

> Pure-documentation deliverable: 2 files / ≤350 net LOC. No code
> under `src/`, no tests touched.

## 0. Origin

Surfaced **2026-05-18 06:46 UTC** during real-user-mode use, right
after row #10 sub-gate b shipped. Operator's verbatim:

> "我就是想看一下这个目录下面的状态 或者问一下问题 不可以吗？
> ... 但是我现在还不想跑我想先看一下状态"
>
> "其实我的想法就是我可以直接用ai-cockpit 把cursor 的交互模式调用进
> 来不就好了 我可以用cursor 也可以用自己的模式"

This is a **philosophical** gap (rows #1–#10 were graph-internal /
process / UX). ai-cockpit's existing modes (`run` / `plan` /
`plans run`) all commit the operator to producing an artefact;
there is no "low-commitment exploration" entry point. Cursor's
interactive mode already implements that experience; the right
design is to **invoke cursor's interactive mode through
ai-cockpit, NOT to reinvent a chat surface inside ai-cockpit**.

Per AUTOMATION_PROMPT §3.1, cron cannot self-add rows to ROADMAP.
This contract is the STOP-and-OQ response, drafted under the
user's 2026-05-18 07:08 UTC *"可以"* authorisation.

## 1. Why

Two complementary modes give the operator full coverage:

| Mode | Use when… |
|---|---|
| **Workflow** (`run` / `plan` / `plans run`, existing) | You have a concrete task with an acceptance criterion. Goal: code change + evidence trail. |
| **Chat** (this row, new) | You want to explore the project, ask questions, decide *whether* there's a task worth running. Goal: understanding, not artefacts. |

Without chat mode every interaction forces the workflow path.
Wrong default for "low-stakes exploration"; that's the
structural reason the operator asked *"我还不想跑我想先看一下状态"*.

Reusing cursor's interactive mode (rather than reinventing one)
gives: (a) one project / one CLI muscle memory; (b) consistent
config + LLM credentials; (c) automatic memory injection into
cursor's context; (d) cost auditability via the existing
`ai-cockpit cost` dashboard.

## 2. Hard invariants (cannot be overridden at implementation time)

| Invariant | Source | How row #11 honours it |
|---|---|---|
| §9 evidence-only reviewer | spec §9 | **chat mode has no reviewer.** The `decision` / `summary` / `reviewer` graph nodes do not run in chat mode. Reviewer prompt path is byte-identical to today; the 5-test §9 anti-deception suite stays untouched. |
| §3.2 memory write approval | hard rule §3.2 | **chat mode never writes to `.ai-cockpit/memory/*`.** Memory files are read-only inputs to cursor's context window; chat exit does NOT generate a suggestion JSON; `memory accept` is the only path to memory writes, unchanged. |
| §12 permanent boundaries | spec §12 | No daemon: cursor is a subprocess whose lifetime ends when the operator exits. No UI: it's a CLI subcommand that happens to be interactive (like `git rebase -i` or `vim`). No cloud, no swarm, no auto-outbound. |
| Chat exit ≠ workflow side-effects | this contract §3 Q4 | Whether or not chat mode lets cursor modify files (Q4 below), chat exit does NOT trigger planner / verifier / reviewer / memory pipeline. If the operator wants those, they run `ai-cockpit run` AFTER the chat session ends. |
| Subprocess-not-replace | this contract §3 Q5 | ai-cockpit `subprocess.run`s cursor (with stdin/stdout/stderr inherited) rather than `execvp`-replacing itself. Reason: ai-cockpit must remain the parent process so it can record session metadata + run cost-tracking on exit. |
| Backwards compatibility | EXECUTION_RULES | Existing 343-test baseline stays green. No CLI-flag signature change to `run` / `plan` / `plans run` / `status` / etc. |
| ≤8 files / ≤400 net LOC per PR | EXECUTION_RULES | Contract (this PR): 2 files / ≤350. Impl: split into a (CLI surface + cursor spawn) ≤4 files / ≤250 LOC, plus optional b (memory injection + cost logging) ≤4 / ≤200. Sub-gate split locked in §6. |

## 3. Open questions (cron recommendations — awaiting user lock)

| # | Question | Cron recommendation | User answer |
|---|---|---|---|
| Q1 | Chat read-only or writable? **(most important)** | **Read-only.** Chat exists for "low-commitment exploration". Cursor is spawned with `--read-only` if its CLI supports it; if not, ai-cockpit takes a `git stash` snapshot before chat starts and refuses to exit cleanly if the working tree changed without operator confirmation. Writable chat blurs the workflow/chat boundary and re-introduces the surprise-edit risk the row #10 dirty-tree precheck protects against. | |
| Q2 | Backend support in v0.1 | **`cursor` + `builtin`.** Sub-gate a ships `--backend cursor` (the headline shape). Sub-gate b is OPTIONAL and ships `--backend builtin` (direct LLM_API_KEY chat via the existing LLMProvider). Aider's interactive mode is NOT supported in v0.1 — aider's REPL is commit-flow-oriented, not chat-oriented, and supporting it would dilute the row's clarity. | |
| Q3 | One-shot vs interactive | **Both.** `ai-cockpit chat` (no args) opens interactive cursor; `ai-cockpit chat "<question>"` is one-shot Q&A (cursor answers + exits, no REPL). The same subcommand handles both shapes by checking whether positional args are present. | |
| Q4 | Memory injection mechanism | **System-prompt prepend.** All `.ai-cockpit/memory/*.md` files (concatenated, with a header line per file) are passed to cursor as a system prompt prefix via cursor's `--system-prompt` flag (or whatever cursor's equivalent is). Cap at 64 KB to protect against runaway memory growth; if memory total exceeds the cap, emit a stderr warning naming which files were truncated. | |
| Q5 | Process model | **`subprocess.run` with inherited stdin/stdout/stderr.** ai-cockpit stays the parent process. NO `os.execvp` replacement. Cursor's exit code propagates as ai-cockpit's exit code. | |
| Q6 | Cost tracking | **Yes, opt-out-able.** ai-cockpit writes one row to the cost-dashboard DB per chat session with `worker_name="chat"` so `ai-cockpit cost` reflects chat token spend alongside workflow token spend. Pass `--no-track-cost` to skip; default is to track. | |
| Q7 | Chat-session log retention | **`.ai-cockpit/history/chat.<thread-id>.log`.** ai-cockpit creates a thread id (same `new_thread_id()` it uses for workflow runs), and the cursor session's stderr is teed to this log for post-hoc operator review. Logs are gitignored under the existing `.ai-cockpit/history/` allow-list. NOT written to `memory/*`. | |
| Q8 | Chat → workflow handoff | **Out of scope for v0.5.** "I chatted, now I want to run the task we discussed" requires the operator to exit chat and invoke `ai-cockpit run` (or `ai-cockpit plan`) themselves. v0.1 explicitly does not implement an in-REPL "/run" command. Revisit in v0.6 if real-use demand surfaces. | |

## 4. Architecture

### 4.1 Process tree

```
operator's shell
  └── ai-cockpit chat [--backend cursor] [args...]      (PID P)
        ├── load_project_config()                      (in-process)
        ├── load_memory_files()                        (in-process, read-only)
        ├── compose_system_prompt()                    (in-process)
        ├── new_thread_id() + open chat log file       (in-process)
        └── subprocess.run(cursor-agent + injected args)  (PID C, child of P)
              ↑ cursor inherits stdin/stdout from operator's TTY
              ↓ stderr tee'd to chat log via wrapper
        on cursor exit:
        ├── write cost row (worker_name="chat")
        └── close chat log; print summary line
```

### 4.2 Memory injection (Q4)

`compose_system_prompt()` concatenates `.ai-cockpit/memory/*.md`
under per-file `## <path>` headers, framed with begin/end
markers, capped at 64 KB; over-cap files truncated alphabetically
with stderr warning naming them.

### 4.3 Read-only enforcement (Q1)

Two-layer: (1) primary — spawn cursor with its `--read-only`
flag (exact flag name verified at impl time); (2) fallback if
cursor lacks one — `git stash create` snapshot before chat,
`git status --porcelain` diff on exit, warn naming modified
paths. Fallback is suboptimal (post-hoc detection only); impl
MUST prefer primary and log which mode is in effect.

## 5. CLI surface

### 5.1 New subcommand `ai-cockpit chat`

```text
Usage: ai-cockpit chat [OPTIONS] [QUESTION]...

  Open an interactive Cursor session (or answer a one-shot
  question), with this project's config + memory pre-loaded.
  Chat mode is read-only by default; the workflow (`ai-cockpit
  run`) is the path to file modifications.

Options:
  --root DIRECTORY            Project root (default: .)
  --backend [cursor|builtin]  Where the chat runs.  [default: cursor]
  --no-track-cost             Skip the cost-dashboard row for this session.
  --binary TEXT               Pin a cursor binary name/path (overrides discovery).
  -h, --help                  Show this message and exit.
```

Behaviour:

- With QUESTION: one-shot. Cursor receives the system prompt +
  the question, prints the answer to stdout, exits. ai-cockpit
  exit code = cursor's exit code.
- Without QUESTION: interactive. Cursor opens its REPL with the
  system prompt loaded. Exits when operator types `/quit` or
  hits Ctrl-D.

### 5.2 `ai-cockpit status` interaction

`status` is extended (sub-gate b) to count chat sessions in the
`suggestions_pending` neighbourhood, e.g.:

```text
chat_sessions_logged: 3 (last: 2026-05-18T08:14:22Z)
```

If sub-gate b is not shipped, status does NOT mention chat.

## 6. File budget

**Contract (this PR):** 2 files / ≤350 net LOC.

- `docs/V0_5_ROW_11_CHAT_MODE_CONTRACT.md` (new — this file).
- `docs/V0_5_ROADMAP.md` (mod — add row #11 to Bucket A, update
  §1/§3/§4/§5/§6).

**Sub-gate a — chat subcommand + cursor backend (separate PR, NOT pre-authorised):** ≤4 files / ≤250 LOC.

- `src/ai_cockpit/cursor_adapter/chat.py` (new — spawn helper,
  read-only enforcement, memory injection composer; ~120 LOC).
- `src/ai_cockpit/cli.py` (mod — `chat` subcommand wiring;
  ~50 LOC).
- `src/ai_cockpit/memory/__init__.py` or sibling (mod — expose
  a `load_all_memory_for_context()` helper; ~20 LOC).
- `tests/test_chat_cursor.py` (new — spawn behaviour, memory
  injection composition, read-only enforcement; ~60 LOC).

**Sub-gate b — builtin backend + status integration + cost logging (separate PR, NOT pre-authorised):** ≤4 files / ≤200 LOC.

- `src/ai_cockpit/cursor_adapter/chat.py` (mod — add `builtin`
  branch using LLMProvider; ~50 LOC).
- `src/ai_cockpit/cost.py` (mod — accept `worker_name="chat"`
  rows; ~20 LOC).
- `src/ai_cockpit/cli.py` (mod — `status` chat-sessions row;
  ~20 LOC).
- `tests/test_chat_builtin.py` (new; ~80 LOC).

Sub-gate b strictly depends on a being merged.

## 7. Threat model

| Threat | Mitigation |
|---|---|
| Operator asks a question, cursor rewrites files anyway | Q1 read-only enforcement (cursor `--read-only` or git-stash snapshot fallback); modified paths reported to stderr on exit. |
| Stale `.ai-cockpit/memory/secrets.md` leaks into chat | Operator-managed; same trust model as `run` (which also reads memory). No new exposure surface. |
| Cursor binary not on PATH | `--binary` override; otherwise existing `probe_cursor_adapter` typed error, with `--backend builtin` fallback hint. |
| Memory injection > token budget | 64 KB cap, alphabetical truncation, stderr warning naming truncated files. |
| Dangling subprocess | `subprocess.run` blocks parent; SIGINT forwards to cursor by default. |
| Chat log fills `.ai-cockpit/history/` | Operator-managed; same model as workflow checkpoint DB. |
| Confusion `cursor` vs `ai-cockpit chat` | `--help` + README clarify it's a wrapper; operator can always bypass to bare `cursor`. |

## 8. DoD

**Contract (this PR) done when:**

1. This file merged to master.
2. `docs/V0_5_ROADMAP.md` Bucket A includes row #11 with pointer
   to this file. §1 framing reads "10 → 11 deficiencies".
3. Pre-push 4 checks pass.
4. No `src/`, no tests touched.

**Sub-gate a done (future PR after `open-gate v0.5-row-11-impl-a`) when:**

1. `ai-cockpit chat` subcommand ships, supports `--backend cursor`
   (default), `--root`, `--binary`, optional QUESTION arg.
2. Cursor is spawned via `subprocess.run` with memory injected as
   system prompt (Q4). Read-only enforced per Q1 with the chosen
   primary or fallback path.
3. New tests cover: spawn-with-args composition; memory injection
   composer + truncation; read-only flag presence / snapshot
   fallback; cursor-binary-missing graceful error.
4. ≤4 files / ≤250 LOC. 343-baseline test count unchanged or
   grown only by new chat tests.

**Sub-gate b done (future PR after `open-gate v0.5-row-11-impl-b` AND sub-gate a merged) when:**

1. `--backend builtin` works against the existing LLMProvider
   (no cursor binary needed).
2. `ai-cockpit cost` includes `worker_name="chat"` rows.
3. `ai-cockpit status` reports `chat_sessions_logged: N (last: ...)`.
4. ≤4 files / ≤200 LOC.

## 9. Out of scope for row #11

- **Chat → workflow handoff** (Q8): no `/run` REPL command in v0.5.
- **Aider interactive mode** as a backend (Q2): aider REPL is
  commit-flow-shaped, not chat-shaped; out of scope until
  demand surfaces.
- **Long-term chat memory** (chat session N remembering chat
  session N-1): each session starts from project memory + the
  current question. Cross-session continuity belongs to the
  operator (via memory accepts).
- **GUI / TUI**: cursor's CLI provides the UI. ai-cockpit does
  not add its own.
- **Multi-user chat / shared sessions**: §12 permanent
  boundary.
- **Cloud-hosted chat**: §12 permanent boundary.
- **In-chat memory.accept**: operator exits chat first, then
  runs `ai-cockpit memory accept` separately.

## 10. Rollback

If sub-gate a is harmful: revert. The `cursor` workflow worker
(`ai-cockpit run --worker cursor --apply`) is independent and
keeps working. Sub-gate b auto-blocks (depends on a).

If sub-gate b is harmful: revert. Cost dashboard and status
revert to pre-row-#11 shape; the chat subcommand from sub-gate
a still works with `--backend cursor` only.

## 11. Authorisation timeline

| When | Signal | Authorised action | Status |
|---|---|---|---|
| 2026-05-18 07:08 UTC | "可以" (in response to the open-roadmap + draft-contract proposal) | This PR: ROADMAP entry + this contract draft, doc-only | THIS PR |
| TBD | `open-gate v0.5-row-11-lock` (or "accept all cron recommendations verbatim") | Doc-only PR that flips status DRAFT→LOCKED and fills §3 User-answer column | not granted |
| TBD | `open-gate v0.5-row-11-impl-a` | Sub-gate a implementation PR | not granted |
| TBD | `open-gate v0.5-row-11-impl-b` | Sub-gate b implementation PR | not granted, depends on a merged |

## 12. Open-gate protocol

```text
open-gate v0.5-row-11-contract              # granted 2026-05-18 07:08 UTC;
                                            # THIS PR is the deliverable.
open-gate v0.5-row-11-lock                  # NOT granted — needs §3 Q1–Q8
                                            # answers (or "accept all cron
                                            # recommendations verbatim").
open-gate v0.5-row-11-impl-a                # NOT until row-11-lock merged.
open-gate v0.5-row-11-impl-b                # NOT until impl-a merged.

open-gate v0.5-row-11-writable-chat         # NEVER without §3 Q1 reversal
                                            # via amendment PR.
open-gate v0.5-row-11-aider-backend         # NEVER in v0.5; future row.
open-gate v0.5-row-11-in-chat-run-command   # NEVER in v0.5 (Q8 out-of-scope).
```

A future `open-gate v0.5-row-11-lock` signal must reference §3's
Q1–Q8 (with per-row answers or "accept all cron recommendations
verbatim"). Otherwise cron stops with an OQ per
`AUTOMATION_PROMPT.md` §4.

## 13. Cross-links

- **Surfacing chat:** 2026-05-18 06:46–07:08 UTC. Verbatim
  quotes in §0.
- **Closest sibling row:** row #10 (CLI ergonomics) — same
  "real-use surfaces a class of deficiency" pattern. Row #10
  closes "the CLI is hard to start"; row #11 closes "the
  workflow is the only mode".
- **Pre-existing cursor surface:** `src/ai_cockpit/cursor_adapter/`
  (B.10 planner/worker/reviewer/writer backends + discovery).
  Row #11 adds `chat.py` to that package; same trust model.
- **Spec invariants:** `docs/AI_COCKPIT_SPEC_V1.md` §9 / §3.2 /
  §12 (all honoured by the read-only chat + no-memory-write
  posture).
