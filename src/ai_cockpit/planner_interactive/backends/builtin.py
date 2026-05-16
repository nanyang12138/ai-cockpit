"""Builtin planner backend for B.9.

B.9b shipped the backend shell and wired the read-only tool registry.
B.9c extends the backend to call the existing :class:`LLMProvider` when
the user runs ``ai-cockpit plan ... --llm <mode>`` with a non-``none``
mode. The deterministic ``--llm none`` path is preserved so tests and
CI run without real LLM calls. LLM-returned drafts are parsed and
validated against the B.6-compatible :class:`PlanDraft` schema before
being exposed; on parse / validation / transport failure the previous
draft (if any) is kept and the failure surfaces in the response message
so the user can ``/revise``.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ai_cockpit.llm.prompts import parse_json_response
from ai_cockpit.llm.provider import LLMProvider
from ai_cockpit.planner_interactive.prompts import build_planner_messages
from ai_cockpit.planner_interactive.tools import PlannerTool, default_tool_registry
from ai_cockpit.planner_interactive.types import (
    PlanDraft,
    PlannerRequest,
    PlannerResponse,
    PlanSlice,
    PlanValidationError,
)

log = logging.getLogger(__name__)


class BuiltinPlannerBackend:
    """Default planner backend; deterministic without a bound LLM."""

    name = "builtin"

    def __init__(self, *, llm_mode: str = "none") -> None:
        self._llm_mode = llm_mode
        self._llm: LLMProvider | None = None
        self._draft: PlanDraft | None = None
        self._tools: dict[str, PlannerTool] = {}
        self._request: PlannerRequest | None = None

    def bind_llm(self, llm: LLMProvider | None) -> None:
        """Inject an :class:`LLMProvider`; required for non-``none`` mode."""
        self._llm = llm

    def start(self, request: PlannerRequest) -> PlannerResponse:
        self._request = request
        self._tools = default_tool_registry(
            Path(request.project_root), max_tool_bytes=request.max_tool_bytes
        )
        if self._llm is None:
            self._draft = PlanDraft.fixture(request.idea)
            return PlannerResponse(
                "Builtin planner ready (deterministic --llm none mode). "
                "Use /tools, /show, /save [path], or /abort.",
                self._draft,
            )
        return self._llm_turn(feedback=None)

    def respond(self, text: str) -> PlannerResponse:
        if self._llm is None or self._request is None:
            return PlannerResponse(
                f"Recorded feedback for the builtin planner: {text}",
                self._draft,
            )
        return self._llm_turn(feedback=text)

    def draft(self) -> PlanDraft | None:
        return self._draft

    def tools(self) -> dict[str, PlannerTool]:
        return dict(self._tools)

    def _llm_turn(self, *, feedback: str | None) -> PlannerResponse:
        assert self._llm is not None and self._request is not None
        system, user = build_planner_messages(
            idea=self._request.idea,
            memory_context=self._request.memory_context,
            tools=self._tools.values(),
            feedback=feedback,
            current_draft=(self._draft.to_dict() if self._draft else None),
        )
        try:
            raw = self._llm.complete(system=system, user=user)
        except Exception as exc:  # noqa: BLE001 - surface transport errors
            log.warning("planner LLM call failed (%s); keeping previous draft", exc)
            return PlannerResponse(
                f"planner LLM call failed: {exc}; keeping previous draft.",
                self._draft,
            )
        parsed = parse_json_response(raw)
        if parsed is None:
            return PlannerResponse(
                "planner LLM reply was not valid JSON; keeping previous draft. "
                "Use /revise <feedback> to ask for a fresh draft.",
                self._draft,
            )
        try:
            new_draft = _draft_from_payload(parsed)
            new_draft.validate(max_slices=self._request.max_slices)
        except PlanValidationError as exc:
            return PlannerResponse(
                f"planner LLM reply failed validation: {exc}. "
                "Use /revise <feedback> to ask for a corrected draft.",
                self._draft,
            )
        self._draft = new_draft
        return PlannerResponse(
            f"draft updated by LLM ({len(new_draft.slices)} slice(s)).",
            self._draft,
        )


def _str_list(payload: object) -> list[str]:
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise PlanValidationError("expected a JSON list")
    return [str(x) for x in payload]


def _draft_from_payload(payload: dict[str, object]) -> PlanDraft:
    if "plan_id" not in payload:
        raise PlanValidationError("missing required field: plan_id")
    slices_raw = payload.get("slices") or []
    if not isinstance(slices_raw, list):
        raise PlanValidationError("slices must be a list")
    return PlanDraft(
        plan_id=str(payload["plan_id"]),
        idea=str(payload.get("idea", "")),
        acceptance_criteria=_str_list(payload.get("acceptance_criteria") or []),
        slices=[_slice_from_payload(s) for s in slices_raw],
    )


def _slice_from_payload(payload: object) -> PlanSlice:
    if not isinstance(payload, dict):
        raise PlanValidationError("each slice must be a JSON object")
    if "id" not in payload:
        raise PlanValidationError("slice missing required field: id")
    try:
        return PlanSlice(
            id=str(payload["id"]),
            title=str(payload.get("title", "")),
            why=str(payload.get("why", "")),
            scope_must=_str_list(payload.get("scope_must")),
            scope_out=_str_list(payload.get("scope_out")),
            dod=_str_list(payload.get("dod")),
            files_budget=int(payload.get("files_budget", 8)),
            loc_budget=int(payload.get("loc_budget", 400)),
            depends_on=_str_list(payload.get("depends_on")),
            test_commands=_str_list(payload.get("test_commands")),
        )
    except (TypeError, ValueError) as exc:
        raise PlanValidationError(f"slice payload invalid: {exc}") from exc
