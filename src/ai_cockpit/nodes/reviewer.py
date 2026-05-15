"""Reviewer node: judges based on collected evidence, not coder summaries.

Hard rules:
- If any verification command failed, the review fails.
- If a stub/dry-run produced no diff and no test commands, that's allowed
  but flagged as a clear note.
- Acceptance criteria are echoed back so a future LLM-backed reviewer can
  reason over them; the v0.1 deterministic logic only checks evidence.
"""

from __future__ import annotations

from ai_cockpit.state import ReviewResult, TaskState


def reviewer_node(state: TaskState) -> TaskState:
    """Produce a structured `ReviewResult` from verification evidence."""

    verification = state.get("verification_result")
    issues: list[str] = []
    notes_parts: list[str] = []
    risk: str = "low"

    if verification is None:
        review: ReviewResult = {
            "passed": False,
            "issues": ["No verification_result available; cannot review."],
            "risk_level": "high",
            "suggested_fix": "Re-run the verifier node before review.",
            "notes": "",
        }
        return {"review_result": review}

    commands = verification.get("commands", [])
    failed = [c for c in commands if c["exit_code"] != 0]
    if failed:
        for c in failed:
            issues.append(
                f"Command failed (exit={c['exit_code']}): {c['command']!s}"
            )
        risk = "high"

    diff = verification.get("git_diff", "") or ""
    has_diff = bool(diff.strip())
    dry_run = bool(state.get("dry_run", False))
    coder_result = state.get("coder_result", "") or ""
    is_stub = coder_result.startswith("Stub worker:")

    if not has_diff and not commands:
        if dry_run or is_stub:
            notes_parts.append(
                "No diff and no verification commands — acceptable because "
                "stub/dry-run mode is active. Reviewer cannot prove progress; "
                "only confirms the workflow ran end-to-end."
            )
        else:
            issues.append("No diff produced and no verification commands ran.")
            risk = "medium"

    if has_diff and not commands:
        notes_parts.append(
            "Diff exists but no test commands were configured. Reviewer "
            "cannot verify behavior; consider passing --test-command."
        )
        if risk == "low":
            risk = "medium"

    passed = len(issues) == 0

    review = {
        "passed": passed,
        "issues": issues,
        "risk_level": risk,  # type: ignore[typeddict-item]
        "suggested_fix": (
            "Re-run with a real worker and provide --test-command "
            "for meaningful verification."
        )
        if not passed or is_stub or dry_run
        else "",
        "notes": " ".join(notes_parts).strip(),
    }
    return {"review_result": review}  # type: ignore[dict-item]
