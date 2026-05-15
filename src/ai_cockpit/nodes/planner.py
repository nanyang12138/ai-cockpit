"""Planner node: deterministic stub that produces an MVP spec.

v0.1 does not call an LLM. The output is structured, derived from the
user's idea, and shaped so a real LLM-backed planner can drop in later.
"""

from __future__ import annotations

import textwrap

from ai_cockpit.state import TaskState


def _condense(text: str, limit: int = 240) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def planner_node(state: TaskState) -> TaskState:
    """Produce ``mvp_spec``, ``acceptance_criteria``, ``implementation_slice``."""

    idea = state.get("idea") or state.get("user_input") or ""
    condensed = _condense(idea) or "(no idea provided)"

    mvp_spec = textwrap.dedent(
        f"""
        MVP goal: {condensed}

        Constraints:
        - Smallest end-to-end vertical slice that proves the idea is workable.
        - No premature abstraction; defer plugins, UI, and integrations.
        - Surface failures loudly; never fake success.
        """
    ).strip()

    acceptance_criteria = [
        "User can invoke the tool with a single command.",
        "Tool produces a structured artifact (spec, plan, or output) for the given idea.",
        "Tool reports verification evidence (git status/diff and at least one shell check).",
        "Tool exits with a clear pass/fail/ask-human decision.",
    ]

    implementation_slice = (
        "Wire the smallest CLI entry point that loads context, calls the planner, "
        "runs a stub worker, collects verification evidence, and prints a summary. "
        "Defer any real code modification to a later iteration."
    )

    return {
        "mvp_spec": mvp_spec,
        "acceptance_criteria": acceptance_criteria,
        "implementation_slice": implementation_slice,
    }
