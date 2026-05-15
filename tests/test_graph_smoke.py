"""End-to-end smoke test for the v0.1 graph using the StubWorker."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ai_cockpit.graph import run_graph


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.test"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "tester"], cwd=path, check=True)
    (path / "README.md").write_text("hi")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    _init_git_repo(tmp_path)
    return tmp_path


def test_graph_runs_end_to_end_with_stub(repo: Path) -> None:
    final = run_graph(
        user_input="Build a tool that turns vague ideas into MVP specs",
        project_root=str(repo),
        mode="exploration",
        max_loops=1,
        test_commands=[],
        dry_run=True,
    )

    for key in (
        "idea",
        "mvp_spec",
        "acceptance_criteria",
        "implementation_slice",
        "coder_result",
        "git_status",
        "git_diff",
        "verification_result",
        "review_result",
        "decision",
        "final_summary",
    ):
        assert key in final, f"missing key in final state: {key}"

    assert final["mode"] == "exploration"
    assert final["loop_count"] >= 1
    assert final["coder_result"].startswith("Stub worker:")
    assert final["decision"] in {"done", "ask_human"}
    assert isinstance(final["acceptance_criteria"], list)
    assert final["acceptance_criteria"], "acceptance_criteria must be non-empty"
    assert "AI Cockpit — Run Summary" in final["final_summary"]


def test_graph_with_passing_test_command(repo: Path) -> None:
    final = run_graph(
        user_input="Trivial idea",
        project_root=str(repo),
        max_loops=1,
        test_commands=["python -c 'print(1)'"],
    )

    verification = final["verification_result"]
    assert verification["passed"] is True
    assert len(verification["commands"]) == 1
    cmd = verification["commands"][0]
    assert cmd["exit_code"] == 0
    assert "1" in cmd["stdout"]
    assert final["review_result"]["passed"] is True
    assert final["decision"] == "done"


def test_graph_with_failing_command_triggers_ask_human(repo: Path) -> None:
    final = run_graph(
        user_input="Trivial idea",
        project_root=str(repo),
        max_loops=1,
        test_commands=["bash -c 'exit 7'"],
    )

    verification = final["verification_result"]
    assert verification["passed"] is False
    assert verification["commands"][0]["exit_code"] == 7
    review = final["review_result"]
    assert review["passed"] is False
    assert any("exit=7" in i for i in review["issues"])
    assert final["loop_count"] <= final["max_loops"] + 1
    assert final["decision"] in {"ask_human", "retry"}
    assert final["decision"] != "retry", "retry must terminate, not be the final decision"
