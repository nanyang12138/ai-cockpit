"""LangGraph wiring for the v0.1 idea-to-MVP execution loop.

We use ``langgraph.graph.StateGraph`` so the graph is explicit, auditable,
and easy to extend. The state-merge behavior is the LangGraph default
(per-key overwrite), which matches our `TaskState` total=False shape.

v0.2 step 1: planner and reviewer can optionally be backed by a real
``LLMProvider``. Pass it through ``build_graph`` / ``run_graph`` — when
``None`` (the default), behavior is identical to v0.1 stub mode.

v0.2 step 3: optional SQLite checkpointing + ``--resume`` support.
``run_graph`` accepts a ``checkpoint_db`` path and a ``thread_id``;
when both are set, the run is persisted via LangGraph's ``SqliteSaver``
and a later call with ``resume=True`` will continue from the last saved
checkpoint instead of restarting from intake.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph

from ai_cockpit.checkpoint import open_checkpoint_saver, resolve_checkpoint_db
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
    interrupt_before: list[str] | None = None,
) -> Any:
    """Assemble and compile the LangGraph workflow.

    When ``llm`` is provided, the planner and reviewer route through it;
    otherwise both fall back to the deterministic v0.1 logic.

    When ``checkpointer`` is provided (typically a ``SqliteSaver``), the
    compiled graph persists state per ``thread_id`` so runs can be resumed.
    ``interrupt_before`` lets callers (mainly tests and debugging) pause
    the graph just before the named nodes execute.
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
    checkpoint_db: str | Path | None = None,
    thread_id: str | None = None,
    resume: bool = False,
) -> TaskState:
    """Execute the graph end-to-end and return the final state.

    Checkpointing is enabled iff ``thread_id`` is provided. In that case
    a ``SqliteSaver`` is opened against ``checkpoint_db`` (defaulting to
    ``<project_root>/.ai-cockpit/history/checkpoints.sqlite``).

    When ``resume=True``, ``thread_id`` is required and the graph is
    invoked with ``None`` so LangGraph picks up from the last saved
    checkpoint. Initial-state fields are ignored in that case.
    """

    if resume and not thread_id:
        raise ValueError("resume=True requires thread_id to be set")

    recursion_limit = max(25, (max_loops + 1) * 8)

    if thread_id is None:
        # No checkpointing: behave exactly as v0.1 / step-1 did.
        graph = build_graph(llm=llm)
        state = initial_state(
            user_input=user_input,
            project_root=project_root,
            mode=mode,  # type: ignore[arg-type]
            max_loops=max_loops,
            test_commands=test_commands,
            dry_run=dry_run,
        )
        final = graph.invoke(state, config={"recursion_limit": recursion_limit})
        return final  # type: ignore[return-value]

    db_path = resolve_checkpoint_db(project_root, checkpoint_db)
    config: dict[str, Any] = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": recursion_limit,
    }

    with open_checkpoint_saver(db_path) as saver:
        graph = build_graph(llm=llm, checkpointer=saver)
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
