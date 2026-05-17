"""Prompt builders for the B.9 interactive planner.

B.9c lets the builtin backend call the existing :class:`LLMProvider` to
turn the user's idea (plus optional feedback and prior draft) into a
B.6-compatible :class:`PlanDraft`. The prompt advertises the read-only
tool inventory descriptively; B.9c does not wire a turn-by-turn
tool-use loop. Parsing/validation happens in
:mod:`ai_cockpit.planner_interactive.backends.builtin`.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from ai_cockpit.planner_interactive.tools import PlannerTool

PLANNER_SYSTEM = (
    "You are the interactive planner inside AI Cockpit. Convert the "
    "user's idea into a small, B.6-compatible plan (schema_version 1) "
    "made of one or more vertical slices. Be concrete and conservative; "
    "each slice must fit within at most 8 files and 400 lines of code. "
    "Reply with strict JSON matching the schema the user describes — "
    "no markdown, no commentary, no prose around the JSON."
)

PLAN_DRAFT_SCHEMA: dict[str, object] = {
    "plan_id": "lowercase slug, 1-48 chars, [a-z0-9-]",
    "idea": "single-line restatement of the user's goal",
    "acceptance_criteria": ["short imperative bullets the saved plan must satisfy"],
    "slices": [
        {
            "id": "lowercase slug, unique within the plan",
            "title": "one-line title, <= 80 chars",
            "why": "2-5 lines of rationale",
            "scope_must": ["non-empty bullet list of must-do items"],
            "scope_out": ["non-empty bullet list of explicit out-of-scope items"],
            "dod": ["non-empty bullet list of done-criteria"],
            "files_budget": "integer in [1, 8]",
            "loc_budget": "integer in [1, 400]",
            "depends_on": ["zero or more earlier slice ids"],
            "test_commands": ["zero or more shell commands"],
        }
    ],
}


def build_planner_messages(
    *,
    idea: str,
    memory_context: str,
    tools: Iterable[PlannerTool],
    feedback: str | None = None,
    current_draft: object | None = None,
    worker_hints: list[str] | None = None,
    worker_name: str | None = None,
    system_override: str | None = None,
) -> tuple[str, str]:
    """Return ``(system, user)`` for a planner LLM call.

    ``worker_hints`` (B.2) is an optional list of human-summary strings
    from ``quirks_for(worker_name)``. The interactive REPL wiring
    (CLI ``ai-cockpit plan --worker <name>``) is a follow-up gate.

    ``system_override`` (B.4): replaces :data:`PLANNER_SYSTEM` verbatim
    when supplied; CLI loader validates first.

    Defaults keep every existing call site byte-identical.
    """

    from ai_cockpit.workers.quirks import format_worker_hints_block

    inventory = (
        "\n".join(f"- {t.name}: {t.description}" for t in tools)
        or "(none registered)"
    )
    parts: list[str] = [
        f"User idea:\n{idea.strip() or '(empty)'}",
        f"Memory context (may be empty):\n{memory_context.strip() or '(none)'}",
        "Read-only planner tools available (descriptive list only; you "
        f"cannot invoke them in this turn):\n{inventory}",
    ]
    if current_draft is not None:
        parts.append(
            "Current draft (revise rather than rewrite from scratch):\n"
            f"{json.dumps(current_draft, indent=2, ensure_ascii=False)}"
        )
    if feedback:
        parts.append(f"User feedback for this turn:\n{feedback.strip()}")
    hints_block = format_worker_hints_block(worker_hints, worker_name)
    if hints_block is not None:
        parts.append(hints_block)
    parts.append(
        "Reply with JSON exactly matching this schema (no commentary):\n"
        f"{json.dumps(PLAN_DRAFT_SCHEMA, indent=2)}"
    )
    system = system_override if system_override is not None else PLANNER_SYSTEM
    return system, "\n\n".join(parts)
