"""Tests for verifier evidence collection and shell helper."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ai_cockpit.nodes.verifier import verifier_node
from ai_cockpit.state import initial_state
from ai_cockpit.tools.shell import run_command


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.test"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "tester"], cwd=path, check=True)
    (path / "a.txt").write_text("one\n")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    _init_git_repo(tmp_path)
    return tmp_path


def test_run_command_captures_stdout_stderr_and_exit_code(tmp_path: Path) -> None:
    result = run_command("python -c \"import sys; sys.stdout.write('ok'); sys.stderr.write('warn'); sys.exit(3)\"", cwd=tmp_path)
    assert result["command"].startswith("python -c")
    assert result["exit_code"] == 3
    assert result["stdout"] == "ok"
    assert "warn" in result["stderr"]


def test_run_command_handles_timeout(tmp_path: Path) -> None:
    result = run_command("python -c \"import time; time.sleep(5)\"", cwd=tmp_path, timeout=0.5)
    assert result["exit_code"] == 124
    assert "timed out" in result["stderr"].lower()


def test_verifier_captures_clean_repo(repo: Path) -> None:
    state = initial_state(
        user_input="x",
        project_root=str(repo),
        test_commands=["python -c 'print(\"hi\")'"],
    )
    update = verifier_node(state)

    assert "verification_result" in update
    v = update["verification_result"]
    assert v["passed"] is True
    assert v["git_status"] == ""
    assert v["git_diff"] == ""
    assert len(v["commands"]) == 1
    assert v["commands"][0]["exit_code"] == 0
    assert "hi" in v["commands"][0]["stdout"]


def test_verifier_captures_unstaged_changes(repo: Path) -> None:
    (repo / "a.txt").write_text("two\n")
    state = initial_state(user_input="x", project_root=str(repo))
    update = verifier_node(state)
    v = update["verification_result"]
    assert "a.txt" in v["git_status"]
    assert "-one" in v["git_diff"] and "+two" in v["git_diff"]
    assert v["passed"] is True


def test_verifier_dry_run_skips_commands(repo: Path) -> None:
    state = initial_state(
        user_input="x",
        project_root=str(repo),
        test_commands=["python -c 'print(1)'"],
        dry_run=True,
    )
    update = verifier_node(state)
    v = update["verification_result"]
    assert v["commands"] == []
    assert v["passed"] is True


def test_verifier_detects_cwd_doubling_and_appends_hint(tmp_path: Path) -> None:
    """Bug F regression (2026-05-17 v0.4 attempt 7) — Layer 3:

    Even with the B.2 quirk + Bug F prompt context block in place, the
    planner LLM may still emit ``pytest -v <cwd_name>/`` if it ignores
    both signals. When that happens the verifier must append a clear
    operator hint to stderr so the reviewer's evidence dict carries a
    diagnostic, not just exit code 4 + "file or directory not found".
    """

    repo = tmp_path / "outer"
    inner = repo / "fixture_pkg"
    inner.mkdir(parents=True)
    _init_git_repo(repo)
    # Make 'fixture_pkg' resolvable from repo.parent (i.e. tmp_path)
    # but NOT from cwd=inner — exactly the cwd-doubling shape.
    state = initial_state(
        user_input="x",
        project_root=str(inner),
        # cwd will be 'inner'; arg 'fixture_pkg/' exists in inner.parent
        # but NOT in inner. ls is universally available and exits 2 on
        # "no such file or directory", matching the heuristic.
        test_commands=["ls fixture_pkg"],
    )
    update = verifier_node(state)
    v = update["verification_result"]
    assert len(v["commands"]) == 1
    cmd_result = v["commands"][0]
    assert cmd_result["exit_code"] != 0
    assert "ai-cockpit-verifier hint" in cmd_result["stderr"], (
        "Bug F Layer 3 regression: expected runtime hint when a failing "
        "test_command references a path that exists in cwd.parent but "
        "not in cwd. Stderr was: " + repr(cmd_result["stderr"])
    )
    assert "fixture_pkg" in cmd_result["stderr"]
    assert v["passed"] is False


def test_verifier_no_hint_on_success(tmp_path: Path) -> None:
    """The runtime hint must only fire when the command actually fails."""

    _init_git_repo(tmp_path)
    state = initial_state(
        user_input="x",
        project_root=str(tmp_path),
        test_commands=["true"],
    )
    update = verifier_node(state)
    cmd_result = update["verification_result"]["commands"][0]
    assert cmd_result["exit_code"] == 0
    assert "ai-cockpit-verifier hint" not in (cmd_result.get("stderr") or "")


def test_verifier_no_hint_when_failure_unrelated_to_path(
    tmp_path: Path,
) -> None:
    """If the failure is not a path-not-found, no hint should fire."""

    _init_git_repo(tmp_path)
    state = initial_state(
        user_input="x",
        project_root=str(tmp_path),
        # Exits 7 with an unrelated stderr — no 'file not found' pattern.
        test_commands=[
            "python -c \"import sys; sys.stderr.write('some other error'); "
            "sys.exit(7)\""
        ],
    )
    update = verifier_node(state)
    cmd_result = update["verification_result"]["commands"][0]
    assert cmd_result["exit_code"] == 7
    assert "ai-cockpit-verifier hint" not in (cmd_result.get("stderr") or "")
