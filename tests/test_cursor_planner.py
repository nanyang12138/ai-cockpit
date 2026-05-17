"""B.10b — Cursor planner backend tests; fake sessions, no real CLI.

B.10pty hardening tests live at the bottom of this file: they exercise
the new RPC default transport (``agent --print --yolo --output-format
json [--mode <m>] [--resume <sid>] <prompt>``) using an injected fake
``subprocess.run`` replacement. CI / cron VMs never invoke the real
Cursor CLI.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from ai_cockpit.cli import main as cli_main
from ai_cockpit.cursor_adapter import (
    CursorPlannerBackend,
    CursorPlannerSession,
    CursorUnavailableError,
)
from ai_cockpit.cursor_adapter.planner import CursorSessionError, _RpcSession
from ai_cockpit.planner_interactive.repl import set_cursor_session_factory_for_tests
from ai_cockpit.planner_interactive.types import PlannerRequest

_VALID_PLAN: dict[str, object] = {
    "plan_id": "ship-cursor-planner",
    "idea": "ship cursor planner",
    "acceptance_criteria": ["cursor planner backend integrated"],
    "slices": [{
        "id": "slice-1",
        "title": "Wire Cursor planner backend",
        "why": "B.10 contract §5.",
        "scope_must": ["Add CursorPlannerBackend implementing PlannerBackend."],
        "scope_out": ["No source writes from the planner."],
        "dod": ["Plan saves through B.9 /save."],
        "files_budget": 6, "loc_budget": 350,
        "depends_on": [], "test_commands": [],
    }],
}


class _FakeSession:
    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.sent: list[str] = []
        self.closed = False

    def send(self, prompt: str) -> str:
        self.sent.append(prompt)
        if not self._replies:
            raise RuntimeError("fake session exhausted")
        return self._replies.pop(0)

    def close(self) -> None:
        self.closed = True


def _make_request(tmp_path: Path) -> PlannerRequest:
    return PlannerRequest(
        idea="ship cursor planner", project_root=tmp_path,
        memory_context="(empty)", output_path=None, llm_mode="none",
        backend="cursor", max_slices=None, max_turns=12, max_tool_bytes=12000,
    )


def _factory(session: CursorPlannerSession):
    def make(_request: PlannerRequest) -> CursorPlannerSession:
        return session
    return make


def test_start_with_json_reply_updates_draft(tmp_path: Path) -> None:
    session = _FakeSession([json.dumps(_VALID_PLAN)])
    backend = CursorPlannerBackend(session_factory=_factory(session))
    response = backend.start(_make_request(tmp_path))
    assert response.draft is not None
    assert response.draft.plan_id == "ship-cursor-planner"
    assert "draft updated by cursor" in response.message
    assert session.sent and "ship cursor planner" in session.sent[0]


def test_start_with_prose_keeps_no_draft_and_shows_reply(tmp_path: Path) -> None:
    session = _FakeSession(["I have some questions before drafting a plan."])
    backend = CursorPlannerBackend(session_factory=_factory(session))
    response = backend.start(_make_request(tmp_path))
    assert response.draft is None and backend.draft() is None
    assert "Cursor planner ready" in response.message
    assert "Cursor said:" in response.message


def test_respond_with_invalid_plan_keeps_previous_draft(tmp_path: Path) -> None:
    bad = {"plan_id": "ship-cursor-planner", "slices": []}
    session = _FakeSession([json.dumps(_VALID_PLAN), json.dumps(bad)])
    backend = CursorPlannerBackend(session_factory=_factory(session))
    backend.start(_make_request(tmp_path))
    response = backend.respond("make it tighter")
    assert response.draft is not None
    assert response.draft.plan_id == "ship-cursor-planner"
    assert "failed validation" in response.message
    assert "make it tighter" in session.sent[-1]


def test_session_error_keeps_previous_draft(tmp_path: Path) -> None:
    class _Boom:
        def __init__(self) -> None:
            self._first = True

        def send(self, prompt: str) -> str:
            if self._first:
                self._first = False
                return json.dumps(_VALID_PLAN)
            raise OSError("broken pipe")

        def close(self) -> None:
            pass

    backend = CursorPlannerBackend(session_factory=_factory(_Boom()))
    backend.start(_make_request(tmp_path))
    response = backend.respond("revise please")
    assert response.draft is not None
    assert "cursor session call failed" in response.message
    assert "broken pipe" in response.message


def test_default_factory_raises_when_no_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    backend = CursorPlannerBackend()
    with pytest.raises(CursorUnavailableError) as info:
        backend.start(_make_request(tmp_path))
    assert "--backend builtin" in str(info.value)


def test_cli_plan_cursor_backend_saves_with_fake_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = _FakeSession([json.dumps(_VALID_PLAN)])
    set_cursor_session_factory_for_tests(_factory(session))
    monkeypatch.setenv("PATH", str(tmp_path))
    try:
        result = CliRunner().invoke(
            cli_main,
            ["plan", "ship cursor planner", "--root", str(tmp_path),
             "--llm", "none", "--backend", "cursor"],
            input="/save\n", catch_exceptions=False,
        )
    finally:
        set_cursor_session_factory_for_tests(None)
    assert result.exit_code == 0, result.output
    saved = tmp_path / "docs" / "plans" / "ship-cursor-planner.plan.yaml"
    assert saved.is_file()
    data = yaml.safe_load(saved.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["plan_id"] == "ship-cursor-planner"
    assert "info: planner backend enabled (cursor)" in result.output


# B.10pty hardening — default RPC transport ----------------------------------


def _envelope(result: str, *, session_id: str = "sess-1",
              is_error: bool = False) -> str:
    return json.dumps({
        "type": "result", "subtype": "error" if is_error else "success",
        "is_error": is_error, "duration_ms": 100, "result": result,
        "session_id": session_id, "request_id": "req-1",
        "usage": {"inputTokens": 11, "outputTokens": 22,
                  "cacheReadTokens": 0, "cacheWriteTokens": 0},
    })


def _ok(stdout: str, *, returncode: int = 0,
        stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["cursor"], returncode=returncode, stdout=stdout, stderr=stderr,
    )


class _RecordingRunner:
    def __init__(self, returns: list[subprocess.CompletedProcess[str]]) -> None:
        self.returns = list(returns)
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str]) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(argv))
        return self.returns.pop(0)


def test_rpc_session_happy_path_resumes_and_validates_plan_draft() -> None:
    plan_json = json.dumps(_VALID_PLAN)
    runner = _RecordingRunner([
        _ok(_envelope(plan_json, session_id="sess-A")),
        _ok(_envelope(plan_json, session_id="sess-A")),
    ])
    session = _RpcSession("cursor", mode="plan", runner=runner)
    out1 = session.send("first prompt")
    assert json.loads(out1)["plan_id"] == "ship-cursor-planner"
    assert session.session_id == "sess-A"
    assert session.last_usage == {
        "input_tokens": 11, "output_tokens": 22,
        "cache_read_tokens": 0, "cache_write_tokens": 0,
    }
    out2 = session.send("second prompt")
    assert json.loads(out2)["plan_id"] == "ship-cursor-planner"
    # Argv shape: agent --print --yolo --output-format json --mode plan
    # [+ --resume sess-A on turn 2] <prompt>.
    for call in runner.calls:
        assert call[1] == "agent"
        assert "--print" in call and "--yolo" in call
        assert "--output-format" in call and "json" in call
        assert "--mode" in call and "plan" in call
    assert "--resume" not in runner.calls[0]
    assert runner.calls[0][-1] == "first prompt"
    assert "--resume" in runner.calls[1] and "sess-A" in runner.calls[1]
    assert runner.calls[1][-1] == "second prompt"
    # PlanDraft schema accepts envelope.result decoded JSON (B.10b
    # invariant restated under the new transport).
    from ai_cockpit.planner_interactive.backends.builtin import _draft_from_payload

    draft = _draft_from_payload(json.loads(out1))
    draft.validate(max_slices=None)
    assert draft.plan_id == "ship-cursor-planner"


def test_rpc_session_is_error_raises_session_error() -> None:
    runner = _RecordingRunner([_ok(_envelope("model refused", is_error=True))])
    session = _RpcSession("cursor", mode="plan", runner=runner)
    with pytest.raises(CursorSessionError) as info:
        session.send("hi")
    assert info.value.envelope["is_error"] is True
    assert "model refused" in str(info.value)
    # session_id NOT advanced when the turn errored.
    assert session.session_id is None


def test_rpc_session_nonzero_exit_raises_unavailable() -> None:
    runner = _RecordingRunner([_ok("", returncode=2, stderr="auth failed")])
    session = _RpcSession("cursor", mode="plan", runner=runner)
    with pytest.raises(CursorUnavailableError, match="auth failed"):
        session.send("hi")
