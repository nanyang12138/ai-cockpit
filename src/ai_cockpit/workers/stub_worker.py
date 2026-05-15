"""StubWorker — never modifies the working tree.

This is the only worker shipped in v0.1 and is the safe default. It exists
so the graph can run end-to-end without touching files, network, or LLMs.
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_cockpit.workers.base import WorkerRequest, WorkerResult


@dataclass
class StubWorker:
    """A no-op worker that produces a clear, deterministic summary."""

    name: str = "stub"

    def run(self, request: WorkerRequest) -> WorkerResult:
        criteria = ", ".join(request.acceptance_criteria) or "(none)"
        summary = (
            "Stub worker: no code changes were made.\n"
            f"objective: {request.objective}\n"
            f"slice: {request.implementation_slice}\n"
            f"acceptance: {criteria}\n"
            f"dry_run: {request.dry_run}"
        )
        return WorkerResult(
            summary=summary,
            changed_files=[],
            notes="StubWorker is intentionally side-effect free in v0.1.",
        )
