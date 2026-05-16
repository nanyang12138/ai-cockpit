"""Coder node: dispatches the implementation slice to a worker.

v0.1 hard-wired ``StubWorker``. v0.3 step 2 introduces a small factory
``make_coder_node(worker_name)`` so the CLI can select between the
deterministic ``StubWorker`` (default) and the real ``AiderWorker``
without the graph wiring needing to know either type.

Backward compatibility: the module-level ``coder_node`` is preserved
and behaves exactly as it did in v0.1 — it always uses ``StubWorker``.
``graph.build_graph()`` switches to the factory when a non-stub worker
is requested.
"""

from __future__ import annotations

from collections.abc import Callable

from ai_cockpit.state import TaskState
from ai_cockpit.workers import AiderWorker, StubWorker, Worker, WorkerRequest


def _select_worker(worker_name: str) -> Worker:
    name = (worker_name or "stub").strip().lower()
    if name == "aider":
        return AiderWorker()
    if name == "cursor":
        from ai_cockpit.cursor_adapter.worker import CursorWorker

        return CursorWorker()
    if name == "stub":
        return StubWorker()
    raise ValueError(
        f"unknown worker: {worker_name!r} (expected 'stub', 'aider', or 'cursor')"
    )


def make_coder_node(worker_name: str = "stub") -> Callable[[TaskState], TaskState]:
    """Return a coder-node callable bound to the selected worker."""

    worker = _select_worker(worker_name)

    def _coder_node(state: TaskState) -> TaskState:
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

    return _coder_node


def coder_node(state: TaskState) -> TaskState:
    """Backwards-compatible v0.1 coder node — always uses ``StubWorker``."""

    return make_coder_node("stub")(state)
