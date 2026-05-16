"""Tests for the ``ai-cockpit status`` subcommand."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from ai_cockpit.cli import main


def _init_git_repo(path: Path) -> None:
    """Initialise a bare git repo so commands that inspect git don't fail."""
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(path),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(path),
        check=True,
        capture_output=True,
    )
    (path / ".gitkeep").touch()
    subprocess.run(["git", "add", "."], cwd=str(path), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init", "--allow-empty"],
        cwd=str(path),
        check=True,
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# Basic invocation
# ---------------------------------------------------------------------------


def test_status_exits_zero_and_prints_all_keys(tmp_path: Path) -> None:
    """``cockpit status`` must exit 0 and contain all six expected keys."""
    _init_git_repo(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["status", "--root", str(tmp_path)])
    assert result.exit_code == 0, result.output
    for key in (
        "version:",
        "project_root:",
        "llm_mode_auto:",
        "workflows_found:",
        "suggestions_pending:",
        "checkpoint_db:",
    ):
        assert key in result.output, f"missing key {key!r} in output:\n{result.output}"


def test_status_project_root_matches_root_flag(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["status", "--root", str(tmp_path)])
    assert result.exit_code == 0
    resolved = str(tmp_path.resolve())
    assert f"project_root: {resolved}" in result.output


# ---------------------------------------------------------------------------
# workflows_found
# ---------------------------------------------------------------------------


def test_status_workflows_found_zero_when_no_dir(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["status", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "workflows_found: 0" in result.output


def test_status_workflows_found_counts_yaml_files(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    wf_dir = tmp_path / ".ai-cockpit" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "a.yaml").write_text("name: a\nmode: exploration\nmax_loops: 1\n")
    (wf_dir / "b.yml").write_text("name: b\nmode: task\nmax_loops: 2\n")
    (wf_dir / "not-a-workflow.txt").write_text("ignored")
    runner = CliRunner()
    result = runner.invoke(main, ["status", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "workflows_found: 2" in result.output


# ---------------------------------------------------------------------------
# suggestions_pending
# ---------------------------------------------------------------------------


def test_status_suggestions_pending_zero_when_none(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["status", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "suggestions_pending: 0" in result.output


def test_status_suggestions_pending_counts_files(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    sug_dir = tmp_path / ".ai-cockpit" / "suggestions"
    sug_dir.mkdir(parents=True)
    for i in range(3):
        sid = f"20260101T00000{i}-test-idea-{i}"
        blob: dict[str, Any] = {
            "id": sid,
            "created_at": "2026-01-01T00:00:00",
            "target": "project.md",
            "operation": "append",
            "content": f"## entry {i}\n\n- decision: done\n",
            "rationale": "fixture",
        }
        (sug_dir / f"{sid}.json").write_text(json.dumps(blob))
    runner = CliRunner()
    result = runner.invoke(main, ["status", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "suggestions_pending: 3" in result.output


# ---------------------------------------------------------------------------
# llm_mode_auto
# ---------------------------------------------------------------------------


def test_status_llm_mode_auto_unavailable_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without LLM env vars, llm_mode_auto should report unavailable."""
    _init_git_repo(tmp_path)
    for var in (
        "LLM_API_KEY",
        "LLM_API_BASE",
        "LLM_MODEL_NAME",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    runner = CliRunner()
    result = runner.invoke(main, ["status", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "llm_mode_auto: unavailable" in result.output


# ---------------------------------------------------------------------------
# checkpoint_db
# ---------------------------------------------------------------------------


def test_status_checkpoint_db_is_under_project_root(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["status", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "checkpoint_db:" in result.output
    for line in result.output.splitlines():
        if line.startswith("checkpoint_db:"):
            db_path = line.split(":", 1)[1].strip()
            assert str(tmp_path.resolve()) in db_path


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


def test_status_version_is_present(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    runner = CliRunner()
    result = runner.invoke(main, ["status", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "version:" in result.output
    for line in result.output.splitlines():
        if line.startswith("version:"):
            value = line.split(":", 1)[1].strip()
            assert len(value) > 0
