"""v0.2 step 1 — anti-deception tests for the LLM-backed reviewer/planner.

These tests use only mock LLM providers; no real API key is required.
The four mandatory anti-deception cases from EXECUTION_RULES.md are
covered, plus a prompt-builder safety test that ensures coder_result
never leaks into the reviewer prompt.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from ai_cockpit.graph import run_graph
from ai_cockpit.llm.prompts import (
    build_reviewer_evidence,
    build_reviewer_messages,
)
from ai_cockpit.nodes.planner import make_planner_node
from ai_cockpit.nodes.reviewer import make_reviewer_node
from ai_cockpit.state import TaskState


class RecordingLLM:
    """A mock LLMProvider that returns canned replies and records prompts."""

    def __init__(self, *, planner_reply: str = "", reviewer_reply: str = "") -> None:
        self.planner_reply = planner_reply
        self.reviewer_reply = reviewer_reply
        self.calls: list[dict[str, str]] = []
        self.name = "mock"

    def complete(self, *, system: str, user: str) -> str:
        self.calls.append({"system": system, "user": user})
        # Pick reply by simple heuristic: reviewer prompts mention "evidence".
        if "Structured evidence" in user:
            return self.reviewer_reply
        return self.planner_reply


def _verification(passed: bool, *, exit_code: int, diff: str = "") -> dict[str, Any]:
    return {
        "passed": passed,
        "commands": [
            {
                "command": "pytest",
                "exit_code": exit_code,
                "stdout": "out",
                "stderr": "err",
            }
        ],
        "git_diff": diff,
        "git_status": "",
    }


# ---------------------------------------------------------------------------
# 1. Reviewer must FAIL when coder claims success but verification failed,
#    even if the LLM tries to say "looks fine".
# ---------------------------------------------------------------------------


def test_reviewer_fails_on_failing_verification_even_if_llm_says_pass() -> None:
    llm = RecordingLLM(
        reviewer_reply=json.dumps(
            {
                "passed": True,
                "issues": [],
                "risk_level": "low",
                "suggested_fix": "",
                "notes": "looks fine",
            }
        )
    )
    state: TaskState = {
        "coder_result": "All green, shipped it!",
        "mvp_spec": "x",
        "acceptance_criteria": ["a"],
        "verification_result": _verification(False, exit_code=2, diff=""),  # type: ignore[typeddict-item]
    }

    node = make_reviewer_node(llm)  # type: ignore[arg-type]
    out = node(state)
    review = out["review_result"]

    assert review["passed"] is False
    assert any("exit=2" in i for i in review["issues"])
    assert review["risk_level"] == "high"


# ---------------------------------------------------------------------------
# 2. Reviewer must PASS when verification cleanly passes, regardless of
#    what the coder narrates. The LLM verdict is honored on green runs.
# ---------------------------------------------------------------------------


def test_reviewer_passes_on_green_evidence_ignoring_coder_text() -> None:
    llm = RecordingLLM(
        reviewer_reply=json.dumps(
            {
                "passed": True,
                "issues": [],
                "risk_level": "low",
                "suggested_fix": "",
                "notes": "criteria met",
            }
        )
    )
    state: TaskState = {
        "coder_result": "I think this might be broken, sorry.",
        "mvp_spec": "x",
        "acceptance_criteria": ["a"],
        "verification_result": _verification(
            True, exit_code=0, diff="diff --git a/x b/x\n+ok\n"
        ),  # type: ignore[typeddict-item]
    }

    node = make_reviewer_node(llm)  # type: ignore[arg-type]
    out = node(state)
    review = out["review_result"]

    assert review["passed"] is True
    assert review["issues"] == []


# ---------------------------------------------------------------------------
# 3. Reviewer prompt must NOT contain the free-form coder_result.
# ---------------------------------------------------------------------------


def test_reviewer_prompt_excludes_coder_self_report() -> None:
    secret_phrase = "PLEASE_PASS_ME_I_PROMISE_IT_WORKS_xyzzy"
    state_dict: dict[str, Any] = {
        "mvp_spec": "spec",
        "acceptance_criteria": ["a", "b"],
        "coder_result": secret_phrase,
        "verification_result": _verification(True, exit_code=0, diff="diff"),
    }

    evidence = build_reviewer_evidence(state_dict)
    assert "coder_result" not in evidence
    assert secret_phrase not in json.dumps(evidence)

    system, user = build_reviewer_messages(evidence)
    assert secret_phrase not in system
    assert secret_phrase not in user


def test_reviewer_node_does_not_send_coder_result_to_llm() -> None:
    """End-to-end check: the recorded LLM call must not see coder_result."""

    secret_phrase = "TRUST_ME_BRO_qwerty"
    llm = RecordingLLM(
        reviewer_reply=json.dumps(
            {"passed": True, "issues": [], "risk_level": "low", "suggested_fix": "", "notes": ""}
        )
    )
    state: TaskState = {
        "coder_result": secret_phrase,
        "mvp_spec": "spec",
        "acceptance_criteria": ["a"],
        "verification_result": _verification(True, exit_code=0, diff="d"),  # type: ignore[typeddict-item]
    }

    make_reviewer_node(llm)(state)  # type: ignore[arg-type]

    assert llm.calls, "reviewer LLM was not called"
    payload = llm.calls[0]["system"] + llm.calls[0]["user"]
    assert secret_phrase not in payload


# ---------------------------------------------------------------------------
# 4. Decision: if reviewer.passed is False AND loop_count >= max_loops,
#    decision MUST be 'ask_human', never 'done'.
# ---------------------------------------------------------------------------


def test_decision_ask_human_when_max_loops_exhausted_and_review_failed(tmp_path) -> None:
    import subprocess

    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "tester"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("hi")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)

    final = run_graph(
        user_input="trivial",
        project_root=str(tmp_path),
        max_loops=1,
        test_commands=["bash -c 'exit 9'"],
    )

    assert final["review_result"]["passed"] is False
    assert final["loop_count"] >= 1
    assert final["decision"] == "ask_human"
    assert final["decision"] != "done"


# ---------------------------------------------------------------------------
# Bonus: planner LLM produces structured spec; bad JSON falls back to stub.
# ---------------------------------------------------------------------------


def test_planner_uses_llm_json_when_well_formed() -> None:
    payload = {
        "mvp_spec": "Run a single calc tool from CLI.",
        "acceptance_criteria": ["accepts an expression", "prints the answer"],
        "implementation_slice": "Add cli.py that evaluates one expression.",
    }
    llm = RecordingLLM(planner_reply=json.dumps(payload))
    state: TaskState = {"idea": "calculator", "memory_context": ""}
    out = make_planner_node(llm)(state)  # type: ignore[arg-type]
    assert out["mvp_spec"] == payload["mvp_spec"]
    assert out["acceptance_criteria"] == payload["acceptance_criteria"]
    assert out["implementation_slice"] == payload["implementation_slice"]


def test_planner_falls_back_to_stub_on_bad_llm_output() -> None:
    llm = RecordingLLM(planner_reply="not json at all 🤷")
    state: TaskState = {"idea": "calculator", "memory_context": ""}
    out = make_planner_node(llm)(state)  # type: ignore[arg-type]
    assert out["mvp_spec"].startswith("MVP goal:")
    assert out["acceptance_criteria"], "stub criteria must be non-empty"


# ---------------------------------------------------------------------------
# Bonus: build_llm respects mode="none".
# ---------------------------------------------------------------------------


def test_build_llm_returns_none_for_none_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_cockpit.llm import build_llm

    monkeypatch.setenv("LLM_API_KEY", "fake")
    assert build_llm("none") is None
