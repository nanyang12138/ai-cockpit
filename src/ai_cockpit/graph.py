"""LangGraph wiring for the AI Cockpit idea-to-MVP execution loop.

We use ``langgraph.graph.StateGraph`` so the graph is explicit, auditable,
and easy to extend. The state-merge behavior is the LangGraph default
(per-key overwrite), which matches our `TaskState` total=False shape.

v0.2 step 1: planner and reviewer can optionally be backed by a real
``LLMProvider``. Pass it through ``build_graph`` / ``run_graph`` — when
``None`` (the default), behavior is identical to v0.1 stub mode.

v0.2 step 3: an optional ``checkpointer`` (typically a
``langgraph.checkpoint.sqlite.SqliteSaver``) can be wired in so each
node's state is persisted and a run can be resumed by ``thread_id``.
"""

from __future__ import annotations

from collections.abc import Sequence
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


def build_graph(
    llm: LLMProvider | None = None,
    *,
    checkpointer: Any = None,
    interrupt_before: Sequence[str] | None = None,
) -> Any:
    """Assemble and compile the LangGraph workflow.

    Parameters
    ----------
    llm:
        Optional LLM provider; when provided the planner and reviewer route
        through it. Otherwise both fall back to the deterministic v0.1 logic.
    checkpointer:
        Optional LangGraph checkpointer (e.g. ``SqliteSaver``). When given,
        invocations must include a ``configurable.thread_id`` and the graph
        state is persisted between nodes — enabling kill/resume.
    interrupt_before:
        Optional list of node names to halt execution before. The run can be
        resumed later by invoking the graph again with ``input=None`` and the
        same ``thread_id``. Useful for tests and for future human-in-the-loop.
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

    compile_kwargs: dict[str, Any] = {}
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer
    if interrupt_before:
        compile_kwargs["interrupt_before"] = list(interrupt_before)

    return builder.compile(**compile_kwargs)


def run_graph(
    *,
    user_input: str,
    project_root: str,
    mode: str = "exploration",
    max_loops: int = 1,
    test_commands: list[str] | None = None,
    dry_run: bool = False,
    llm: LLMProvider | None = None,
    checkpointer: Any = None,
    thread_id: str | None = None,
    resume: bool = False,
    interrupt_before: Sequence[str] | None = None,
) -> TaskState:
    """Execute the graph end-to-end and return the final state.

    Resume semantics (v0.2 step 3): when ``resume=True`` the graph is
    invoked with ``None`` input so LangGraph continues from the last
    checkpoint belonging to ``thread_id``. ``checkpointer`` and
    ``thread_id`` are required in that case.
    """

    if resume and (checkpointer is None or thread_id is None):
        raise ValueError("resume=True requires both checkpointer and thread_id")

    graph = build_graph(
        llm=llm,
        checkpointer=checkpointer,
        interrupt_before=interrupt_before,
    )

    recursion_limit = max(25, (max_loops + 1) * 8)
    config: dict[str, Any] = {"recursion_limit": recursion_limit}
    if thread_id is not None:
        config["configurable"] = {"thread_id": thread_id}

    if resume:
        final = graph.invoke(None, config=config)
    else:
        state = initial_state(
            user_input=user_input,
            project_root=project_root,
            mode=mode,  # type: ignore[arg-type]
            max_loops=max_loops,
            test_commands=test_commands,
            dry_run=dry_run,
        )
        final = graph.invoke(state, config=config)
    return final  # type: ignore[return-value]
