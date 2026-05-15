# Automation Prompt: Build AI Cockpit v0.1

You are a coding automation agent working in this repository.

Your job is to implement the first runnable version of AI Cockpit, based on:

- `docs/AI_COCKPIT_SPEC_V1.md`
- `docs/AI_COCKPIT_IMPLEMENTATION_PLAN_V0.md`

## Goal

Build a minimal, safe, runnable vertical slice:

```text
idea input
-> load memory
-> planner creates MVP spec
-> coder stub executes
-> verifier collects git diff/status and runs shell checks
-> reviewer evaluates evidence
-> decision chooses done/retry/ask_human
-> summary prints final result
```

This is not a full platform. Do not build UI, plugins, cloud execution, daemon processes, or ruflo integration.

## Required Tech Direction

Use Python.

Use LangGraph for the workflow if practical. If dependency setup blocks progress, create a clean internal graph abstraction first, but keep the code shaped so LangGraph can replace it easily.

Do not integrate OpenHands, Cursor SDK, Aider, or Claude Code in v0.1. Implement a `StubWorker` first so the workflow can run end-to-end safely.

## Required Files / Structure

Create a Python project with this shape:

```text
pyproject.toml
README.md
.ai-cockpit/
  memory/
    user.md
    project.md
    preferences.md
  workflows/
    idea-to-mvp.yaml
  history/
src/
  ai_cockpit/
    __init__.py
    cli.py
    config.py
    state.py
    graph.py
    nodes/
      __init__.py
      intake.py
      planner.py
      coder.py
      verifier.py
      reviewer.py
      decision.py
      summary.py
    workers/
      __init__.py
      base.py
      stub_worker.py
    tools/
      __init__.py
      git.py
      shell.py
    memory/
      __init__.py
      loader.py
tests/
  test_graph_smoke.py
  test_verifier.py
```

Adjust only if there is a clear reason.

## Functional Requirements

The CLI must support:

```bash
ai-cockpit "I want to build a tool that turns vague ideas into MVP specs"
```

Optional flags:

```bash
--root .
--max-loops 1
--mode exploration
--test-command "python -m pytest"
--dry-run
```

The first version may use deterministic stub outputs for planner/reviewer, but it must pass state through the full workflow.

## State Model

Implement a typed state object containing at least:

```text
user_input
mode
project_root
memory_context
idea
mvp_spec
acceptance_criteria
implementation_slice
coder_result
git_diff
git_status
verification_result
review_result
decision
loop_count
max_loops
final_summary
```

## Node Responsibilities

`intake`

- Read user input.
- Load memory files from `.ai-cockpit/memory/` if present.
- Default mode to `exploration`.

`planner`

- Produce a concise MVP spec.
- Produce acceptance criteria.
- Choose one minimal implementation slice.
- Stub output is acceptable in v0.1.

`coder`

- Use `StubWorker`.
- Do not modify code in v0.1 unless explicitly configured later.
- Return a clear `coder_result`.

`verifier`

- Run `git status --short`.
- Run `git diff`.
- Run user-provided test commands if present.
- Preserve command exit code, stdout, and stderr.

`reviewer`

- Judge based on evidence, not coder self-report.
- If verification commands fail, review should fail.
- If no code changes were expected because dry-run/stub mode is active, it can pass with a clear note.

`decision`

- If review passes, choose `done`.
- If review fails and `loop_count < max_loops`, choose `retry`.
- Otherwise choose `ask_human`.
- Do not allow infinite loops.

`summary`

- Print final result.
- Include MVP spec, acceptance criteria, verification result, review result, and decision.

## Safety Rules

Do not:

- delete files
- edit secrets
- install global packages
- start long-running daemons
- add ruflo
- implement swarm behavior
- push directly to `master`
- force push
- bypass branch protection
- merge manually without checks

Keep all changes small and reviewable.

## GitHub Delivery Workflow

This repository requires changes to go through pull requests. After implementation and tests:

1. Create a feature branch from the latest `master`.
2. Use a branch name that starts with `cursor/`, for example:

```bash
cursor/build-v0.1-agent-loop
```

3. Commit the implementation with a concise message.
4. Push the branch to `origin`.
5. Create a pull request targeting `master`.
6. Enable auto-merge for the PR if the environment supports it.
7. Do not manually merge unless auto-merge is unavailable and the user explicitly approves.

Preferred commands when GitHub CLI is available:

```bash
git switch -c cursor/build-v0.1-agent-loop
git add .
git commit -m "<message>"
git push -u origin HEAD
gh pr create --base master --head cursor/build-v0.1-agent-loop --title "<title>" --body "<summary>"
gh pr merge --auto --squash
```

If GitHub CLI is unavailable, push the branch and report the PR creation URL:

```text
https://github.com/nanyang12138/ai-cockpit/pull/new/<branch-name>
```

The repository also contains an auto-merge workflow. Auto-merge only applies after the `validate` workflow succeeds and the branch name matches `cursor/*`.

## Tests

Add focused tests:

- smoke test that the graph runs end-to-end with stub worker
- verifier test that shell command results are captured
- memory loader test if simple

Use the repo's chosen test runner.

## Acceptance Criteria

The work is complete when:

- `ai-cockpit "some idea"` runs locally.
- The workflow reaches summary.
- State is passed through every node.
- Git status/diff are captured.
- At least one verification command can run.
- Reviewer returns structured pass/fail.
- Decision respects `max_loops`.
- Tests pass.

## Output Expected From You

After implementation, report:

- What was built.
- How to run it.
- What tests were run.
- Known limitations.
- Recommended next step.

