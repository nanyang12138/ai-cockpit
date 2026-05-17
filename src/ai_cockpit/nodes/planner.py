"""Planner node: produce an MVP spec from the user's idea.

By default the planner is a deterministic stub (v0.1 behavior). When an
``LLMProvider`` is supplied via ``make_planner_node(llm)``, the node will
ask the model for a structured JSON spec; if the call fails or the JSON
cannot be parsed, the deterministic stub is used as a safe fallback.
"""

from __future__ import annotations

import logging
import textwrap
from collections.abc import Callable

from ai_cockpit.llm import LLMProvider
from ai_cockpit.llm.prompts import build_planner_messages, parse_json_response
from ai_cockpit.state import TaskState
from ai_cockpit.workers.quirks import quirks_for

log = logging.getLogger(__name__)


def _condense(text: str, limit: int = 240) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _stub_plan(idea: str) -> dict[str, object]:
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
    return {
        "mvp_spec": mvp_spec,
        "acceptance_criteria": [
            "User can invoke the tool with a single command.",
            "Tool produces a structured artifact (spec, plan, or output) for the given idea.",
            "Tool reports verification evidence (git status/diff and at least one shell check).",
            "Tool exits with a clear pass/fail/ask-human decision.",
        ],
        "implementation_slice": (
            "Wire the smallest CLI entry point that loads context, calls the planner, "
            "runs a stub worker, collects verification evidence, and prints a summary. "
            "Defer any real code modification to a later iteration."
        ),
    }


def _llm_plan(
    llm: LLMProvider,
    idea: str,
    memory_context: str,
    *,
    worker_name: str | None = None,
) -> dict[str, object] | None:
    system, user = build_planner_messages(
        idea=idea,
        memory_context=memory_context,
        worker_hints=quirks_for(worker_name),
        worker_name=worker_name,
    )
    try:
        raw = llm.complete(system=system, user=user)
    except Exception as exc:  # noqa: BLE001 — LLM call site, must not crash the run
        log.warning("planner LLM call failed (%s); falling back to stub", exc)
        return None
    parsed = parse_json_response(raw)
    if not parsed:
        log.warning("planner LLM returned non-JSON; falling back to stub")
        return None

    mvp_spec = parsed.get("mvp_spec")
    acceptance = parsed.get("acceptance_criteria")
    slice_ = parsed.get("implementation_slice")
    if not isinstance(mvp_spec, str) or not isinstance(slice_, str):
        return None
    if not isinstance(acceptance, list) or not acceptance:
        return None
    return {
        "mvp_spec": mvp_spec.strip(),
        "acceptance_criteria": [str(c).strip() for c in acceptance if str(c).strip()],
        "implementation_slice": slice_.strip(),
    }


def make_planner_node(
    llm: LLMProvider | None,
    *,
    worker_name: str | None = None,
) -> Callable[[TaskState], TaskState]:
    """Return a planner node bound to an optional LLM provider.

    ``worker_name`` (B.2) is resolved at message-build time via
    ``quirks_for(worker_name)`` and appended as planner hints. Default
    ``None`` keeps every existing call site byte-identical (no hint
    block emitted).
    """

    def planner_node(state: TaskState) -> TaskState:
        idea = state.get("idea") or state.get("user_input") or ""
        memory_context = state.get("memory_context", "") or ""

        result: dict[str, object] | None = None
        if llm is not None:
            result = _llm_plan(
                llm, idea, memory_context, worker_name=worker_name
            )
        if result is None:
            result = _stub_plan(idea)

        return {
            "mvp_spec": result["mvp_spec"],  # type: ignore[typeddict-item]
            "acceptance_criteria": result["acceptance_criteria"],  # type: ignore[typeddict-item]
            "implementation_slice": result["implementation_slice"],  # type: ignore[typeddict-item]
        }

    return planner_node


def planner_node(state: TaskState) -> TaskState:
    """Back-compat: deterministic stub planner used when no LLM is wired."""

    return make_planner_node(None)(state)
