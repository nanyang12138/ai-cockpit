"""B.10c — Cursor-backed worker for ai-cockpit's coder role.

Per contract §6 the worker sends Cursor a controlled task package
(objective, slice, acceptance, scope, forbidden actions, test
commands, max-change guidance), treats Cursor stdout as **self-report
only** — the deterministic verifier owns ground truth (spec §9), and
defaults to preview unless the CLI passes ``--apply``. Tests inject a
fake :class:`CursorWorkerSession`; the real Cursor CLI is never
spawned in CI.
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
from ai_cockpit.workers.base import WorkerRequest, WorkerResult

log = logging.getLogger(__name__)

_TRANSCRIPT_LIMIT_BYTES = 64_000


class CursorWorkerSession(Protocol):
    """Minimal interactive-session API consumed by the Cursor worker."""

    def send(self, prompt: str) -> str: ...
    def close(self) -> None: ...


CursorWorkerSessionFactory = Callable[[WorkerRequest], CursorWorkerSession]


def _build_task_package(request: WorkerRequest) -> str:
    criteria = list(request.acceptance_criteria or [])
    criteria_block = (
        "\n\nAcceptance criteria:\n" + "\n".join(f"- {c}" for c in criteria)
        if criteria else ""
    )
    return (
        f"Objective: {request.objective}\n\n"
        f"Implementation slice: {request.implementation_slice}"
        f"{criteria_block}\n\n"
        "Scope constraints: stay within the slice; do not refactor "
        "unrelated files.\n"
        "Forbidden actions: do not commit, do not push, do not edit "
        ".ai-cockpit/memory/*; do not delete files outside the slice.\n"
        "Test commands: ai-cockpit's verifier will run the slice's "
        "test_commands after this turn; you do NOT run them yourself.\n"
        "Maximum change guidance: keep diffs small (<=8 files, <=400 "
        "net LOC) and prefer targeted edits over rewrites.\n"
        "Note: your stdout is logged as self-report only; ai-cockpit's "
        "deterministic verifier owns ground truth."
    )


@dataclass
class CursorWorker:
    """Cursor-backed ``Worker``; preview-only when ``request.dry_run``."""

    name: str = "cursor"
    binary_override: str | None = None
    session_factory: CursorWorkerSessionFactory | None = None
    transcript_limit: int = _TRANSCRIPT_LIMIT_BYTES

    def run(self, request: WorkerRequest) -> WorkerResult:
        prompt = _build_task_package(request)
        if request.dry_run:
            preview = (
                "CursorWorker preview (--apply NOT passed; Cursor was "
                "not spawned).\n--- task package ---\n"
                f"{prompt}"
            )
            return WorkerResult(
                summary=preview, changed_files=[],
                notes="CursorWorker dry-run: no Cursor session spawned.",
            )
        factory = self.session_factory or _default_session_factory(
            binary_override=self.binary_override
        )
        try:
            session = factory(request)
        except CursorUnavailableError as exc:
            return WorkerResult(
                summary=f"CursorWorker error: {exc}", changed_files=[],
                notes="CursorWorker: Cursor CLI unavailable.",
            )
        try:
            try:
                transcript = session.send(prompt)
            except Exception as exc:  # noqa: BLE001 - surface transport
                log.warning("cursor worker session failed (%s)", exc)
                return WorkerResult(
                    summary=f"CursorWorker error: cursor session call failed: {exc}",
                    changed_files=[],
                    notes="CursorWorker: session transport failure.",
                )
        finally:
            try:
                session.close()
            except Exception:  # noqa: BLE001 - best-effort cleanup
                pass
        clipped = (transcript or "")[: self.transcript_limit]
        summary = (
            "CursorWorker self-report (verifier owns ground truth).\n"
            "--- cursor stdout ---\n"
            f"{clipped if clipped.strip() else '(empty)'}"
        )
        return WorkerResult(
            summary=summary, changed_files=[],
            notes="CursorWorker self-report; not verification evidence.",
        )


def _default_session_factory(
    *, binary_override: str | None
) -> CursorWorkerSessionFactory:
    def factory(_request: WorkerRequest) -> CursorWorkerSession:
        path = _resolve_binary(binary_override)
        if path is None:
            _raise_unavailable(
                binary_override,
                "rerun with --worker stub|aider or install the Cursor CLI.",
            )
            raise AssertionError("unreachable")
        # Worker runs in default ("agent") mode so Cursor can edit files.
        return _RpcSession(path, mode=None)

    return factory
