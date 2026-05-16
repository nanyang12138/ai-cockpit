"""B.10a — Cursor CLI adapter (read-only discovery only).

Shared subpackage for future Cursor role backends (B.10b/c/d/e).
"""

from __future__ import annotations

from ai_cockpit.cursor_adapter.discovery import (
    DEFAULT_CANDIDATE_BINARIES,
    CursorAdapterStatus,
    probe_cursor_adapter,
)

__all__ = [
    "DEFAULT_CANDIDATE_BINARIES",
    "CursorAdapterStatus",
    "probe_cursor_adapter",
]
