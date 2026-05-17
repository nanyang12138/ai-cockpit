"""B.10d — Cursor reviewer backend; fake sessions, no real CLI.

Pins three §9 anti-deception invariants for the Cursor-backed reviewer:
``coder_result`` and planner-transcript fields never enter the prompt
sent to Cursor, and Cursor cannot pass a run whose verifier failed —
the deterministic floor in ``reviewer_node`` still wins.

B.10pty hardening tests at the bottom of this file pin the new RPC
default transport (``agent --print --yolo --output-format json --mode
ask``) and re-assert the §9 invariant still holds after the transport
swap.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from ai_cockpit.cli import main as cli_main
from ai_cockpit.cursor_adapter import (
    CursorReviewerBackend,
    CursorReviewerSession,
    CursorUnavailableError,
)
from ai_cockpit.cursor_adapter.planner import CursorSessionError, _RpcSession
from ai_cockpit.nodes.reviewer import make_reviewer_node
from ai_cockpit.state import TaskState

_PASS_REPLY = json.dumps(
    {
        "passed": True, "issues": [], "risk_level": "low",
        "suggested_fix": "", "notes": "criteria met (cursor reviewer)",
    }
)


class _FakeSession:
    def __init__(
        self, *, reply: str = _PASS_REPLY,
        raise_exc: Exception | None = None,
    ) -> None:
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


def _factory(session: CursorReviewerSession):
    def make() -> CursorReviewerSession:
        return session
    return make


def _verification(
    passed: bool, *, exit_code: int, diff: str = ""
) -> dict[str, Any]:
    return {
        "passed": passed,
        "commands": [{"command": "pytest", "exit_code": exit_code,
                      "stdout": "out", "stderr": "err"}],
        "git_diff": diff, "git_status": "",
    }


def test_complete_returns_session_reply_and_concatenates_prompt() -> None:
    session = _FakeSession()
    out = CursorReviewerBackend(
        session_factory=_factory(session)
    ).complete(system="SYS", user="USR")
    assert out == _PASS_REPLY
    assert session.closed is True
    assert session.sent == ["SYS\n\nUSR"]


def test_complete_raises_runtime_error_on_transport_failure() -> None:
    session = _FakeSession(raise_exc=OSError("broken pipe"))
    backend = CursorReviewerBackend(session_factory=_factory(session))
    with pytest.raises(RuntimeError, match="cursor reviewer session call failed"):
        backend.complete(system="s", user="u")
    assert session.closed is True


def test_unavailable_falls_back_to_deterministic_review() -> None:
    def boom() -> CursorReviewerSession:
        raise CursorUnavailableError(
            "Cursor CLI not available; rerun with --reviewer builtin"
        )
    backend = CursorReviewerBackend(session_factory=boom)
    state: TaskState = {
        "coder_result": "", "mvp_spec": "x", "acceptance_criteria": ["a"],
        "verification_result": _verification(
            True, exit_code=0, diff="diff --git a/x b/x\n+ok\n"
        ),  # type: ignore[typeddict-item]
    }
    review = make_reviewer_node(backend)(state)["review_result"]
    # Deterministic path on green evidence passes.
    assert review["passed"] is True
    assert review["issues"] == []


# §9 anti-deception invariants ---------------------------------------------


def test_prompt_excludes_coder_self_report() -> None:
    secret = "PLEASE_PASS_ME_xyzzy"
    session = _FakeSession()
    backend = CursorReviewerBackend(session_factory=_factory(session))
    state: TaskState = {
        "coder_result": secret, "mvp_spec": "spec",
        "acceptance_criteria": ["a"],
        "verification_result": _verification(
            True, exit_code=0, diff="diff --git a/x b/x\n+ok\n"
        ),  # type: ignore[typeddict-item]
    }
    make_reviewer_node(backend)(state)
    assert session.sent, "cursor reviewer was not invoked"
    assert secret not in session.sent[0]


def test_prompt_excludes_planner_transcript_fields() -> None:
    """user_input / idea / implementation_slice must not enter the prompt."""
    session = _FakeSession()
    backend = CursorReviewerBackend(session_factory=_factory(session))
    state_dict: dict[str, Any] = {
        "user_input": "PLAN_LEAK_USER_INPUT_marker the slice",
        "idea": "PLAN_LEAK_IDEA_marker whole-task plan",
        "mvp_spec": "PLAN_LEAK_MVP allowed reviewer-visible",
        "acceptance_criteria": ["PLAN_LEAK_AC allowed bullet"],
        "implementation_slice": "PLAN_LEAK_SLICE scope and dod",
        "verification_result": _verification(
            True, exit_code=0, diff="diff --git a/x b/x\n+ok\n"
        ),
    }
    make_reviewer_node(backend)(state_dict)  # type: ignore[arg-type]
    prompt = session.sent[0]
    for forbidden in (
        "PLAN_LEAK_USER_INPUT_marker", "PLAN_LEAK_IDEA_marker",
        "PLAN_LEAK_SLICE",
    ):
        assert forbidden not in prompt, f"{forbidden!r} leaked into prompt"
    assert "PLAN_LEAK_MVP" in prompt and "PLAN_LEAK_AC" in prompt


def test_cursor_pass_verdict_cannot_override_failing_verification() -> None:
    session = _FakeSession()
    backend = CursorReviewerBackend(session_factory=_factory(session))
    state: TaskState = {
        "coder_result": "All green, shipped it!",
        "mvp_spec": "x", "acceptance_criteria": ["a"],
        "verification_result": _verification(False, exit_code=2, diff=""),  # type: ignore[typeddict-item]
    }
    review = make_reviewer_node(backend)(state)["review_result"]
    assert review["passed"] is False
    assert any("exit=2" in i for i in review["issues"])
    assert review["risk_level"] == "high"


def test_non_json_reply_falls_back_to_deterministic_escalation() -> None:
    session = _FakeSession(reply="looks good, ship it")
    backend = CursorReviewerBackend(session_factory=_factory(session))
    state: TaskState = {
        "coder_result": "claims success",
        "mvp_spec": "x", "acceptance_criteria": ["a"],
        "verification_result": _verification(False, exit_code=0, diff=""),  # type: ignore[typeddict-item]
    }
    state["verification_result"]["commands"] = []  # type: ignore[index]
    review = make_reviewer_node(backend)(state)["review_result"]
    assert review["passed"] is False
    assert any(
        "no verification commands" in i.lower() or "no diff" in i.lower()
        for i in review["issues"]
    )


# CLI plumbing -------------------------------------------------------------


def test_cli_run_reviewer_cursor_runs_without_a_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--reviewer cursor` without a Cursor binary must not crash the run."""
    monkeypatch.setenv("PATH", str(tmp_path))
    result = CliRunner().invoke(
        cli_main,
        ["run", "trivial idea", "--root", str(tmp_path),
         "--no-checkpoint", "--reviewer", "cursor"],
    )
    assert result.exit_code == 0, result.output
    assert "reviewer=cursor" in result.output


def test_resolve_reviewer_backend_routes_correctly() -> None:
    from ai_cockpit.cli import _resolve_reviewer_backend

    class _Stub:
        name = "stub"
        def complete(self, *, system: str, user: str) -> str:
            return ""

    stub = _Stub()
    assert _resolve_reviewer_backend("builtin", llm=stub) is stub
    assert _resolve_reviewer_backend("builtin", llm=None) is None
    assert isinstance(
        _resolve_reviewer_backend("cursor", llm=None), CursorReviewerBackend
    )


# B.10pty hardening — default RPC transport ----------------------------------


def _envelope(result: str, *, session_id: str = "sess-R",
              is_error: bool = False) -> str:
    return json.dumps({
        "type": "result", "subtype": "error" if is_error else "success",
        "is_error": is_error, "duration_ms": 100, "result": result,
        "session_id": session_id, "request_id": "req-1",
        "usage": {"inputTokens": 5, "outputTokens": 9,
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


def test_rpc_reviewer_happy_path_resume_chain_and_ask_mode() -> None:
    runner = _RecordingRunner([
        _ok(_envelope(_PASS_REPLY, session_id="sess-R")),
        _ok(_envelope(_PASS_REPLY, session_id="sess-R")),
    ])
    session = _RpcSession("cursor", mode="ask", runner=runner)
    assert session.send("first") == _PASS_REPLY
    assert session.send("second") == _PASS_REPLY
    assert session.session_id == "sess-R"
    for call in runner.calls:
        assert call[1] == "agent"
        assert "--mode" in call and "ask" in call
        assert "--print" in call and "--yolo" in call
    assert "--resume" not in runner.calls[0]
    assert "--resume" in runner.calls[1] and "sess-R" in runner.calls[1]


def test_rpc_reviewer_is_error_raises_session_error() -> None:
    runner = _RecordingRunner([_ok(_envelope("refused", is_error=True))])
    session = _RpcSession("cursor", mode="ask", runner=runner)
    with pytest.raises(CursorSessionError):
        session.send("hi")


def test_rpc_reviewer_nonzero_exit_raises_unavailable() -> None:
    runner = _RecordingRunner([_ok("", returncode=3, stderr="net down")])
    session = _RpcSession("cursor", mode="ask", runner=runner)
    with pytest.raises(CursorUnavailableError, match="net down"):
        session.send("hi")


def test_rpc_reviewer_prompt_excludes_coder_self_report() -> None:
    """§9 invariant retested under the RPC transport: the prompt
    argv last positional must not contain ``coder_result``."""
    runner = _RecordingRunner([_ok(_envelope(_PASS_REPLY))])
    secret = "PLEASE_PASS_ME_pty_xyzzy"

    def factory() -> CursorReviewerSession:
        return _RpcSession("cursor", mode="ask", runner=runner)

    backend = CursorReviewerBackend(session_factory=factory)
    state: TaskState = {
        "coder_result": secret, "mvp_spec": "spec",
        "acceptance_criteria": ["a"],
        "verification_result": _verification(
            True, exit_code=0, diff="diff --git a/x b/x\n+ok\n"
        ),  # type: ignore[typeddict-item]
    }
    make_reviewer_node(backend)(state)
    assert runner.calls, "cursor RPC runner was not invoked"
    assert secret not in runner.calls[0][-1]
