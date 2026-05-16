"""Tests for B.9b read-only planner tools and builtin backend shell."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from ai_cockpit.cli import main as cli_main
from ai_cockpit.planner_interactive.backends import BuiltinPlannerBackend
from ai_cockpit.planner_interactive.tools import (
    DEFAULT_MAX_BYTES,
    PlannerToolError,
    default_tool_registry,
    git_log,
    git_status,
    glob_files,
    read_existing_plans,
    read_file,
    ripgrep_search,
)
from ai_cockpit.planner_interactive.types import PlannerRequest


def _request(root: Path) -> PlannerRequest:
    return PlannerRequest(
        idea="ship interactive planner",
        project_root=root,
        memory_context="",
        output_path=None,
        llm_mode="none",
        backend="builtin",
        max_slices=None,
        max_turns=12,
        max_tool_bytes=DEFAULT_MAX_BYTES,
    )


def test_read_file_clips_and_rejects_unsafe_inputs(tmp_path: Path) -> None:
    (tmp_path / "big.txt").write_text("a" * 200, encoding="utf-8")
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01\x02zzz")
    (tmp_path / "project").mkdir()
    (tmp_path.parent / "secret.txt").write_text("nope", encoding="utf-8")

    clipped = read_file(tmp_path, "big.txt", max_bytes=64)
    assert clipped.truncated and clipped.output.endswith("[clipped]")

    with pytest.raises(PlannerToolError, match="binary file refused"):
        read_file(tmp_path, "blob.bin")
    with pytest.raises(PlannerToolError, match="escapes project root"):
        read_file(tmp_path / "project", "../secret.txt")


def test_glob_files_lists_matches_and_skips_unsafe(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "src" / "b.py").write_text("y = 2\n", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref\n", encoding="utf-8")

    result = glob_files(tmp_path, "**/*.py")
    assert "src/a.py" in result.output and "src/b.py" in result.output
    assert ".git" not in result.output

    for unsafe in ("/etc/passwd", "../**/*"):
        with pytest.raises(PlannerToolError, match="unsafe glob pattern"):
            glob_files(tmp_path, unsafe)


def test_ripgrep_finds_matches_skips_skip_dirs_and_caps(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("alpha-secret\n", encoding="utf-8")

    result = ripgrep_search(tmp_path, "alpha")
    assert "a.py:1:alpha" in result.output and ".git" not in result.output

    with pytest.raises(PlannerToolError, match="invalid regex"):
        ripgrep_search(tmp_path, "(")

    (tmp_path / "many.txt").write_text("\n".join(["match"] * 500), encoding="utf-8")
    capped = ripgrep_search(tmp_path, "match", max_results=10)
    assert capped.truncated and capped.output.count("many.txt:") <= 10


def test_git_status_log_and_existing_plans(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "f.txt").write_text("hi\n", encoding="utf-8")
    subprocess.run(["git", "add", "f.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "first"], cwd=tmp_path, check=True)
    (tmp_path / "f.txt").write_text("hi2\n", encoding="utf-8")

    assert "f.txt" in git_status(tmp_path).output
    assert "first" in git_log(tmp_path, limit=5).output
    assert "git log failed" in git_log(tmp_path.parent / "not-a-repo").output

    assert "no docs/plans/" in read_existing_plans(tmp_path).output
    plans_dir = tmp_path / "docs" / "plans"
    plans_dir.mkdir(parents=True)
    (plans_dir / "alpha.plan.yaml").write_text("schema_version: 1\n", encoding="utf-8")
    assert "alpha.plan.yaml" in read_existing_plans(tmp_path).output


def test_registry_and_builtin_backend(tmp_path: Path) -> None:
    expected = {"read_file", "glob", "ripgrep", "git_status", "git_log", "read_existing_plans"}
    registry = default_tool_registry(tmp_path, max_tool_bytes=1024)
    assert set(registry) == expected
    for tool in registry.values():
        assert callable(tool.call) and tool.description

    backend = BuiltinPlannerBackend(llm_mode="none")
    response = backend.start(_request(tmp_path))
    assert response.draft is not None
    assert response.draft.plan_id == "ship-interactive-planner"
    assert "Builtin planner ready" in response.message
    assert expected.issubset(backend.tools())

    # Without bind_llm(), even a non-'none' mode falls back to the
    # deterministic fixture (B.9c keeps the safe default for tests).
    unbound = BuiltinPlannerBackend(llm_mode="anthropic")
    unbound_response = unbound.start(_request(tmp_path))
    assert unbound_response.draft is not None
    assert "Builtin planner ready" in unbound_response.message


def test_plan_tools_command_lists_registered_tools(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli_main,
        ["plan", "list tools demo", "--root", str(tmp_path), "--llm", "none"],
        input="/tools\n/abort\n",
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    assert "Read-only planner tools:" in result.output
    for name in ("read_file", "glob", "ripgrep", "git_status", "git_log"):
        assert name in result.output
