"""B.10a — Cursor CLI adapter (read-only discovery only).

Shared subpackage for future Cursor role backends (B.10b/c/d/e).
"""

from __future__ import annotations

from ai_cockpit.cursor_adapter.discovery import (
    DEFAULT_CANDIDATE_BINARIES,
    CursorAdapterStatus,
    probe_cursor_adapter,
)
from ai_cockpit.cursor_adapter.planner import (
    CursorPlannerBackend,
    CursorPlannerSession,
    CursorSessionFactory,
    CursorUnavailableError,
)
from ai_cockpit.cursor_adapter.worker import (
    CursorWorker,
    CursorWorkerSession,
    CursorWorkerSessionFactory,
)

__all__ = [
    "DEFAULT_CANDIDATE_BINARIES",
    "CursorAdapterStatus",
    "CursorPlannerBackend",
    "CursorPlannerSession",
    "CursorSessionFactory",
    "CursorUnavailableError",
    "CursorWorker",
    "CursorWorkerSession",
    "CursorWorkerSessionFactory",
    "probe_cursor_adapter",
]
