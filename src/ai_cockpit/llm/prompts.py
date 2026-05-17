"""Prompt builders for planner and reviewer.

Hard rule (spec section 9 anti-deception): the reviewer prompt MUST be
built only from a structured evidence dict. The free-form ``coder_result``
self-report is intentionally excluded so the reviewer cannot be talked
into passing a failing run.
"""

from __future__ import annotations

import json
from typing import Any

PLANNER_SYSTEM = (
    "You are the planner inside AI Cockpit. Convert a user idea into a "
    "minimal MVP spec. Be concrete, conservative, and prefer the smallest "
    "vertical slice that proves the idea works. Reply with strict JSON "
    "matching the schema the user describes — no markdown, no commentary."
)

PLANNER_SCHEMA = {
    "mvp_spec": "string, 3-8 sentences",
    "acceptance_criteria": "array of 3-6 short imperative bullets",
    "implementation_slice": "string, the single smallest change to attempt first",
}

REVIEWER_SYSTEM = (
    "You are the reviewer inside AI Cockpit. Judge ONLY the structured "
    "evidence the user provides. Do NOT trust narrative summaries from "
    "anyone else. If verification commands failed, you MUST fail the "
    "review. Reply with strict JSON matching the schema — no markdown."
)

REVIEWER_SCHEMA = {
    "passed": "boolean",
    "issues": "array of short strings; empty if passed",
    "risk_level": "one of 'low', 'medium', 'high'",
    "suggested_fix": "string; short, actionable; empty if passed",
    "notes": "string; free-form context",
}


def build_planner_messages(
    *,
    idea: str,
    memory_context: str,
    system_override: str | None = None,
) -> tuple[str, str]:
    """Return (system, user) messages for the planner LLM call.

    ``system_override`` (B.4): when supplied, replaces
    :data:`PLANNER_SYSTEM` verbatim; CLI validates via
    :mod:`ai_cockpit.llm.prompts_override` first.
    """

    user = (
        "Memory context (may be empty):\n"
        f"{memory_context.strip() or '(none)'}\n\n"
        "User idea:\n"
        f"{idea.strip()}\n\n"
        "Reply with JSON of this exact shape:\n"
        f"{json.dumps(PLANNER_SCHEMA, indent=2)}"
    )
    system = system_override if system_override is not None else PLANNER_SYSTEM
    return system, user


def build_reviewer_evidence(state: dict[str, Any]) -> dict[str, Any]:
    """Extract the structured evidence dict for the reviewer prompt.

    Must NOT include ``coder_result`` (anti-deception rule).
    """

    verification = state.get("verification_result") or {}
    commands = list(verification.get("commands") or [])
    return {
        "mvp_spec": state.get("mvp_spec", ""),
        "acceptance_criteria": list(state.get("acceptance_criteria") or []),
        "git_status": verification.get("git_status", ""),
        "git_diff": verification.get("git_diff", ""),
        "verification": {
            "passed": bool(verification.get("passed", False)),
            "commands": [
                {
                    "command": c.get("command", ""),
                    "exit_code": int(c.get("exit_code", 0)),
                    "stdout_tail": (c.get("stdout") or "")[-2000:],
                    "stderr_tail": (c.get("stderr") or "")[-2000:],
                }
                for c in commands
            ],
        },
    }


def build_reviewer_messages(
    evidence: dict[str, Any],
    *,
    system_override: str | None = None,
) -> tuple[str, str]:
    """Return (system, user) messages for the reviewer LLM call.

    Caller must pass a dict from :func:`build_reviewer_evidence` so
    ``coder_result`` cannot leak in. ``system_override`` (B.4) replaces
    :data:`REVIEWER_SYSTEM` verbatim when supplied; the §9 allow-list
    is enforced by :mod:`ai_cockpit.llm.prompts_override` upstream.
    """

    user = (
        "Structured evidence (the only ground truth):\n"
        f"{json.dumps(evidence, indent=2, ensure_ascii=False)}\n\n"
        "Reply with JSON of this exact shape:\n"
        f"{json.dumps(REVIEWER_SCHEMA, indent=2)}"
    )
    system = system_override if system_override is not None else REVIEWER_SYSTEM
    return system, user


def parse_json_response(text: str) -> dict[str, Any] | None:
    """Best-effort JSON extraction from an LLM reply.

    Tolerates leading/trailing prose by locating the outermost ``{...}``.
    Returns ``None`` on failure so callers fall back to deterministic
    logic instead of raising.
    """

    if not text:
        return None
    stripped = text.strip()
    try:
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(stripped[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None
