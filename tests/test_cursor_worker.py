"""B.10c — Cursor worker backend tests; fake sessions, no real CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from ai_cockpit.cli import main as cli_main
from ai_cockpit.cursor_adapter import (
    CursorUnavailableError,
    CursorWorker,
    CursorWorkerSession,
)
from ai_cockpit.workers import WorkerRequest


def _req(**over: Any) -> WorkerRequest:
    base: dict[str, Any] = {
        "objective": "make calc.add return a+b",
        "implementation_slice": "edit src/calc.py so add() returns a+b",
        "acceptance_criteria": [
            "pytest tests/test_calc.py passes", "no other files change",
        ],
        "project_root": "/tmp/proj", "dry_run": False,
    }
    base.update(over)
    return WorkerRequest(**base)


class _FakeSession:
    def __init__(self, *, reply: str = "Edited calc.py.\n",
                 raise_exc: Exception | None = None) -> None:
        self.reply = reply
        self.raise_exc = raise_exc
        self.sent: list[str] = []
        self.closed = False

    def send(self, prompt: str) -> str:
        self.sent.append(prompt)
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.reply

    def close(self) -> None:
        self.closed = True


def _factory(session: CursorWorkerSession):
    def make(_request: WorkerRequest) -> CursorWorkerSession:
        return session
    return make


def test_dry_run_does_not_spawn_session() -> None:
    session = _FakeSession()
    result = CursorWorker(session_factory=_factory(session)).run(_req(dry_run=True))
    assert session.sent == [] and session.closed is False
    assert "preview" in result.summary.lower()
    assert "no Cursor session spawned" in result.notes
    assert "Objective: make calc.add return a+b" in result.summary
    assert "Forbidden actions" in result.summary
    assert result.changed_files == []


def test_real_run_sends_full_task_package() -> None:
    session = _FakeSession(reply="Done. Wrote calc.py.\n")
    result = CursorWorker(session_factory=_factory(session)).run(_req())
    assert len(session.sent) == 1
    prompt = session.sent[0]
    for needle in (
        "Objective: make calc.add return a+b",
        "Implementation slice: edit src/calc.py",
        "pytest tests/test_calc.py passes",
        "Forbidden actions", "Maximum change guidance",
        "<=8 files", "self-report",
    ):
        assert needle in prompt
    assert session.closed is True
    assert "Done. Wrote calc.py" in result.summary
    assert "verifier owns ground truth" in result.summary
    assert result.changed_files == []


def test_session_error_returns_clean_summary() -> None:
    session = _FakeSession(raise_exc=OSError("broken pipe"))
    result = CursorWorker(session_factory=_factory(session)).run(_req())
    assert "session call failed" in result.summary
    assert "broken pipe" in result.summary
    assert "session transport failure" in result.notes
    assert session.closed is True


def test_session_unavailable_returns_clean_summary() -> None:
    def boom(_request: WorkerRequest) -> CursorWorkerSession:
        raise CursorUnavailableError(
            "Cursor CLI not available (no Cursor CLI on PATH); "
            "rerun with --worker stub|aider"
        )
    result = CursorWorker(session_factory=boom).run(_req())
    assert "CursorWorker error" in result.summary
    assert "not available" in result.summary
    assert "Cursor CLI unavailable" in result.notes


def test_default_factory_raises_when_no_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    result = CursorWorker().run(_req(project_root=str(tmp_path)))
    assert "CursorWorker error" in result.summary
    assert "--worker stub|aider" in result.summary


def test_select_worker_routes_cursor_and_rejects_unknown() -> None:
    from ai_cockpit.nodes.coder import _select_worker

    assert _select_worker("cursor").__class__.__name__ == "CursorWorker"
    with pytest.raises(ValueError, match="unknown worker"):
        _select_worker("not-a-real-worker")


def test_cli_run_cursor_preview_only_does_not_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom_factory(*a: Any, **k: Any) -> Any:
        def factory(_req: Any) -> Any:
            raise AssertionError("Cursor must NOT be spawned without --apply")
        return factory

    monkeypatch.setattr(
        "ai_cockpit.cursor_adapter.worker._default_session_factory", boom_factory
    )
    result = CliRunner().invoke(
        cli_main,
        ["run", "trivial idea", "--root", str(tmp_path),
         "--no-checkpoint", "--worker", "cursor"],
    )
    assert result.exit_code == 0, result.output
    assert "preview-only" in result.output and "worker=cursor" in result.output


def test_cli_run_cursor_apply_blocked_on_dirty_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "ai_cockpit.cli._dirty_paths_outside_aider_allowlist",
        lambda _root: ["src/calc.py"],
    )
    result = CliRunner().invoke(
        cli_main,
        ["run", "trivial idea", "--root", str(tmp_path),
         "--no-checkpoint", "--worker", "cursor", "--apply"],
    )
    assert result.exit_code != 0
    assert "dirty working tree blocks --worker cursor --apply" in result.output


def test_cli_apply_requires_apply_capable_worker(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli_main,
        ["run", "trivial idea", "--root", str(tmp_path),
         "--no-checkpoint", "--worker", "stub", "--apply"],
    )
    assert result.exit_code != 0
    assert "--apply is only meaningful with --worker aider|cursor" in result.output
