"""SQLite checkpoint helpers for the AI Cockpit graph.

v0.2 step 3 wires ``langgraph.checkpoint.sqlite.SqliteSaver`` into the
workflow so a run can survive process exit and be resumed by thread id.

This module intentionally stays thin: callers (CLI, tests) own the
SqliteSaver lifecycle via the ``open_sqlite_saver`` context manager so
the underlying SQLite connection is always closed cleanly.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver

DEFAULT_CHECKPOINT_SUBPATH = Path(".ai-cockpit") / "history" / "checkpoints.sqlite"


def default_checkpoint_path(project_root: str | Path) -> Path:
    """Return the default on-disk SQLite checkpoint file for a project root."""

    return Path(project_root) / DEFAULT_CHECKPOINT_SUBPATH


def ensure_checkpoint_dir(path: str | Path) -> Path:
    """Make sure the parent directory for the checkpoint DB exists."""

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


@contextmanager
def open_sqlite_saver(path: str | Path) -> Iterator[SqliteSaver]:
    """Open a SqliteSaver bound to ``path``; close the connection on exit.

    ``path`` may be ``":memory:"`` for ephemeral (test-only) use; otherwise
    the parent directory is created if missing.
    """

    path_str = str(path)
    if path_str != ":memory:":
        ensure_checkpoint_dir(path_str)
    with SqliteSaver.from_conn_string(path_str) as saver:
        yield saver


def thread_config(thread_id: str, *, recursion_limit: int | None = None) -> dict[str, Any]:
    """Build the LangGraph ``config`` dict for a given checkpoint thread."""

    cfg: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
    if recursion_limit is not None:
        cfg["recursion_limit"] = recursion_limit
    return cfg
