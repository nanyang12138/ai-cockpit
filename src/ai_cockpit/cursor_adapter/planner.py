"""B.10b — Cursor-backed planner backend for the B.9 interactive shell.

B.10pty hardening (2026-05-17): the default transport is now a
single-shot RPC (``agent --print --yolo --output-format json
[--mode plan|ask] [--resume <sid>] <prompt>``) instead of an
interactive Popen. The prompt is passed as an argv positional so
``stdin`` is never required; the JSON envelope returned on stdout
is parsed in-process. Fakes are still injected through
:class:`CursorPlannerSession` so tests never spawn the real CLI.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from collections.abc import Callable
from typing import Any, Protocol

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
_SUBPROCESS_TIMEOUT_SECONDS: float = 60.0


class CursorPlannerSession(Protocol):
    """Minimal session API consumed by the Cursor backends."""

    def send(self, prompt: str) -> str: ...
    def close(self) -> None: ...


CursorSessionFactory = Callable[[PlannerRequest], CursorPlannerSession]


class CursorUnavailableError(RuntimeError):
    """Raised when no usable Cursor CLI binary can be resolved."""


class CursorSessionError(RuntimeError):
    """Raised when the Cursor RPC envelope reports ``is_error: true``."""

    def __init__(self, envelope: dict[str, Any]) -> None:
        self.envelope = envelope
        result = envelope.get("result")
        snippet = str(result)[:200] if result is not None else ""
        super().__init__(
            f"cursor envelope reported is_error=true (subtype="
            f"{envelope.get('subtype')!r}): {snippet}"
        )


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


_SubprocessRunner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]


def _default_subprocess_runner(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - argv is fully constructed in-process
        argv,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=_SUBPROCESS_TIMEOUT_SECONDS,
        check=False,
    )


class _RpcSession:
    """One-subprocess-per-turn Cursor session (B.10pty default).

    Each ``send()`` spawns ``<binary> agent --print --yolo
    --output-format json [--mode <mode>] [--resume <session_id>]
    <prompt>``, parses the JSON envelope, raises
    :class:`CursorSessionError` if ``is_error`` is true, raises
    :class:`CursorUnavailableError` if the binary exits non-zero,
    and returns the inner ``result`` string for downstream parsing.
    """

    def __init__(
        self,
        binary_path: str,
        *,
        mode: str | None = None,
        runner: _SubprocessRunner | None = None,
        read_limit: int = _SESSION_READ_LIMIT_BYTES,
    ) -> None:
        self._binary = binary_path
        self._mode = mode
        self._runner = runner or _default_subprocess_runner
        self._read_limit = read_limit
        self.session_id: str | None = None
        self.last_usage: dict[str, int] | None = None

    def send(self, prompt: str) -> str:
        argv: list[str] = [
            self._binary, "agent", "--print", "--yolo",
            "--output-format", "json",
        ]
        if self._mode is not None:
            argv += ["--mode", self._mode]
        if self.session_id:
            argv += ["--resume", self.session_id]
        argv.append(prompt)
        proc = self._runner(argv)
        if proc.returncode != 0:
            err = (proc.stderr or "").strip()[:200]
            raise CursorUnavailableError(
                f"cursor exited with code {proc.returncode}: {err or '(no stderr)'}"
            )
        stdout = proc.stdout or ""
        try:
            envelope: dict[str, Any] = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"cursor stdout was not valid JSON: {exc}; "
                f"first 200 bytes: {stdout[:200]!r}"
            ) from exc
        if not isinstance(envelope, dict):
            raise RuntimeError(
                f"cursor envelope was not a JSON object (got {type(envelope).__name__})"
            )
        if envelope.get("is_error"):
            raise CursorSessionError(envelope)
        sid = envelope.get("session_id")
        if isinstance(sid, str) and sid:
            self.session_id = sid
        usage = envelope.get("usage")
        if isinstance(usage, dict):
            self.last_usage = {
                "input_tokens": int(usage.get("inputTokens", 0) or 0),
                "output_tokens": int(usage.get("outputTokens", 0) or 0),
                "cache_read_tokens": int(usage.get("cacheReadTokens", 0) or 0),
                "cache_write_tokens": int(usage.get("cacheWriteTokens", 0) or 0),
            }
        result = envelope.get("result", "")
        text = result if isinstance(result, str) else json.dumps(result)
        return text[: self._read_limit]

    def close(self) -> None:
        return None


def _resolve_binary(binary_override: str | None) -> str | None:
    if binary_override:
        return shutil.which(binary_override) or (
            binary_override if "/" in binary_override else None
        )
    for name in DEFAULT_CANDIDATE_BINARIES:
        path = shutil.which(name)
        if path is not None:
            return path
    return None


def _raise_unavailable(binary_override: str | None, hint: str) -> None:
    status = probe_cursor_adapter(binary_override=binary_override)
    hints = "; ".join(status.errors) or "no Cursor CLI on PATH"
    raise CursorUnavailableError(f"Cursor CLI not available ({hints}); {hint}")


def _default_session_factory(*, binary_override: str | None) -> CursorSessionFactory:
    def factory(_request: PlannerRequest) -> CursorPlannerSession:
        path = _resolve_binary(binary_override)
        if path is None:
            _raise_unavailable(
                binary_override,
                "rerun with --backend builtin or install the Cursor CLI.",
            )
            raise AssertionError("unreachable")
        return _RpcSession(path, mode="plan")
    return factory
