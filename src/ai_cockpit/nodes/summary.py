"""Summary node: render the final human-readable report.

The actual rendering logic lives in :mod:`ai_cockpit.render` so the
``run`` / ``plans run`` / future-writer call sites can share it. This
node is the LangGraph entry point: it dispatches on the run's
``output_format`` field, prints to stdout, and stores the plain-text
shape in ``final_summary`` (the v0.1 invariant — preserved so existing
tests + checkpoint replay continue to work).
"""

from __future__ import annotations

from ai_cockpit.render import print_summary, render_summary_plain
from ai_cockpit.state import TaskState

__all__ = ["render_summary", "summary_node"]


def render_summary(state: TaskState) -> str:
    """Backward-compatible alias kept for callers that import this name."""
    return render_summary_plain(state)


def summary_node(state: TaskState) -> TaskState:
    plain = print_summary(state)
    return {"final_summary": plain}
