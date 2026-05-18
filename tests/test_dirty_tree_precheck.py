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


# ---------------------------------------------------------------------------
# v0.5 row #10 follow-up: ``ai-cockpit init`` artifacts must be allow-listed
# so the init → run flow has no manual git-commit step in between. Surfaced
# on 2026-05-18 06:30 UTC by the first real-user-mode invocation.
# ---------------------------------------------------------------------------


def test_init_config_files_allowlisted(tmp_path: Path) -> None:
    """``.ai-cockpit/config.yaml`` + ``.ai-cockpit/config.local.yaml`` must
    not block ``--apply`` runs — they're user-intentional project metadata,
    not WIP code."""
    _init_git_repo(tmp_path)
    cfg_dir = tmp_path / ".ai-cockpit"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text("schema_version: 1\ndefaults:\n  llm: auto\n")
    (cfg_dir / "config.local.yaml").write_text(
        "schema_version: 1\ndefaults:\n  worker: cursor\n"
    )
    assert _dirty_paths_outside_aider_allowlist(str(tmp_path)) == []


def test_init_config_backup_allowlisted(tmp_path: Path) -> None:
    """``init --force`` backups (``config.yaml.bak.<ts>``) must also be
    allow-listed — they're produced by the tool, not the operator."""
    _init_git_repo(tmp_path)
    cfg_dir = tmp_path / ".ai-cockpit"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml.bak.20260518T063000Z").write_text("old: config\n")
    assert _dirty_paths_outside_aider_allowlist(str(tmp_path)) == []


def test_gitignore_allowlisted(tmp_path: Path) -> None:
    """A dirty ``.gitignore`` (typically the ``init`` append) must not
    block ``--apply``. Aider runs with ``--no-gitignore`` so it cannot
    squash a genuine gitignore WIP; cursor likewise does not auto-edit
    top-level metadata during normal task execution."""
    _init_git_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("**/.ai-cockpit/config.local.yaml\n")
    assert _dirty_paths_outside_aider_allowlist(str(tmp_path)) == []


def test_init_then_run_no_commit_in_between(tmp_path: Path) -> None:
    """End-to-end: ``ai-cockpit init`` immediately followed by
    ``ai-cockpit run --worker aider --apply`` must NOT trip the
    dirty-tree guard — the two-step flow is exactly what a fresh-checkout
    operator runs on day 1."""
    _init_git_repo(tmp_path)
    # Mirror the real scenario: the workflow file is already committed
    # (it ships with the project). What's NOT committed is everything
    # `init` itself creates.
    workflows = tmp_path / ".ai-cockpit" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "bug-fix.yaml").write_text(
        "name: bug-fix\nmode: task\nmax_loops: 1\n"
        "nodes: [intake, planner, coder, verifier, reviewer, decision, summary]\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", ".ai-cockpit"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "add workflows"], cwd=tmp_path, check=True
    )
    # Step 1: init (writes config.yaml + appends to .gitignore).
    init_result = CliRunner().invoke(
        cli_main,
        ["init", "--root", str(tmp_path)],
        input="\n".join(["", "", "", "", "", ""]) + "\n",
    )
    assert init_result.exit_code == 0, init_result.output
    # Step 2: run --apply, no manual git-commit between them.
    run_result = CliRunner().invoke(cli_main, _aider_apply_cmd(tmp_path))
    # The critical assertion: dirty-tree guard does NOT fire even though
    # init left the working tree dirty (config.yaml + .gitignore + workflow
    # all freshly created).
    assert "dirty working tree" not in (run_result.stderr or "")
    # The run itself may or may not succeed depending on aider availability;
    # this test only cares that the dirty-tree precheck didn't block.


def test_user_wip_still_blocks_even_with_config_present(tmp_path: Path) -> None:
    """Regression guard: allow-listing config files must NOT mask user WIP
    in OTHER paths."""
    _init_git_repo(tmp_path)
    cfg_dir = tmp_path / ".ai-cockpit"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text("schema_version: 1\n")
    (tmp_path / "src" / "real_wip.py").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "src" / "real_wip.py").write_text("# unfinished\n")
    dirty = _dirty_paths_outside_aider_allowlist(str(tmp_path))
    assert "src/real_wip.py" in dirty
    assert ".ai-cockpit/config.yaml" not in dirty


def test_init_banner_suggests_commit(tmp_path: Path) -> None:
    """The wizard's closing banner now reminds the operator to commit."""
    _init_git_repo(tmp_path)
    result = CliRunner().invoke(
        cli_main,
        ["init", "--root", str(tmp_path)],
        input="\n".join(["", "", "", "", "", ""]) + "\n",
    )
    assert result.exit_code == 0, result.output
    assert "git add .ai-cockpit/config.yaml .gitignore" in result.output
    assert "git commit" in result.output
