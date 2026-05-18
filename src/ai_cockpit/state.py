"""Typed state and result models passed between graph nodes."""

from __future__ import annotations

from typing import Any, Literal, TypedDict


class CommandResult(TypedDict):
    """Captured result of a single shell command."""

    command: str
    exit_code: int
    stdout: str
    stderr: str


class VerificationResult(TypedDict):
    """Aggregated verifier output: deterministic checks only."""

    passed: bool
    commands: list[CommandResult]
    git_diff: str
    git_status: str


class ReviewResult(TypedDict):
    """Reviewer judgement based purely on collected evidence."""

    passed: bool
    issues: list[str]
    risk_level: Literal["low", "medium", "high"]
    suggested_fix: str
    notes: str


Decision = Literal["done", "retry", "ask_human", "stop"]
Mode = Literal["exploration", "task"]


class TaskState(TypedDict, total=False):
    """The single state object that flows through the LangGraph workflow.

    `total=False` allows nodes to populate fields incrementally; the graph
    starts with only the intake-supplied fields populated and accumulates
    the rest as it executes.
    """

    user_input: str
    mode: Mode
    project_root: str
    memory_context: str

    idea: str
    mvp_spec: str
    acceptance_criteria: list[str]
    implementation_slice: str

    coder_result: str
    git_diff: str
    git_status: str
    verification_result: VerificationResult
    review_result: ReviewResult

    decision: Decision
    loop_count: int
    max_loops: int
    final_summary: str

    dry_run: bool
    test_commands: list[str]

    # B.3: worker token/cost metrics; absent on pre-B.3 checkpoints (total=False).
    metrics: dict[str, float]

    # v0.5 summary-rendering: how summary_node prints its result.
    # Currently consumed by :func:`ai_cockpit.render.print_summary` to
    # pick between the new colored text view (default ``"text"``) and
    # the v0.1-compatible ``"plain"`` view. Absent on pre-v0.5
    # checkpoints (``total=False``); treated as ``"text"`` then. Does
    # NOT affect the plain text stored in ``final_summary`` — that
    # remains the v0.1-compatible shape so checkpoint replay + grep
    # workflows keep working.
    output_format: str


def initial_state(
    *,
    user_input: str,
    project_root: str,
    mode: Mode = "exploration",
    max_loops: int = 1,
    test_commands: list[str] | None = None,
    dry_run: bool = False,
    output_format: str | None = None,
) -> TaskState:
    """Construct the starting `TaskState` for a run."""

    state: TaskState = {
        "user_input": user_input,
        "project_root": project_root,
        "mode": mode,
        "max_loops": max_loops,
        "loop_count": 0,
        "test_commands": list(test_commands or []),
        "dry_run": dry_run,
    }
    if output_format:
        state["output_format"] = output_format
    return state


def state_summary(state: TaskState) -> dict[str, Any]:
    """Produce a serializable subset of the state for logging/printing."""

    keys = (
        "mode",
        "loop_count",
        "max_loops",
        "decision",
        "idea",
        "mvp_spec",
        "acceptance_criteria",
        "implementation_slice",
        "coder_result",
    )
    return {k: state.get(k) for k in keys}
