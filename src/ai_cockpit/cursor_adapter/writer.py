"""B.10e — Cursor-backed writer (draft-only local text per contract §8).

Spec §12 forbids outbound comms; this module imports no network
primitives and ships no default subprocess transport (callers inject
``session_factory``). Tests use a fake session; the real Cursor CLI
is never spawned in CI.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ai_cockpit.cursor_adapter.planner import CursorUnavailableError

log = logging.getLogger(__name__)
_LIMIT = 64_000
_ALLOWED: tuple[str, ...] = ("pr_description", "run_summary", "status_report")


class CursorWriterSession(Protocol):
    def send(self, prompt: str) -> str: ...
    def close(self) -> None: ...


CursorWriterSessionFactory = Callable[["WriterDraftRequest"], CursorWriterSession]

@dataclass(frozen=True)
class WriterDraftRequest:
    artifact: str
    objective: str
    diff_summary: str = ""
    verifier_results: str = ""
    constraints: str = ""

@dataclass(frozen=True)
class WriterDraftResult:
    artifact: str
    text: str
    notes: str = ""


def _build_writer_prompt(req: WriterDraftRequest) -> str:
    if req.artifact not in _ALLOWED:
        raise ValueError(f"writer artifact {req.artifact!r} not in {_ALLOWED}")
    parts = [f"Artifact: {req.artifact}", f"Objective: {req.objective}"]
    for label, value in (("Diff summary", req.diff_summary),
                         ("Verifier results", req.verifier_results),
                         ("Constraints", req.constraints)):
        if value.strip():
            parts.append(f"{label}:\n{value.strip()}")
    parts.append("Hard rules: this output is a LOCAL DRAFT only. Do NOT post"
                 " to Slack, email, PR comments, or any external service."
                 " Do NOT run shell or edit files. Produce one Markdown block.")
    return "\n\n".join(parts)


@dataclass
class CursorWriterBackend:
    name: str = "cursor-writer"
    session_factory: CursorWriterSessionFactory | None = None
    transcript_limit: int = _LIMIT

    def draft(self, req: WriterDraftRequest) -> WriterDraftResult:
        prompt = _build_writer_prompt(req)
        def _empty(why: str) -> WriterDraftResult:
            return WriterDraftResult(artifact=req.artifact, text="", notes=why)
        if self.session_factory is None:
            return _empty("CursorWriter unavailable: no session_factory supplied.")
        try:
            session = self.session_factory(req)
        except CursorUnavailableError as exc:
            return _empty(f"CursorWriter unavailable: {exc}")
        try:
            try:
                transcript = session.send(prompt)
            except Exception as exc:  # noqa: BLE001 - surface transport
                log.warning("cursor writer session failed (%s)", exc)
                return _empty(f"CursorWriter session failure: {exc}")
        finally:
            try:
                session.close()
            except Exception:  # noqa: BLE001 - best-effort cleanup
                pass
        return WriterDraftResult(
            artifact=req.artifact,
            text=(transcript or "")[: self.transcript_limit],
            notes="CursorWriter local draft; no external posting performed.",
        )


__all__ = ["CursorWriterBackend", "CursorWriterSession",
           "CursorWriterSessionFactory", "WriterDraftRequest", "WriterDraftResult"]
