"""Decision node: chooses ``done`` / ``retry`` / ``ask_human``.

Loop control is enforced here so no other node can introduce an infinite
loop. The accompanying `route_after_decision` callable is what the graph
uses to pick the next edge.
"""

from __future__ import annotations

from ai_cockpit.state import Decision, TaskState


def decision_node(state: TaskState) -> TaskState:
    review = state.get("review_result")
    loop_count = int(state.get("loop_count", 0) or 0)
    max_loops = int(state.get("max_loops", 1) or 1)

    decision: Decision
    if review and review.get("passed"):
        decision = "done"
    elif loop_count < max_loops:
        decision = "retry"
    else:
        decision = "ask_human"

    return {"decision": decision}


def route_after_decision(state: TaskState) -> str:
    """Pick the next graph edge based on the recorded decision."""

    decision = state.get("decision", "ask_human")
    if decision == "retry":
        return "coder"
    return "summary"
