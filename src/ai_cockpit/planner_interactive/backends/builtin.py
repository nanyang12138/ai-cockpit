"""Builtin planner backend for B.9.

B.9b introduces the backend shell and wires the read-only tool registry
from :mod:`ai_cockpit.planner_interactive.tools`. The deterministic
``--llm none`` path is preserved so tests and CI run without real LLM
calls. LLM-backed behavior is added in B.9c on top of this same shape.
"""

from __future__ import annotations

from pathlib import Path

from ai_cockpit.planner_interactive.tools import PlannerTool, default_tool_registry
from ai_cockpit.planner_interactive.types import (
    PlanDraft,
    PlannerRequest,
    PlannerResponse,
)


class BuiltinPlannerBackend:
    """Default planner backend, deterministic in ``llm_mode='none'``."""

    name = "builtin"

    def __init__(self, *, llm_mode: str = "none") -> None:
        if llm_mode != "none":
            raise ValueError(
                "B.9b builtin backend only supports llm_mode='none'. "
                "LLM-backed planning is B.9c."
            )
        self._draft: PlanDraft | None = None
        self._tools: dict[str, PlannerTool] = {}

    def start(self, request: PlannerRequest) -> PlannerResponse:
        self._tools = default_tool_registry(
            Path(request.project_root), max_tool_bytes=request.max_tool_bytes
        )
        self._draft = PlanDraft.fixture(request.idea)
        return PlannerResponse(
            "Builtin planner ready (deterministic --llm none mode). "
            "Use /tools, /show, /save [path], or /abort.",
            self._draft,
        )

    def respond(self, text: str) -> PlannerResponse:
        return PlannerResponse(
            f"Recorded feedback for the builtin planner: {text}", self._draft
        )

    def draft(self) -> PlanDraft | None:
        return self._draft

    def tools(self) -> dict[str, PlannerTool]:
        return dict(self._tools)
