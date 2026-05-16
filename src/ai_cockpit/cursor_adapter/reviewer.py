"""B.10d — Cursor-backed reviewer for the §9 evidence-only review path.

Implements :class:`~ai_cockpit.llm.LLMProvider` so the existing
``make_reviewer_node`` already builds the prompt via
``build_reviewer_evidence`` (which excludes ``coder_result`` and
planner-transcript fields) and parses the JSON verdict / enforces the
deterministic floor. This backend only owns the transport. Tests
inject a fake :class:`CursorReviewerSession`; the real Cursor CLI is
never spawned in CI.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ai_cockpit.cursor_adapter.discovery import (
    DEFAULT_CANDIDATE_BINARIES,
    probe_cursor_adapter,
)
from ai_cockpit.cursor_adapter.planner import CursorUnavailableError

log = logging.getLogger(__name__)

_SESSION_READ_LIMIT_BYTES = 64_000
_SUBPROCESS_TIMEOUT_SECONDS: float = 45.0


class CursorReviewerSession(Protocol):
    def send(self, prompt: str) -> str: ...
    def close(self) -> None: ...


CursorReviewerSessionFactory = Callable[[], CursorReviewerSession]


@dataclass
class CursorReviewerBackend:
    """Cursor-backed ``LLMProvider``; only ever sees §9 evidence."""
    name: str = "cursor-reviewer"
    binary_override: str | None = None
    session_factory: CursorReviewerSessionFactory | None = None

    def complete(self, *, system: str, user: str) -> str:
        factory = self.session_factory or _default_session_factory(
            binary_override=self.binary_override
        )
        session = factory()
        prompt = f"{system}\n\n{user}"
        try:
            try:
                return session.send(prompt)
            except CursorUnavailableError:
                raise
            except Exception as exc:  # noqa: BLE001 - surface transport
                log.warning("cursor reviewer session failed (%s)", exc)
                raise RuntimeError(
                    f"cursor reviewer session call failed: {exc}"
                ) from exc
        finally:
            try:
                session.close()
            except Exception:  # noqa: BLE001 - best-effort cleanup
                pass


class _SubprocessSession:
    def __init__(self, binary_path: str, *, mode: str = "ask") -> None:
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
            raise RuntimeError(
                f"cursor reviewer session timed out after {exc.timeout}s"
            ) from exc
        return out[:_SESSION_READ_LIMIT_BYTES]

    def close(self) -> None:
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self._proc.kill()


def _default_session_factory(
    *, binary_override: str | None
) -> CursorReviewerSessionFactory:
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

    def factory() -> CursorReviewerSession:
        path = _resolve()
        if path is None:
            status = probe_cursor_adapter(binary_override=binary_override)
            hints = "; ".join(status.errors) or "no Cursor CLI on PATH"
            raise CursorUnavailableError(
                f"Cursor CLI not available ({hints}); rerun with "
                "--reviewer builtin or install the Cursor CLI."
            )
        return _SubprocessSession(path)

    return factory
