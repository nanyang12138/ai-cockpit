# v0.2 — Completion Record

Status: **functionally complete**.
Date: 2026-05-15.
Master tip on this date: `39ce91d` (Step 1 follow-up, PR #17).

This document archives the evidence that the v0.2 scope, as written in
`V0_2_PLAN.md`, has been delivered, and pins down the one carry-over to
v0.3 so nothing is lost.

## What v0.2 was supposed to deliver

From `docs/AI_COCKPIT_SPEC_V1.md` and `V0_2_PLAN.md` (in cron memory):

1. Real LLM-backed planner & reviewer behind a generic provider
   abstraction that works with enterprise proxies (Step 1).
2. SQLite checkpoint + thread resume so a run can survive process
   exit (Step 3).
3. The workflow YAML actually drives the graph instead of being
   decorative (Step 4).
4. A memory-suggestion loop that proposes diffs to
   `.ai-cockpit/memory/*.md` after a run, never applies them
   automatically; a `memory {list,show,accept}` CLI for the human
   (Step 5).
5. spec §9 anti-deception: the reviewer is fed only structured
   evidence (mvp_spec / acceptance_criteria / git_diff / git_status /
   verification_result) — never the coder self-report — and must
   refuse to pass when the evidence is empty.
6. spec §12 boundaries: no UI / no daemon / no cloud / no ruflo / no
   plugin marketplace.

Deferred from the start:

- Step 2 — Aider worker (needs a real LLM endpoint reachable from
  whatever environment runs `ai-cockpit`). Carried to v0.3.
- Step 6+ — OpenHands sandbox worker, browser verifier, PR-review
  workflow, Cursor SDK worker. Out of scope for v0.2.

## Shipped PRs (all merged into master)

| PR | Step | Title |
|----|------|-------|
| #5, #7, #9 | Step 1 | LLM-backed planner & reviewer |
| #10 | Step 3 | SQLite checkpoint + `--thread-id` / `--resume` |
| #12 | Step 3 follow-up | `--no-checkpoint` flag + boolean `--resume` |
| #13 | Step 4 | workflow YAML drives the graph |
| #14 | meta | `cursor-pr-automation` workflow (auto-open PR for cron pushes) |
| #15 | Step 5a | memory-suggestion library + post-run hook |
| #16 | Step 5b | `ai-cockpit memory {list,show,accept}` CLI |
| #17 | Step 1 follow-up | `LLM_API_EXTRA_HEADERS` for APIM-fronted gateways |

At master `39ce91d`: `pytest` 79 / 79 green, `ruff` clean, `mypy`
clean (27 source files), CLI smoke OK.

## spec §15 exit-gate evidence

spec §15 lists three scenarios. v0.2's stated exit gate was 15.1 and
15.3.

### §15.3 — "vague idea → spec/slice a human can accept" ✅ VERIFIED

Real-LLM run on user's AMD work laptop on 2026-05-15 at ~13:23 UTC,
against the enterprise proxy `https://llm-api.amd.com/Anthropic`
(`claude-opus-4-6`), with both Step 1 and Step 1 follow-up shipped:

```text
ai-cockpit "给 README 加一行说明本项目用 Python 3.12" \
    --llm auto --max-loops 1 --dry-run
```

Output (Claude-generated, not stub):

- **MVP Spec**: "Add a single line to the existing README file
  stating that this project requires Python 3.12+. The line should
  be placed in a logical location (e.g., near the top or in a
  Requirements/Prerequisites section if one exists). No other content
  changes are made."
- **Acceptance Criteria** (5 items, all task-specific):
  - `README.md` contains a clearly visible statement that the project
    uses Python 3.12+.
  - No existing README content is removed or altered.
  - The addition is a single line or short paragraph, not a new
    section unless no suitable section exists.
  - Lint passes: `ruff check .`.
  - File is valid Markdown with no formatting errors.
- **Implementation Slice**: "Append or insert the line
  `> Requires **Python 3.12+**` into `README.md` at the most logical
  position."

A human can pick up that slice and execute it directly. §15.3 passes.

### spec §9 — "reviewer must not be fooled" ✅ VERIFIED on real LLM

Same run, Review block:

```text
passed: False
risk:   high
issues:
- git_diff is empty — no changes were made to README.md
- git_status shows only untracked .ai-cockpit/suggestions/ directory,
  no modified files
- Acceptance criterion 'README.md contains a clearly visible statement
  that the project uses Python 3.12+' cannot be satisfied with no diff
- No verification commands were actually run to confirm any criteria
```

The reviewer is a real Claude call and was given **only** the
structured evidence dict (no `coder_result`). Despite the StubWorker's
upbeat `Coder Result` line, Claude correctly returned
`passed: False`, `risk_level: high`, and concrete `issues` pointing at
the empty diff. Decision dispatched to `ask_human`, never `done`.

This is the single most important property v0.2 had to establish:
**a real LLM reviewer cannot be talked into passing an empty diff**.
The four mock-LLM anti-deception tests in
`tests/test_llm_planner_reviewer.py` are how CI keeps this honest;
this run is how we proved the same property under a real model.

### §15.1 — "failing test → green via Step-2 worker" ⏭ CARRIED TO v0.3

§15.1 requires a real coder worker (Aider per `V0_2_PLAN.md`). Step 2
was deferred from the start of v0.2 because Aider in turn needs a
reachable LLM endpoint, and the Cloud Agent VM cron runs in cannot
reach the AMD enterprise proxy.

This is **not a v0.2 functional gap** — it is a deliberately deferred
step now carried to v0.3 with its existing contract from
`V0_2_PLAN.md` (Aider worker, `--worker {stub,aider}` flag, default
`--dry-run`, single `implementation_slice` per invocation, full
stdout/stderr capture, env-var passthrough).

## AMD APIM proxy — operational notes

Captured for future operators of the AMD-style enterprise gateway:

```text
URL:                 https://llm-api.amd.com/Anthropic/v1/messages
Required header:     Ocp-Apim-Subscription-Key: <subscription-key>
Optional:            x-api-key: <same key>   (allowed but not required)
Required:            anthropic-version: 2023-06-01
Wire format:         standard Anthropic Messages API
```

To make `ai-cockpit --llm auto` actually go through this gateway,
set (in addition to the standard generic envs):

```bash
export LLM_API_KEY=<your key>
export LLM_API_BASE=https://llm-api.amd.com/Anthropic
export LLM_MODEL_NAME=claude-opus-4-6
export LLM_API_EXTRA_HEADERS='{"Ocp-Apim-Subscription-Key": "<your key>"}'
```

`LLM_API_EXTRA_HEADERS` is a JSON object that is forwarded verbatim
to the underlying LangChain client as `default_headers`. No
provider's header name is hardcoded anywhere in `ai-cockpit`; the
same mechanism works for any future APIM-style gateway.

## v0.3 starting state

`V0_2_PLAN.md` Step 2 contract carries over unchanged.

Two small improvements observed during v0.2 exit validation, queued
as v0.3 nice-to-haves (each its own micro-step):

1. **Filter trivial memory suggestions.** Today the Step 5a hook
   writes a suggestion file on every run, including runs where
   `decision != done` and `git_diff` is empty. Such suggestions are
   pure noise in `ai-cockpit memory list`. The hook should skip a
   suggestion when the run produced no actionable knowledge.
2. **Workflow YAML coverage.** Step 4 made the YAML drive node order
   but only a single workflow ships. v0.3 could add 1-2 more
   workflows (e.g., a `bug-fix.yaml` aimed at §15.1) and assert via
   tests that each declared workflow can drive a graph.

Neither item is required to ship v0.3 Step 2 — they are independent
small steps that can interleave.

## Permanent boundaries (unchanged)

Per spec §12 and `AUTOMATION_PROMPT.md` §3.1:

- No UI, no web app, no daemon, no cloud execution backend, no
  multi-user / team permissions.
- No ruflo, swarm behavior, plugin marketplace, generic agent
  platform.
- No automatic emails, automatic Slack messages, or automatic PR
  comments outside the PR the agent itself opened.

These continue to hold throughout v0.3.
