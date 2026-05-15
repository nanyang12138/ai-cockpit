"""SQLite-backed checkpoint persistence for the v0.2 step-3 resume feature.

The CLI runs in a single short-lived process. To support
``--thread-id`` / ``--resume`` we open a ``sqlite3.Connection`` for the
duration of one ``run_graph`` call, hand it to LangGraph's
``SqliteSaver``, and close it when the run ends. Threads are identified
by an opaque string (caller-provided or auto-generated).

This module is intentionally tiny: it owns the DB-path resolution and
connection lifecycle, nothing more.
"""

from __future__ import annotations

import contextlib
import sqlite3
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

DEFAULT_CHECKPOINT_DB = ".ai-cockpit/history/checkpoints.sqlite"


def resolve_checkpoint_db(
    project_root: str | Path,
    override: str | Path | None = None,
) -> Path:
    """Return the absolute path to the checkpoint DB, creating parent dirs.

    ``override`` (when provided) may be absolute or relative to
    ``project_root``. When omitted, falls back to the spec-defined
    ``.ai-cockpit/history/checkpoints.sqlite`` under the project root.
    """

    root = Path(project_root)
    if override is not None:
        candidate = Path(override)
        path = candidate if candidate.is_absolute() else root / candidate
    else:
        path = root / DEFAULT_CHECKPOINT_DB

    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def new_thread_id() -> str:
    """Generate a short opaque thread id for fresh runs."""

    return uuid.uuid4().hex[:12]


@contextlib.contextmanager
def open_checkpoint_saver(db_path: str | Path) -> Iterator[Any]:
    """Yield a ``SqliteSaver`` bound to a sqlite3 connection.

    The saver and its connection are closed when the context exits, so
    the CLI can safely call this once per run.
    """

    from langgraph.checkpoint.sqlite import SqliteSaver

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    try:
        yield SqliteSaver(conn)
    finally:
        conn.close()
