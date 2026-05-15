"""Worker abstractions.

v0.1 shipped only ``StubWorker``. v0.3 step 2 adds ``AiderWorker``,
which wraps the ``aider`` CLI behind the same ``Worker`` protocol so
the graph wiring does not need to know whether the worker is real or
stubbed. New workers in later steps (Cursor SDK, OpenHands, …) plug in
the same way.
"""

from ai_cockpit.workers.aider_worker import AiderWorker
from ai_cockpit.workers.base import Worker, WorkerRequest, WorkerResult
from ai_cockpit.workers.stub_worker import StubWorker

__all__ = ["Worker", "WorkerRequest", "WorkerResult", "StubWorker", "AiderWorker"]
