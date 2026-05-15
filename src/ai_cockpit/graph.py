"""LangGraph wiring for the v0.1 idea-to-MVP execution loop.

We use ``langgraph.graph.StateGraph`` so the graph is explicit, auditable,
and easy to extend. The state-merge behavior is the LangGraph default
(per-key overwrite), which matches our `TaskState` total=False shape.

v0.2 step 1: planner and reviewer can optionally be backed by a real
``LLMProvider``. Pass it through ``build_graph`` / ``run_graph`` — when
``None`` (the default), behavior is identical to v0.1 stub mode.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from ai_cockpit.llm import LLMProvider
from ai_cockpit.nodes import (
    coder_node,
    decision_node,
    intake_node,
    make_planner_node,
    make_reviewer_node,
    route_after_decision,
    summary_node,
    verifier_node,
)
from ai_cockpit.state import TaskState, initial_state


def build_graph(llm: LLMProvider | None = None) -> Any:
    """Assemble and compile the LangGraph workflow.

    When ``llm`` is provided, the planner and reviewer route through it;
    otherwise both fall back to the deterministic v0.1 logic.
    """

    builder: StateGraph = StateGraph(TaskState)

    builder.add_node("intake", intake_node)
    builder.add_node("planner", make_planner_node(llm))  # type: ignore[arg-type]
    builder.add_node("coder", coder_node)
    builder.add_node("verifier", verifier_node)
    builder.add_node("reviewer", make_reviewer_node(llm))  # type: ignore[arg-type]
    builder.add_node("decision", decision_node)
    builder.add_node("summary", summary_node)

    builder.add_edge(START, "intake")
    builder.add_edge("intake", "planner")
    builder.add_edge("planner", "coder")
    builder.add_edge("coder", "verifier")
    builder.add_edge("verifier", "reviewer")
    builder.add_edge("reviewer", "decision")
    builder.add_conditional_edges(
        "decision",
        route_after_decision,
        {"coder": "coder", "summary": "summary"},
    )
    builder.add_edge("summary", END)

    return builder.compile()


def run_graph(
    *,
    user_input: str,
    project_root: str,
    mode: str = "exploration",
    max_loops: int = 1,
    test_commands: list[str] | None = None,
    dry_run: bool = False,
    llm: LLMProvider | None = None,
) -> TaskState:
    """Execute the graph end-to-end and return the final state."""

    graph = build_graph(llm=llm)
    state = initial_state(
        user_input=user_input,
        project_root=project_root,
        mode=mode,  # type: ignore[arg-type]
        max_loops=max_loops,
        test_commands=test_commands,
        dry_run=dry_run,
    )

    recursion_limit = max(25, (max_loops + 1) * 8)
    final = graph.invoke(state, config={"recursion_limit": recursion_limit})
    return final  # type: ignore[return-value]
