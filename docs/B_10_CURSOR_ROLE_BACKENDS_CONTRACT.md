# B.10 — Cursor-backed Role Backends (contract v0.1)

Status: **contract authored, awaiting user open-gate signal.** This
document captures the 2026-05-16 decision that Cursor should be treated
as a high-capability agent engine inside `ai-cockpit`, not as something
`ai-cockpit` tries to replace.

> Until the user explicitly says "open-gate B.10a" (or equivalent), no
> source code under `src/` may be modified in service of B.10.

## 1. Core decision

The desired architecture is:

```text
ai-cockpit Manager / Controller
  -> Cursor-backed Planner Agent
  -> Cursor-backed Worker Agent
  -> deterministic Verifier
  -> Cursor-backed Reviewer Agent
  -> ai-cockpit Decision / Memory / Summary
```

Cursor provides agent capability: repository understanding, planning,
code editing, and natural-language critique.

`ai-cockpit` provides the operating layer:

- workflow state machine;
- policy and scope boundaries;
- memory read/write rules;
- evidence collection;
- deterministic verification;
- retry / stop / ask-human decisions;
- audit artifacts (`plan.yaml`, run summaries, git commits);
- provider/backend selection.

The rule is:

> Cursor does the thinking and code-work for a role; `ai-cockpit`
> controls when that role runs, what evidence it sees, what it may
> write, and what counts as success.

## 2. Why this is not "replace ai-cockpit with Cursor"

Cursor is already strong at local repository reasoning and coding. The
project should use that strength instead of reimplementing it badly.

But Cursor alone does not provide this project's hard guarantees:

- §9 reviewer evidence isolation;
- §3.2 memory write approval;
- explicit plan artifacts under `docs/plans/`;
- deterministic verifier output;
- per-slice budgets;
- stable workflow templates;
- backend fallback when Cursor is unavailable;
- small, auditable PR-sized changes.

B.10 therefore makes Cursor a **role backend**, not the product's
manager.

## 3. Hard invariants

| Invariant | Source | How B.10 honors it |
| --- | --- | --- |
| Manager stays in `ai-cockpit` | project architecture | Cursor roles are invoked by `ai-cockpit`; they do not call each other directly. |
| Verifier stays deterministic | spec §9 | Tests, lint, typecheck, git diff, and git status are collected by `ai-cockpit`, not trusted from Cursor prose. |
| Reviewer sees evidence only | spec §9 | Cursor Reviewer backend receives the same evidence bundle as the current LLM reviewer. It never receives Cursor Worker self-report as positive evidence. |
| Memory not auto-written | spec §3.2 | Cursor may suggest memory changes only through existing suggestion files; `memory accept` remains the only writer to `.ai-cockpit/memory/*`. |
| No swarm / no agent-to-agent bus | spec §12 | Planner, Worker, Reviewer, Writer are roles invoked serially by the controller. They do not chat with each other. No A2A server. |
| No mandatory Cursor dependency | generic provider principle | Cursor backend is optional. Builtin / existing backends remain usable. |
| No hidden source writes from planning/review | B.9 + §9 | Cursor Planner and Cursor Reviewer are read-only roles. Only Cursor Worker may modify source, and only through explicit apply semantics. |
| No blind trust in `--yolo` | safety | Any Cursor invocation that requires trust/yolo must be wrapped by explicit `ai-cockpit` guardrails and documented user consent. |

## 4. Role map

| Role | Cursor-backed? | Notes |
| --- | --- | --- |
| Manager / Controller | No | Remains Python + LangGraph / CLI logic. This role enforces boundaries and sequencing. |
| Planner | Yes | Cursor Plan Mode / interactive Cursor Agent can help clarify and form `plan.yaml`. |
| Worker / Coder | Yes | Cursor can be a `Worker` implementation beside `stub` and `aider`. |
| Verifier | No | Must stay deterministic shell/git/test collection. |
| Reviewer | Yes, with strict evidence input | Cursor can critique diff/test evidence, but cannot see worker self-report as proof. |
| Writer / Summary | Yes, optional | Cursor can draft human-readable summaries, but must not send Slack/email/PR comments automatically. |

## 5. Cursor Planner backend

This is the user's highest-priority Cursor use case: bring Cursor's
interactive planning ability into `ai-cockpit`.

Target UX:

```bash
ai-cockpit plan "complex idea" --backend cursor
```

Behavior:

1. `ai-cockpit` starts an interactive planning session.
2. Cursor is allowed to inspect the repository and ask clarifying
   questions.
3. The user discusses and revises the plan.
4. Cursor proposes structured plan content.
5. `ai-cockpit` validates and saves `docs/plans/<plan_id>.plan.yaml`
   only after the user explicitly accepts `/save`.

Important distinction:

- `agent --print` was experimentally observed to return first-turn
  progress narration, not reliable completed plan artifacts.
- Therefore B.10 must not depend on `agent --print` as the main planner
  path.
- Cursor Planner integration should be interactive-first, likely using
  a subprocess/PTY session or a future stable Cursor SDK/API if one is
  available.

## 6. Cursor Worker backend

Cursor Worker is the code-writing role.

Future CLI shape:

```bash
ai-cockpit run "idea" --worker cursor --apply
ai-cockpit plans run <plan_id> <slice_id> --worker cursor --apply
```

Rules:

- Without `--apply`, Cursor Worker is preview-only.
- With `--apply`, `ai-cockpit` must run the same dirty-tree guard used
  for Aider.
- Cursor receives a controlled task package:
  - objective;
  - implementation slice;
  - acceptance criteria;
  - scope constraints;
  - forbidden actions;
  - test commands to expect;
  - maximum-change guidance.
- Cursor Worker output is treated as self-report. It may be logged, but
  it is not verification evidence.
- `ai-cockpit` still runs verifier after Cursor returns.

Open implementation risk:

Cursor CLI's exact non-interactive "run until done" semantics must be
probed before this role ships. If the local `agent` binary only supports
interactive completion reliably, Cursor Worker may need to be an
interactive apply mode first, not an autonomous worker.

## 7. Cursor Reviewer backend

Cursor Reviewer is allowed, but only under the existing §9 evidence
contract.

Future CLI shape:

```bash
ai-cockpit run "idea" --reviewer cursor
```

Input allowed:

- `mvp_spec`;
- `acceptance_criteria`;
- `git_status`;
- `git_diff`;
- verifier command names, exit codes, stdout/stderr tails.

Input forbidden:

- Cursor Worker self-report as proof;
- Aider Worker self-report as proof;
- planner conversation transcript;
- planner tool outputs;
- plan prose that claims a slice is easy/trivial;
- memory suggestions not accepted by the user.

Reviewer output must be parsed into the existing review shape:

```yaml
passed: true|false
risk: low|medium|high
issues:
  - ...
suggested_fix: ...
notes: ...
```

The existing deterministic hard-rule floor still wins. If tests fail,
Cursor Reviewer cannot pass the run.

## 8. Cursor Writer backend

Cursor may later draft summaries, PR descriptions, or status reports.

Hard boundary:

- It may write local draft text.
- It may not post Slack/email/PR comments automatically.
- Any external posting remains out of scope unless a future contract
  explicitly changes spec §12, which current rules forbid.

## 9. Backend discovery and compatibility

B.10 must start with a discovery step because Cursor's CLI name and
supported flags may vary by installation.

Observed by the user on 2026-05-16:

- local binary name: `agent`;
- supported `--mode` values included `plan` and `ask`;
- invalid: `--mode=agent`;
- `--print --output-format=json` produced JSON envelopes but did not
  reliably complete complex planning tasks;
- interactive runs exposed resumable session IDs;
- workspace trust may require an explicit trust/yolo flag.

B.10a should implement a read-only probe:

```bash
ai-cockpit cursor status
```

It should report:

- binary path chosen (`agent`, `cursor-agent`, or configured path);
- version, if available;
- supported modes, if discoverable;
- whether `--print --output-format=json` works for trivial ask;
- whether workspace trust is required;
- whether a resume/session flag is advertised.

Tests must use fake binaries on PATH, not the real Cursor CLI.

## 10. Relationship to B.9

B.9 introduced the interactive planner shell and reserved
`--backend cursor`.

B.10 broadens that idea:

- B.9 is the UX shell for planning.
- B.10 defines Cursor as a family of role backends.
- If B.10 is accepted, the old "B.9d Cursor backend" should be
  implemented as B.10b Cursor Planner backend, not as an ad-hoc one-off.

In other words:

```text
B.9a-c: generic interactive planner shell + builtin backend
B.10a: Cursor CLI discovery / adapter foundation
B.10b: Cursor Planner backend for B.9
B.10c: Cursor Worker backend
B.10d: Cursor Reviewer backend
B.10e: optional Cursor Writer backend
```

## 11. Implementation split

Each PR must stay within the project cap: at most 8 files changed and
at most 400 net LOC.

### B.10a — Cursor adapter discovery

Estimated 5 files / 300 net LOC.

- `src/ai_cockpit/cursor_adapter/__init__.py`
- `src/ai_cockpit/cursor_adapter/discovery.py`
- `src/ai_cockpit/cli.py` (`ai-cockpit cursor status`)
- `tests/test_cursor_adapter.py`
- README or ROADMAP note if needed

No planning, coding, or reviewing yet. This PR only learns what local
Cursor integration surface is available.

### B.10b — Cursor Planner backend

Estimated 5 files / 350 net LOC.

- Cursor backend implementation for the B.9 planner protocol.
- Interactive session bridge.
- Save remains through B.9 `/save` and plan validation.
- Tests with a fake Cursor process/session transcript.

### B.10c — Cursor Worker backend

Estimated 6 files / 350 net LOC.

- `Worker` implementation named `cursor`.
- Preview-only by default; `--apply` required for writes.
- Dirty-tree guard shared with Aider.
- Fake Cursor binary tests for success/failure/self-report capture.

### B.10d — Cursor Reviewer backend

Estimated 5 files / 300 net LOC.

- Reviewer backend selector (`builtin` / existing LLM / `cursor`) if
  not already present.
- Evidence-only prompt construction.
- JSON/YAML review verdict parser.
- Anti-deception tests proving worker self-report and planner transcript
  are absent from Cursor Reviewer input.

### B.10e — Cursor Writer backend (optional)

Estimated 3 files / 180 net LOC.

- Draft-only summary/PR-description writer.
- No external posting.
- Tests for local output only.

## 12. Threat model

| Threat | Mitigation |
| --- | --- |
| Cursor role starts editing during planning | Planner backend is interactive/read-only; only `/save` writes plan YAML. |
| Cursor Worker modifies user WIP | Reuse dirty-tree pre-check; require `--apply`; preview-only default. |
| Cursor Reviewer is persuaded by Cursor Worker prose | §9 input builder excludes worker self-report; anti-deception tests pin this. |
| Cursor becomes mandatory | Builtin/stub/Aider paths remain; Cursor adapter reports unavailable cleanly. |
| Cursor CLI flags change | B.10a discovery isolates version/flag probing and tests fake binaries. |
| Workspace trust/yolo hides dangerous permissions | `ai-cockpit` surfaces trust mode explicitly and refuses hidden escalation. |
| Agent-to-agent swarm creep | Roles are serial calls from manager; no peer messaging, no A2A server. |
| External side effects | Cursor Writer drafts locally only; no Slack/email/PR posting. |

## 13. DoD

B.10 is done only when:

1. `ai-cockpit cursor status` reports local Cursor availability without
   real side effects.
2. `ai-cockpit plan ... --backend cursor` can run an interactive Cursor
   planning session and save a validated plan artifact.
3. `--worker cursor` can run in preview mode and, with `--apply`, modify
   files only after dirty-tree checks.
4. Cursor Reviewer receives only evidence and passes all §9
   anti-deception tests.
5. Cursor unavailable / unsupported CLI produces clear errors and
   suggests builtin or Aider fallback.
6. All standard checks pass: `pytest`, `ruff check .`, `mypy .`, and
   the smoke command with `--llm none --no-checkpoint`.

## 14. Out of scope

- No A2A protocol server.
- No generic agent marketplace.
- No swarm where Cursor agents talk directly to each other.
- No mandatory Cursor dependency.
- No automatic external posting.
- No background daemon.
- No UI beyond terminal interaction.
- No memory writes outside `memory accept`.

## 15. Authorization

B.10 is specified but not open for implementation.

Open-gate sequence:

```text
open-gate B.10a
open-gate B.10b
open-gate B.10c
open-gate B.10d
open-gate B.10e
```

Each step requires an explicit user instruction. Opening B.10a does not
implicitly authorize B.10b or later.
