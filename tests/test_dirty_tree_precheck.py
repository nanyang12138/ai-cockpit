"""A.7 — pre-run dirty-tree pre-check tests.

These tests verify the safety net that guards ``--worker aider --apply``
from silently squashing user work-in-progress. They never spawn the real
aider CLI; the guard runs before worker selection so all we need is a
git working tree on disk.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from click.testing import CliRunner

from ai_cockpit.cli import (
    _AIDER_RUNTIME_ALLOWLIST_PREFIXES,
    _dirty_paths_outside_aider_allowlist,
)
from ai_cockpit.cli import main as cli_main


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.test"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "tester"], cwd=path, check=True)
    (path / "README.md").write_text("hi\n")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)


def _aider_apply_cmd(root: Path, *extra: str) -> list[str]:
    return [
        "--root",
        str(root),
        "--max-loops",
        "1",
        "--worker",
        "aider",
        "--apply",
        "--no-checkpoint",
        *extra,
        "smoke idea",
    ]


def test_allowlist_and_helper_smoke(tmp_path: Path) -> None:
    """Allowlist exposes the documented prefixes and the helper short-circuits
    on a non-git path (best-effort safety net, never raises)."""
    assert ".aider." in _AIDER_RUNTIME_ALLOWLIST_PREFIXES
    assert ".ai-cockpit/suggestions/" in _AIDER_RUNTIME_ALLOWLIST_PREFIXES
    assert ".ai-cockpit/history/" in _AIDER_RUNTIME_ALLOWLIST_PREFIXES
    assert _dirty_paths_outside_aider_allowlist(str(tmp_path)) == []


def test_helper_filters_user_vs_runtime(tmp_path: Path) -> None:
    """Mixed dirty tree: aider runtime paths drop, user paths surface."""
    _init_git_repo(tmp_path)
    (tmp_path / ".aider.chat.history.md").write_text("aider noise\n")
    (tmp_path / ".ai-cockpit").mkdir()
    (tmp_path / ".ai-cockpit" / "suggestions").mkdir()
    (tmp_path / ".ai-cockpit" / "suggestions" / "x.json").write_text("{}")
    (tmp_path / "user_wip.py").write_text("print('wip')\n")
    assert _dirty_paths_outside_aider_allowlist(str(tmp_path)) == ["user_wip.py"]


def test_clean_tree_allows_aider_apply(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    result = CliRunner().invoke(cli_main, _aider_apply_cmd(tmp_path))
    assert result.exit_code == 0, result.output + (result.stderr or "")
    assert "dirty working tree" not in (result.stderr or "")


def test_dirty_tree_blocks_aider_apply_with_hint(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / "README.md").write_text("user wip change\n")
    result = CliRunner().invoke(cli_main, _aider_apply_cmd(tmp_path))
    assert result.exit_code != 0
    stderr = result.stderr or ""
    assert "dirty working tree blocks" in stderr
    assert "git checkout -- README.md" in stderr


def test_untracked_user_file_blocks_aider_apply(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / "scratch.py").write_text("# wip\n")
    result = CliRunner().invoke(cli_main, _aider_apply_cmd(tmp_path))
    assert result.exit_code != 0
    assert "git checkout -- scratch.py" in (result.stderr or "")


def test_aider_runtime_only_dirty_does_not_block(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / ".aider.chat.history.md").write_text("aider chatter\n")
    result = CliRunner().invoke(cli_main, _aider_apply_cmd(tmp_path))
    assert result.exit_code == 0, result.output + (result.stderr or "")
    assert "dirty working tree" not in (result.stderr or "")


def test_allow_dirty_tree_bypasses_guard(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / "README.md").write_text("user wip change\n")
    result = CliRunner().invoke(
        cli_main, _aider_apply_cmd(tmp_path, "--allow-dirty-tree")
    )
    assert result.exit_code == 0, result.output + (result.stderr or "")
    assert "dirty working tree blocks" not in (result.stderr or "")


def test_stub_worker_unaffected_on_dirty_tree(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / "README.md").write_text("user wip change\n")
    result = CliRunner().invoke(
        cli_main,
        [
            "--root", str(tmp_path), "--max-loops", "1",
            "--worker", "stub", "--dry-run", "--no-checkpoint", "smoke idea",
        ],
    )
    assert result.exit_code == 0, result.output + (result.stderr or "")
    assert "dirty working tree" not in (result.stderr or "")


def test_aider_preview_unaffected_on_dirty_tree(tmp_path: Path) -> None:
    """``--worker aider`` without ``--apply`` is preview-only, must NOT trip the guard."""
    _init_git_repo(tmp_path)
    (tmp_path / "README.md").write_text("user wip change\n")
    result = CliRunner().invoke(
        cli_main,
        [
            "--root", str(tmp_path), "--max-loops", "1",
            "--worker", "aider", "--no-checkpoint", "smoke idea",
        ],
    )
    assert result.exit_code == 0, result.output + (result.stderr or "")
    assert "dirty working tree" not in (result.stderr or "")
