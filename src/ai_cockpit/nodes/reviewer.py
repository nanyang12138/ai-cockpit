"""Reviewer node: judges based on collected evidence, not coder summaries.

Hard rules (spec section 9 anti-deception):
- If any verification command failed, the review fails — no LLM can
  override this.
- The LLM, when wired, only ever sees a structured evidence dict; the
  free-form ``coder_result`` self-report is intentionally excluded.
- If a stub/dry-run produced no diff and no test commands, that's allowed
  but flagged as a clear note.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ai_cockpit.llm import LLMProvider
from ai_cockpit.llm.prompts import (
    build_reviewer_evidence,
    build_reviewer_messages,
    parse_json_response,
)
from ai_cockpit.state import ReviewResult, TaskState

log = logging.getLogger(__name__)


def _deterministic_review(state: TaskState) -> ReviewResult:
    verification = state.get("verification_result")
    issues: list[str] = []
    notes_parts: list[str] = []
    risk: str = "low"

    if verification is None:
        return {
            "passed": False,
            "issues": ["No verification_result available; cannot review."],
            "risk_level": "high",
            "suggested_fix": "Re-run the verifier node before review.",
            "notes": "",
        }

    commands = verification.get("commands", [])
    failed = [c for c in commands if c["exit_code"] != 0]
    if failed:
        for c in failed:
            issues.append(f"Command failed (exit={c['exit_code']}): {c['command']!s}")
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
    return {
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


def _normalize_risk(value: object) -> str:
    if isinstance(value, str) and value.lower() in {"low", "medium", "high"}:
        return value.lower()
    return "medium"


def _llm_review(llm: LLMProvider, state: TaskState) -> ReviewResult | None:
    evidence = build_reviewer_evidence(dict(state))
    system, user = build_reviewer_messages(evidence)
    try:
        raw = llm.complete(system=system, user=user)
    except Exception as exc:  # noqa: BLE001 — LLM call site, must not crash the run
        log.warning("reviewer LLM call failed (%s); falling back to deterministic", exc)
        return None
    parsed = parse_json_response(raw)
    if not parsed:
        log.warning("reviewer LLM returned non-JSON; falling back to deterministic")
        return None

    issues_raw = parsed.get("issues") or []
    if not isinstance(issues_raw, list):
        return None

    review: ReviewResult = {
        "passed": bool(parsed.get("passed", False)),
        "issues": [str(i) for i in issues_raw],
        "risk_level": _normalize_risk(parsed.get("risk_level")),  # type: ignore[typeddict-item]
        "suggested_fix": str(parsed.get("suggested_fix", "")),
        "notes": str(parsed.get("notes", "")),
    }
    return review


def _enforce_hard_rules(review: ReviewResult, state: TaskState) -> ReviewResult:
    """Override LLM verdict if verification commands failed.

    The LLM is never trusted to pass a run whose verifier reports a
    non-zero exit code. This is the spec section 9 anti-deception floor.
    """

    verification: dict[str, Any] = dict(state.get("verification_result") or {})
    commands = verification.get("commands") or []
    failed = [c for c in commands if int(c.get("exit_code", 0)) != 0]
    if not failed:
        return review

    issues = list(review.get("issues") or [])
    for c in failed:
        marker = f"exit={c.get('exit_code')}"
        if not any(marker in i for i in issues):
            issues.append(f"Command failed (exit={c.get('exit_code')}): {c.get('command')!s}")

    return {
        "passed": False,
        "issues": issues,
        "risk_level": "high",
        "suggested_fix": (
            review.get("suggested_fix")
            or "Fix the failing verification command before re-review."
        ),
        "notes": review.get("notes", ""),
    }


def make_reviewer_node(llm: LLMProvider | None) -> Callable[[TaskState], TaskState]:
    """Return a reviewer node bound to an optional LLM provider."""

    def reviewer_node(state: TaskState) -> TaskState:
        review: ReviewResult | None = None
        if llm is not None:
            review = _llm_review(llm, state)
        if review is None:
            review = _deterministic_review(state)

        review = _enforce_hard_rules(review, state)
        return {"review_result": review}

    return reviewer_node


def reviewer_node(state: TaskState) -> TaskState:
    """Back-compat: deterministic reviewer used when no LLM is wired."""

    return make_reviewer_node(None)(state)
