"""Worker abstractions. v0.1 ships only `StubWorker`."""

from ai_cockpit.workers.base import Worker, WorkerRequest, WorkerResult
from ai_cockpit.workers.stub_worker import StubWorker

__all__ = ["Worker", "WorkerRequest", "WorkerResult", "StubWorker"]
