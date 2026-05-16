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
from ai_cockpit.workers.base import WorkerRequest, WorkerResult

log = logging.getLogger(__name__)

_TRANSCRIPT_LIMIT_BYTES = 64_000
_SUBPROCESS_TIMEOUT_SECONDS: float = 60.0


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


class _SubprocessSession:
    """Default Popen-based bridge; production may need a PTY-backed session."""

    def __init__(self, binary_path: str) -> None:
        self._proc = subprocess.Popen(  # noqa: S603 - args are flag-only
            [binary_path],
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
                f"cursor worker session timed out after {exc.timeout}s"
            ) from exc
        return out

    def close(self) -> None:
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self._proc.kill()


def _default_session_factory(
    *, binary_override: str | None
) -> CursorWorkerSessionFactory:
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

    def factory(_request: WorkerRequest) -> CursorWorkerSession:
        path = _resolve()
        if path is None:
            status = probe_cursor_adapter(binary_override=binary_override)
            hints = "; ".join(status.errors) or "no Cursor CLI on PATH"
            raise CursorUnavailableError(
                f"Cursor CLI not available ({hints}); rerun with "
                "--worker stub|aider or install the Cursor CLI."
            )
        return _SubprocessSession(path)

    return factory
