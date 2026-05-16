"""B.10b — Cursor-backed planner backend for the B.9 interactive shell.

Interactive-first per contract §5 (no ``--print`` reliance); fakes are
injected through :class:`CursorPlannerSession` so tests never spawn the
real Cursor CLI. Saves still flow through B.9 ``/save``.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from collections.abc import Callable
from typing import Protocol

from ai_cockpit.cursor_adapter.discovery import (
    DEFAULT_CANDIDATE_BINARIES,
    probe_cursor_adapter,
)
from ai_cockpit.llm.prompts import parse_json_response
from ai_cockpit.planner_interactive.prompts import build_planner_messages
from ai_cockpit.planner_interactive.tools import PlannerTool, default_tool_registry
from ai_cockpit.planner_interactive.types import (
    PlanDraft,
    PlannerRequest,
    PlannerResponse,
    PlanValidationError,
)

log = logging.getLogger(__name__)

_SESSION_READ_LIMIT_BYTES = 64_000
_SUBPROCESS_TIMEOUT_SECONDS: float = 30.0


class CursorPlannerSession(Protocol):
    """Minimal interactive-session API consumed by the Cursor backend."""

    def send(self, prompt: str) -> str: ...
    def close(self) -> None: ...


CursorSessionFactory = Callable[[PlannerRequest], CursorPlannerSession]


class CursorUnavailableError(RuntimeError):
    """Raised when no usable Cursor CLI binary can be resolved."""


class CursorPlannerBackend:
    """Cursor-backed planner; reuses B.9's JSON plan schema."""

    name = "cursor"

    def __init__(
        self,
        *,
        session_factory: CursorSessionFactory | None = None,
        binary_override: str | None = None,
    ) -> None:
        self._session_factory = session_factory or _default_session_factory(
            binary_override=binary_override
        )
        self._session: CursorPlannerSession | None = None
        self._draft: PlanDraft | None = None
        self._request: PlannerRequest | None = None
        self._tools: dict[str, PlannerTool] = {}

    def start(self, request: PlannerRequest) -> PlannerResponse:
        self._request = request
        self._tools = default_tool_registry(
            request.project_root, max_tool_bytes=request.max_tool_bytes
        )
        self._session = self._session_factory(request)
        return self._turn(
            self._build_user(feedback=None, with_draft=False),
            intro="Cursor planner ready (interactive bridge).",
        )

    def respond(self, text: str) -> PlannerResponse:
        if self._session is None or self._request is None:
            return PlannerResponse(
                "cursor planner has no active session; use /abort and restart.",
                self._draft,
            )
        return self._turn(
            self._build_user(feedback=text, with_draft=True), intro=None
        )

    def draft(self) -> PlanDraft | None:
        return self._draft

    def _build_user(self, *, feedback: str | None, with_draft: bool) -> str:
        assert self._request is not None
        _, user = build_planner_messages(
            idea=self._request.idea,
            memory_context=self._request.memory_context,
            tools=self._tools.values(),
            feedback=feedback,
            current_draft=(self._draft.to_dict() if with_draft and self._draft else None),
        )
        return user

    def _turn(self, prompt: str, *, intro: str | None) -> PlannerResponse:
        assert self._session is not None and self._request is not None
        try:
            raw = self._session.send(prompt)
        except Exception as exc:  # noqa: BLE001 - surface transport errors
            log.warning("cursor session call failed (%s); keeping previous draft", exc)
            return PlannerResponse(
                f"cursor session call failed: {exc}; keeping previous draft.",
                self._draft,
            )
        parsed = parse_json_response(raw)
        if parsed is None:
            base = intro or "cursor reply had no JSON plan; keeping previous draft."
            snippet = (raw or "").strip()
            if snippet:
                base += f"\nCursor said:\n{snippet[:240]}{'...' if len(snippet) > 240 else ''}"
            return PlannerResponse(base, self._draft)
        from ai_cockpit.planner_interactive.backends.builtin import _draft_from_payload

        try:
            new_draft = _draft_from_payload(parsed)
            new_draft.validate(max_slices=self._request.max_slices)
        except PlanValidationError as exc:
            return PlannerResponse(
                f"cursor reply failed validation: {exc}. "
                "Use /revise <feedback> to ask for a corrected draft.",
                self._draft,
            )
        self._draft = new_draft
        msg = f"draft updated by cursor ({len(new_draft.slices)} slice(s))."
        return PlannerResponse(f"{intro} {msg}" if intro else msg, self._draft)


class _SubprocessSession:
    """Default Popen-based bridge; production may need a PTY-backed session."""

    def __init__(self, binary_path: str, *, mode: str = "plan") -> None:
        self._proc = subprocess.Popen(  # noqa: S603 - args are flag-only
            [binary_path, "--mode", mode],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1,
        )

    def send(self, prompt: str) -> str:
        if self._proc.stdin is None or self._proc.stdout is None:
            raise RuntimeError("cursor subprocess has no stdio")
        self._proc.stdin.write(prompt.rstrip("\n") + "\n")
        self._proc.stdin.flush()
        self._proc.stdin.close()
        try:
            out, _ = self._proc.communicate(timeout=_SUBPROCESS_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as exc:
            self._proc.kill()
            raise RuntimeError(f"cursor session timed out after {exc.timeout}s") from exc
        return out[:_SESSION_READ_LIMIT_BYTES]

    def close(self) -> None:
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self._proc.kill()


def _default_session_factory(*, binary_override: str | None) -> CursorSessionFactory:
    def _resolve() -> str | None:
        if binary_override:
            return shutil.which(binary_override) or (
                binary_override if "/" in binary_override else None
            )
        for name in DEFAULT_CANDIDATE_BINARIES:
            path = shutil.which(name)
            if path is not None:
                return path
        return None

    def factory(_request: PlannerRequest) -> CursorPlannerSession:
        path = _resolve()
        if path is None:
            status = probe_cursor_adapter(binary_override=binary_override)
            hints = "; ".join(status.errors) or "no Cursor CLI on PATH"
            raise CursorUnavailableError(
                f"Cursor CLI not available ({hints}); "
                "rerun with --backend builtin or install the Cursor CLI."
            )
        return _SubprocessSession(path)
    return factory
