"""B.10e — Cursor writer: fake sessions only, no real CLI."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from ai_cockpit.cursor_adapter import (
    CursorUnavailableError,
    CursorWriterBackend,
    CursorWriterSession,
    WriterDraftRequest,
)
from ai_cockpit.cursor_adapter.writer import _build_writer_prompt

_OK = "## PR Description\n\nFixed broken calc bug."


class _Fake:
    def __init__(self, *, reply: str = _OK, raise_exc: Exception | None = None):
        self.reply, self.raise_exc = reply, raise_exc
        self.sent: list[str] = []
        self.closed = False

    def send(self, prompt: str) -> str:
        self.sent.append(prompt)
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.reply

    def close(self) -> None:
        self.closed = True


def _f(s: CursorWriterSession):
    return lambda _r: s


def _req(**kw: object) -> WriterDraftRequest:
    base: dict[str, object] = {
        "artifact": "pr_description", "objective": "Document calc fix",
        "diff_summary": "src/calc.py +3 -1",
        "verifier_results": "pytest: 236 passed",
        "constraints": "under 200 words",
    }
    base.update(kw)
    return WriterDraftRequest(**base)  # type: ignore[arg-type]


def test_draft_carries_evidence_returns_reply_closes_and_clips() -> None:
    s = _Fake()
    r = CursorWriterBackend(session_factory=_f(s)).draft(_req())
    assert r.text == _OK and r.artifact == "pr_description"
    assert "no external posting" in r.notes and s.closed and len(s.sent) == 1
    for m in ("Artifact: pr_description", "Document calc fix",
              "src/calc.py +3 -1", "pytest: 236 passed",
              "under 200 words", "LOCAL DRAFT only", "Do NOT post"):
        assert m in s.sent[0], f"{m!r} missing from prompt"
    with pytest.raises(ValueError, match="writer artifact 'slack_message'"):
        _build_writer_prompt(_req(artifact="slack_message"))
    big = _Fake(reply="x" * 2048)
    assert CursorWriterBackend(
        session_factory=_f(big), transcript_limit=128
    ).draft(_req()).text == "x" * 128


def test_draft_handles_transport_unavailable_and_missing_factory() -> None:
    s = _Fake(raise_exc=OSError("broken pipe"))
    r = CursorWriterBackend(session_factory=_f(s)).draft(_req())
    assert r.text == "" and "session failure" in r.notes
    assert "broken pipe" in r.notes and s.closed

    def boom(_r: WriterDraftRequest) -> CursorWriterSession:
        raise CursorUnavailableError("not installed")
    r2 = CursorWriterBackend(session_factory=boom).draft(_req())
    assert r2.text == "" and "unavailable" in r2.notes.lower()
    r3 = CursorWriterBackend().draft(_req())
    assert r3.text == "" and "no session_factory" in r3.notes


def test_writer_module_imports_no_outbound_comms_libraries() -> None:
    """Spec §12: writer must not import outbound-comms libraries."""
    src = (Path(__file__).resolve().parent.parent
           / "src/ai_cockpit/cursor_adapter/writer.py").read_text(encoding="utf-8")
    forbidden = {"requests", "urllib", "urllib3", "smtplib",
                 "http", "socket", "httpx", "aiohttp"}
    names: set[str] = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    leaked = {n for n in names if n.split(".")[0] in forbidden}
    assert not leaked, f"writer imports forbidden network modules: {leaked}"
