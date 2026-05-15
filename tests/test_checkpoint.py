"""Tests for v0.2 step 3: SQLite checkpoint + human interrupt/resume.

What these tests guarantee:

1. ``open_sqlite_saver`` creates a usable SqliteSaver and a DB file on disk.
2. With a checkpointer + thread_id, a completed run leaves a retrievable
   final state under that thread (so resume-after-completion is a no-op).
3. ``interrupt_before`` halts the workflow mid-run; reinvoking with
   ``resume=True`` + the same thread_id finishes the workflow — this is
   the spec section "kill mid-run, resume, finish" scenario.
4. ``run_graph(resume=True)`` rejects calls missing checkpointer/thread_id.
5. CLI flag ``--no-checkpoint`` runs the workflow without creating the DB.

We use a separate temp git repo (built like the smoke tests) so verifier's
``git status`` / ``git diff`` calls succeed.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from ai_cockpit.checkpoint import default_checkpoint_path, open_sqlite_saver
from ai_cockpit.cli import main as cli_main
from ai_cockpit.graph import build_graph, run_graph


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


def test_default_checkpoint_path_is_under_ai_cockpit_history() -> None:
    p = default_checkpoint_path("/some/proj")
    assert p == Path("/some/proj/.ai-cockpit/history/checkpoints.sqlite")


def test_open_sqlite_saver_creates_db_file(tmp_path: Path) -> None:
    db = tmp_path / "nested" / "checkpoints.sqlite"
    assert not db.exists()
    with open_sqlite_saver(db) as saver:
        saver.setup()
    assert db.exists(), "SqliteSaver should have written the DB file on disk"


def test_completed_run_persists_state_under_thread(repo: Path) -> None:
    db = repo / "checkpoints.sqlite"
    thread_id = "thread-completed"

    with open_sqlite_saver(db) as saver:
        final = run_graph(
            user_input="Persist me",
            project_root=str(repo),
            max_loops=1,
            dry_run=True,
            checkpointer=saver,
            thread_id=thread_id,
        )
        assert final["decision"] in {"done", "ask_human"}

        graph = build_graph(checkpointer=saver)
        snap = graph.get_state({"configurable": {"thread_id": thread_id}})
        assert snap is not None
        persisted = dict(snap.values)
        assert persisted.get("mvp_spec") == final["mvp_spec"]
        assert "AI Cockpit" in persisted.get("final_summary", "")


def test_interrupt_and_resume_completes_workflow(repo: Path) -> None:
    """Spec DoD: kill mid-run, resume, finish."""

    db = repo / "checkpoints.sqlite"
    thread_id = "thread-interrupt"

    with open_sqlite_saver(db) as saver:
        partial = run_graph(
            user_input="Resume me",
            project_root=str(repo),
            max_loops=1,
            dry_run=True,
            checkpointer=saver,
            thread_id=thread_id,
            interrupt_before=["reviewer"],
        )

        assert "review_result" not in partial, (
            "reviewer should NOT have executed yet when interrupted before it"
        )
        assert "verification_result" in partial, (
            "verifier should have run before the reviewer interrupt"
        )

        graph_with_resume = build_graph(checkpointer=saver)
        resumed = graph_with_resume.invoke(
            None, config={"configurable": {"thread_id": thread_id}}
        )

        assert "review_result" in resumed
        assert "decision" in resumed
        assert "final_summary" in resumed
        assert "AI Cockpit" in resumed["final_summary"]


def test_resume_requires_checkpointer_and_thread(repo: Path) -> None:
    with pytest.raises(ValueError):
        run_graph(
            user_input="x",
            project_root=str(repo),
            resume=True,
        )

    with open_sqlite_saver(":memory:") as saver:
        with pytest.raises(ValueError):
            run_graph(
                user_input="x",
                project_root=str(repo),
                resume=True,
                checkpointer=saver,
            )


def test_resume_continues_same_thread_after_completion(repo: Path) -> None:
    """Resuming a fully-completed thread should not crash and should
    return the existing final state without rerunning nodes.
    """

    db = repo / "checkpoints.sqlite"
    thread_id = "thread-reresume"

    with open_sqlite_saver(db) as saver:
        first = run_graph(
            user_input="hello",
            project_root=str(repo),
            max_loops=1,
            dry_run=True,
            checkpointer=saver,
            thread_id=thread_id,
        )
        again = run_graph(
            user_input="hello",
            project_root=str(repo),
            max_loops=1,
            dry_run=True,
            checkpointer=saver,
            thread_id=thread_id,
            resume=True,
        )
        assert again["final_summary"] == first["final_summary"]
        assert again["decision"] == first["decision"]


def test_cli_no_checkpoint_skips_db_write(repo: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli_main,
        ["smoke idea", "--root", str(repo), "--dry-run", "--no-checkpoint"],
    )
    assert result.exit_code == 0, result.output
    assert not (repo / ".ai-cockpit" / "history" / "checkpoints.sqlite").exists()


def test_cli_writes_checkpoint_db_by_default(repo: Path) -> None:
    runner = CliRunner()
    db = repo / "history.sqlite"
    result = runner.invoke(
        cli_main,
        [
            "smoke idea",
            "--root",
            str(repo),
            "--dry-run",
            "--thread-id",
            "cli-thread-1",
            "--checkpoint-db",
            str(db),
        ],
    )
    assert result.exit_code == 0, result.output
    assert db.exists()


def test_cli_resume_requires_thread_id(repo: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli_main,
        ["smoke idea", "--root", str(repo), "--dry-run", "--resume"],
    )
    assert result.exit_code != 0
    assert "--resume requires --thread-id" in result.output
