"""v0.2 step-3 DoD tests: SQLite checkpoint + interrupt/resume.

These tests exercise the LangGraph ``SqliteSaver`` integration end-to-end:
they interrupt a run before the ``coder`` node, simulate the process
exiting (the saver context closes), then re-open the database in a fresh
process-equivalent state and continue. The resumed run must walk the
remaining nodes (coder -> verifier -> reviewer -> decision -> summary)
and produce ``final_summary``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ai_cockpit.checkpoint import (
    new_thread_id,
    open_checkpoint_saver,
    resolve_checkpoint_db,
)
from ai_cockpit.graph import build_graph, run_graph
from ai_cockpit.state import initial_state


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


def test_resolve_checkpoint_db_creates_parent(tmp_path: Path) -> None:
    db = resolve_checkpoint_db(tmp_path)
    assert db.parent.exists()
    assert db.name == "checkpoints.sqlite"
    assert db.parent.name == "history"
    assert db.is_absolute()


def test_resolve_checkpoint_db_respects_override(tmp_path: Path) -> None:
    db = resolve_checkpoint_db(tmp_path, override="custom/path.sqlite")
    assert db.parent.name == "custom"
    assert db.parent.exists()
    assert db.name == "path.sqlite"


def test_run_graph_with_thread_id_persists_and_returns(repo: Path) -> None:
    """Smoke: enabling checkpointing must not change happy-path output."""

    final = run_graph(
        user_input="checkpointed run",
        project_root=str(repo),
        max_loops=1,
        dry_run=True,
        thread_id="t-smoke",
    )

    assert final.get("final_summary"), "checkpointed run should still reach summary"
    assert final["decision"] in {"done", "ask_human"}

    db = resolve_checkpoint_db(str(repo))
    assert db.exists(), "checkpoint DB should be written"
    assert db.stat().st_size > 0


def test_resume_after_interrupt_completes_run(repo: Path) -> None:
    """The DoD: interrupt mid-run, resume from DB, run finishes."""

    db = resolve_checkpoint_db(str(repo))
    thread_id = new_thread_id()
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 25,
    }

    state = initial_state(
        user_input="resume me please",
        project_root=str(repo),
        max_loops=1,
        dry_run=True,
    )

    # Phase 1: run with an interrupt before the coder node. The graph
    # halts before coder, so coder_result must NOT yet be populated.
    with open_checkpoint_saver(db) as saver:
        graph = build_graph(checkpointer=saver, interrupt_before=["coder"])
        partial = graph.invoke(state, config=config)

    assert partial.get("idea"), "intake should have populated idea"
    assert partial.get("mvp_spec"), "planner should have produced an mvp_spec"
    assert "coder_result" not in partial or not partial.get("coder_result"), (
        "coder must not have run before the interrupt"
    )
    assert "final_summary" not in partial or not partial.get("final_summary")

    # Phase 2: brand-new graph + saver (mimics a fresh process). With
    # no interrupts and the same thread_id, invoking with `None` must
    # resume from coder onward and finish.
    with open_checkpoint_saver(db) as saver:
        graph2 = build_graph(checkpointer=saver)
        final = graph2.invoke(None, config=config)

    assert final.get("coder_result", "").startswith("Stub worker:"), (
        "resumed run should execute coder"
    )
    assert final.get("final_summary"), "resumed run should reach summary"
    assert "AI Cockpit — Run Summary" in final["final_summary"]
    assert final["decision"] in {"done", "ask_human"}


def test_resume_via_run_graph_helper(repo: Path) -> None:
    """The public run_graph(resume=True) path should also continue work."""

    db = resolve_checkpoint_db(str(repo))
    thread_id = new_thread_id()
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 25,
    }

    # Manually drive an interrupt so the public helper has something to
    # resume from.
    state = initial_state(
        user_input="resume via helper",
        project_root=str(repo),
        max_loops=1,
        dry_run=True,
    )
    with open_checkpoint_saver(db) as saver:
        graph = build_graph(checkpointer=saver, interrupt_before=["coder"])
        graph.invoke(state, config=config)

    final = run_graph(
        user_input="",
        project_root=str(repo),
        max_loops=1,
        dry_run=True,
        thread_id=thread_id,
        resume=True,
    )
    assert final.get("final_summary"), "run_graph(resume=True) should finish"
    assert final.get("coder_result", "").startswith("Stub worker:")


def test_resume_without_thread_id_raises() -> None:
    with pytest.raises(ValueError):
        run_graph(
            user_input="ignored",
            project_root=".",
            resume=True,
        )
