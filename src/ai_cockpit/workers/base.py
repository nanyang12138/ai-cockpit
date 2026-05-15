"""Worker base protocol.

A `Worker` receives a controlled task package and returns a structured
result. v0.1 keeps this intentionally tiny so future workers (Aider,
Cursor SDK, OpenHands) can implement the same interface without changing
the graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class WorkerRequest:
    """Controlled task package handed to a worker."""

    objective: str
    implementation_slice: str
    acceptance_criteria: list[str] = field(default_factory=list)
    project_root: str = "."
    dry_run: bool = False


@dataclass(frozen=True)
class WorkerResult:
    """Structured worker output. `changed_files` may be empty for stubs."""

    summary: str
    changed_files: list[str] = field(default_factory=list)
    notes: str = ""


class Worker(Protocol):
    """Protocol all workers must implement."""

    name: str

    def run(self, request: WorkerRequest) -> WorkerResult: ...
