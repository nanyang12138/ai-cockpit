"""Summary node: render the final human-readable report."""

from __future__ import annotations

from typing import Any

from ai_cockpit.state import TaskState


def _render_commands(commands: list[dict[str, Any]]) -> str:
    if not commands:
        return "  (no verification commands ran)"
    lines = []
    for c in commands:
        status = "ok" if c["exit_code"] == 0 else f"FAIL ({c['exit_code']})"
        lines.append(f"  - [{status}] {c['command']}")
    return "\n".join(lines)


def render_summary(state: TaskState) -> str:
    """Build the final summary string from accumulated state."""

    review: dict[str, Any] = dict(state.get("review_result") or {})
    verification: dict[str, Any] = dict(state.get("verification_result") or {})
    decision = state.get("decision", "ask_human")
    criteria = state.get("acceptance_criteria") or []
    issues = review.get("issues") or []
    notes = review.get("notes") or ""

    criteria_block = "\n".join(f"  - {c}" for c in criteria) or "  (none)"
    issues_block = "\n".join(f"  - {i}" for i in issues) or "  (none)"
    commands_block = _render_commands(list(verification.get("commands") or []))

    git_status = (verification.get("git_status") or "").rstrip()
    if not git_status:
        git_status = "  (clean working tree)"
    else:
        git_status = "\n".join(f"  {line}" for line in git_status.splitlines())

    parts = [
        "=" * 72,
        "AI Cockpit — Run Summary",
        "=" * 72,
        f"Mode:        {state.get('mode', 'exploration')}",
        f"Loops:       {state.get('loop_count', 0)} / {state.get('max_loops', 1)}",
        f"Decision:    {decision}",
        "",
        "Idea:",
        f"  {state.get('idea', '') or state.get('user_input', '')}",
        "",
        "MVP Spec:",
        *("  " + line for line in (state.get("mvp_spec") or "").splitlines()),
        "",
        "Acceptance Criteria:",
        criteria_block,
        "",
        "Implementation Slice:",
        f"  {state.get('implementation_slice', '')}",
        "",
        "Coder Result:",
        *("  " + line for line in (state.get("coder_result") or "").splitlines()),
        "",
        "Verification:",
        f"  passed: {verification.get('passed', False)}",
        commands_block,
        "  git status --short:",
        git_status,
        "",
        "Review:",
        f"  passed: {review.get('passed', False)}",
        f"  risk:   {review.get('risk_level', 'unknown')}",
        "  issues:",
        issues_block,
    ]
    if notes:
        parts += ["  notes:", f"    {notes}"]
    suggested = review.get("suggested_fix") or ""
    if suggested:
        parts += ["  suggested_fix:", f"    {suggested}"]

    parts += ["", "=" * 72, ""]
    return "\n".join(parts)


def summary_node(state: TaskState) -> TaskState:
    text = render_summary(state)
    print(text)
    return {"final_summary": text}
