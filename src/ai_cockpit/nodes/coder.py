"""Coder node: dispatches the implementation slice to a worker.

v0.1 hard-wires `StubWorker` and never modifies code. Future versions
can choose a worker based on configuration without changing this node's
shape.
"""

from __future__ import annotations

from ai_cockpit.state import TaskState
from ai_cockpit.workers import StubWorker, WorkerRequest


def coder_node(state: TaskState) -> TaskState:
    """Run the configured worker (StubWorker only in v0.1)."""

    worker = StubWorker()
    request = WorkerRequest(
        objective=state.get("idea", "") or state.get("user_input", ""),
        implementation_slice=state.get("implementation_slice", ""),
        acceptance_criteria=list(state.get("acceptance_criteria", []) or []),
        project_root=state.get("project_root", "."),
        dry_run=bool(state.get("dry_run", False)),
    )
    result = worker.run(request)

    return {
        "coder_result": result.summary,
        "loop_count": int(state.get("loop_count", 0) or 0) + 1,
    }
