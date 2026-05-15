"""Intake node: bootstrap the run from raw user input + memory files."""

from __future__ import annotations

from ai_cockpit.memory.loader import load_memory
from ai_cockpit.state import TaskState


def intake_node(state: TaskState) -> TaskState:
    """Read user input, load memory, default mode to ``exploration``."""

    user_input = (state.get("user_input") or "").strip()
    project_root = state.get("project_root") or "."
    mode = state.get("mode") or "exploration"

    memory_context = load_memory(project_root)

    update: TaskState = {
        "idea": user_input,
        "mode": mode,
        "memory_context": memory_context,
        "loop_count": int(state.get("loop_count", 0) or 0),
        "max_loops": int(state.get("max_loops", 1) or 1),
    }
    return update
