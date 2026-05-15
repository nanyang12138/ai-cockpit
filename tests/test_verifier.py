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
