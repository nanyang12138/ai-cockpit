"""Tests for the CLI flag interactions added in the step-3 follow-up.

Covers the contract change that flipped checkpointing to on-by-default:

- a default invocation auto-mints a thread id and writes the DB
- ``--no-checkpoint`` skips the DB write and is mutually exclusive with
  ``--thread-id`` / ``--resume`` / ``--checkpoint-db``
- ``--resume`` is now a boolean flag and requires ``--thread-id``
- ``--resume --thread-id ID`` continues a previously persisted run
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from click.testing import CliRunner

from ai_cockpit.checkpoint import (
    open_checkpoint_saver,
    resolve_checkpoint_db,
)
from ai_cockpit.cli import main as cli_main
from ai_cockpit.graph import build_graph
from ai_cockpit.state import initial_state


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.test"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "tester"], cwd=path, check=True)
    (path / "README.md").write_text("hi")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)


def test_default_invocation_auto_mints_thread_id_and_writes_db(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)

    result = CliRunner().invoke(
        cli_main,
        ["--root", str(tmp_path), "--max-loops", "1", "--dry-run", "smoke idea"],
    )

    assert result.exit_code == 0, result.output + (result.stderr or "")
    assert "checkpointing enabled, thread id:" in (result.stderr or "")

    db = resolve_checkpoint_db(str(tmp_path))
    assert db.exists(), "default invocation should write checkpoint DB"
    assert db.stat().st_size > 0


def test_no_checkpoint_skips_db_write(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)

    result = CliRunner().invoke(
        cli_main,
        [
            "--root",
            str(tmp_path),
            "--max-loops",
            "1",
            "--dry-run",
            "--no-checkpoint",
            "smoke idea",
        ],
    )

    assert result.exit_code == 0, result.output + (result.stderr or "")
    assert "checkpointing enabled" not in (result.stderr or "")

    db = tmp_path / ".ai-cockpit" / "history" / "checkpoints.sqlite"
    assert not db.exists(), "--no-checkpoint must not write the DB file"


def test_no_checkpoint_conflicts_with_thread_id(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)

    result = CliRunner().invoke(
        cli_main,
        [
            "--root",
            str(tmp_path),
            "--no-checkpoint",
            "--thread-id",
            "abc",
            "idea",
        ],
    )

    assert result.exit_code != 0
    assert "--no-checkpoint" in (result.stderr or "")


def test_no_checkpoint_conflicts_with_resume(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)

    result = CliRunner().invoke(
        cli_main,
        [
            "--root",
            str(tmp_path),
            "--no-checkpoint",
            "--resume",
            "--thread-id",
            "abc",
        ],
    )

    assert result.exit_code != 0
    assert "--no-checkpoint" in (result.stderr or "")


def test_no_checkpoint_conflicts_with_checkpoint_db(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)

    result = CliRunner().invoke(
        cli_main,
        [
            "--root",
            str(tmp_path),
            "--no-checkpoint",
            "--checkpoint-db",
            str(tmp_path / "x.sqlite"),
            "idea",
        ],
    )

    assert result.exit_code != 0
    assert "--no-checkpoint" in (result.stderr or "")


def test_resume_requires_thread_id(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)

    result = CliRunner().invoke(
        cli_main,
        ["--root", str(tmp_path), "--resume"],
    )

    assert result.exit_code != 0
    assert "--resume requires --thread-id" in (result.stderr or "")


def test_resume_is_boolean_not_value(tmp_path: Path) -> None:
    """--resume must NOT swallow the next positional as its value.

    Under the old (now-removed) value-taking semantics, ``--resume idea``
    would treat 'idea' as the thread id. With the boolean form, 'idea'
    stays as a positional argument; the run then errors because no
    --thread-id was given.
    """
    _init_git_repo(tmp_path)

    result = CliRunner().invoke(
        cli_main,
        ["--root", str(tmp_path), "--resume", "some-thread"],
    )

    assert result.exit_code != 0
    assert "--resume requires --thread-id" in (result.stderr or "")


def test_resume_with_thread_id_continues_persisted_run(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)

    db = resolve_checkpoint_db(str(tmp_path))
    thread_id = "resume-flag-test"
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 25,
    }

    state = initial_state(
        user_input="seed for resume",
        project_root=str(tmp_path),
        max_loops=1,
        dry_run=True,
    )
    with open_checkpoint_saver(db) as saver:
        graph = build_graph(checkpointer=saver, interrupt_before=["coder"])
        graph.invoke(state, config=config)

    result = CliRunner().invoke(
        cli_main,
        [
            "--root",
            str(tmp_path),
            "--max-loops",
            "1",
            "--dry-run",
            "--resume",
            "--thread-id",
            thread_id,
        ],
    )

    assert result.exit_code == 0, result.output + (result.stderr or "")
    assert f"resuming thread {thread_id}" in (result.stderr or "")
    assert "AI Cockpit — Run Summary" in result.output
