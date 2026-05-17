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
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ai_cockpit.cursor_adapter.planner import (
    CursorUnavailableError,
    _raise_unavailable,
    _resolve_binary,
    _RpcSession,
)

log = logging.getLogger(__name__)


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


def _default_session_factory(
    *, binary_override: str | None
) -> CursorReviewerSessionFactory:
    def factory() -> CursorReviewerSession:
        path = _resolve_binary(binary_override)
        if path is None:
            _raise_unavailable(
                binary_override,
                "rerun with --reviewer builtin or install the Cursor CLI.",
            )
            raise AssertionError("unreachable")
        return _RpcSession(path, mode="ask")

    return factory
