"""B.6b — ``plans run`` dependency-check and stub-worker execution tests."""

from __future__ import annotations

import shlex
from pathlib import Path

import pytest
from click.testing import CliRunner

from ai_cockpit.cli import main as cli_main
from ai_cockpit.graph import slice_to_user_input
from ai_cockpit.plans import (
    DependencyError,
    Plan,
    Slice,
    check_dependencies,
    find_plan_markers,
    make_commit_marker,
    save_plan,
)
from ai_cockpit.tools.shell import run_command


def _git(cmd: str, cwd: Path) -> None:
    result = run_command(cmd, cwd=cwd)
    assert result["exit_code"] == 0, f"{cmd}: {result['stderr']!r}"


def _slice(sid: str, deps: list[str]) -> Slice:
    return Slice(
        id=sid,
        depends_on=deps,
        title=f"slice {sid}",
        why=f"why-{sid}",
        scope_must=[f"do-{sid}"],
        scope_out=["nothing else"],
        dod=[f"{sid} merged"],
        files_budget=1,
        loc_budget=10,
        test_commands=[],
    )


def _make_plan(plan_id: str = "demo-plan") -> Plan:
    return Plan(
        plan_id=plan_id,
        created_at="2026-05-16T16:30:00+00:00",
        idea="Two-slice fixture used to exercise plans run.",
        acceptance_criteria=["both slices merged"],
        slices=[_slice("slice-a", []), _slice("slice-b", ["slice-a"])],
    )


@pytest.fixture
def plan_repo(tmp_path: Path) -> tuple[Path, Plan]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("git init -q -b main", cwd=repo)
    _git("git config user.email cron@test", cwd=repo)
    _git("git config user.name cron-test", cwd=repo)
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    _git("git add README.md", cwd=repo)
    _git("git commit -q -m seed", cwd=repo)
    plan = _make_plan()
    save_plan(repo / "docs" / "plans" / f"{plan.plan_id}.plan.yaml", plan)
    return repo, plan


def _commit_with_marker(repo: Path, plan_id: str, slice_id: str) -> None:
    marker = make_commit_marker(plan_id, slice_id)
    fname = f"{slice_id}.txt"
    (repo / fname).write_text(slice_id + "\n", encoding="utf-8")
    _git(f"git add {fname}", cwd=repo)
    _git(f"git commit -q -m {shlex.quote(slice_id + ': ' + marker)}", cwd=repo)


def test_marker_round_trips_and_check_deps(plan_repo: tuple[Path, Plan]) -> None:
    repo, plan = plan_repo
    marker = make_commit_marker(plan.plan_id, "slice-a")
    assert plan.plan_id in marker and "slice-a" in marker
    with pytest.raises(DependencyError) as exc:
        check_dependencies(repo, plan.plan_id, ["slice-a"])
    assert "slice-a" in str(exc.value)
    _commit_with_marker(repo, plan.plan_id, "slice-a")
    assert "slice-a" in find_plan_markers(repo, plan.plan_id)
    assert "slice-b" not in find_plan_markers(repo, plan.plan_id)
    check_dependencies(repo, plan.plan_id, ["slice-a"])


def test_slice_to_user_input_carries_marker_and_scope(
    plan_repo: tuple[Path, Plan],
) -> None:
    _, plan = plan_repo
    rendered = slice_to_user_input(plan, plan.slices[1])
    for needle in (
        "slice slice-b",
        "why-slice-b",
        "do-slice-b",
        "nothing else",
        "slice-b merged",
        make_commit_marker(plan.plan_id, "slice-b"),
    ):
        assert needle in rendered, f"missing {needle!r} in rendered slice"


@pytest.mark.parametrize(
    ("argv_extra", "needle"),
    [
        (["no-such-plan", "slice-x"], "no-such-plan"),
        (["demo-plan", "slice-z"], "slice-z"),
        (["demo-plan", "slice-b"], "slice-a"),
    ],
)
def test_plans_run_rejects_with_helpful_message(
    plan_repo: tuple[Path, Plan], argv_extra: list[str], needle: str,
) -> None:
    repo, _ = plan_repo
    runner = CliRunner()
    result = runner.invoke(
        cli_main,
        ["plans", "run", *argv_extra, "--root", str(repo), "--no-checkpoint"],
    )
    assert result.exit_code != 0
    assert needle in result.output


def test_plans_run_executes_when_no_deps(plan_repo: tuple[Path, Plan]) -> None:
    repo, plan = plan_repo
    runner = CliRunner()
    result = runner.invoke(
        cli_main,
        [
            "plans", "run", plan.plan_id, "slice-a",
            "--root", str(repo), "--no-checkpoint", "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "running slice demo-plan/slice-a" in result.output


def test_plans_run_allow_dirty_tree_skips_a7_precheck(
    plan_repo: tuple[Path, Plan], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression surfaced by the 2026-05-17 v0.4 gate run:

    ``ai-cockpit plan ... /save`` writes ``docs/plans/<id>.plan.yaml``
    as an untracked file, which the A.7 precheck would refuse for
    ``--worker aider --apply``. Without ``--allow-dirty-tree`` on
    ``plans run`` there is no way to proceed, so the legacy
    ``ai-cockpit run --allow-dirty-tree`` bypass must work here too.

    Mock both the precheck and the graph runner: the test only cares
    about whether the precheck branch is taken, not whether aider can
    actually spawn in CI.
    """
    repo, plan = plan_repo
    seen: list[str] = []

    def _fake_precheck(*args: object, **kwargs: object) -> None:
        seen.append("precheck-called")

    def _fake_run_graph(**_: object) -> dict[str, object]:
        return {"final_summary": "stubbed by test"}

    monkeypatch.setattr(
        "ai_cockpit.cli._enforce_dirty_tree_precheck", _fake_precheck
    )
    monkeypatch.setattr("ai_cockpit.cli.run_graph", _fake_run_graph)
    runner = CliRunner()
    result = runner.invoke(
        cli_main,
        [
            "plans", "run", plan.plan_id, "slice-a",
            "--root", str(repo), "--no-checkpoint",
            "--worker", "aider", "--apply", "--allow-dirty-tree",
        ],
    )
    assert result.exit_code == 0, result.output
    assert seen == [], "A.7 precheck should be skipped under --allow-dirty-tree"
    assert "A.7 precheck skipped on plans run" in result.output


def test_plans_run_blocks_without_allow_dirty_tree(
    plan_repo: tuple[Path, Plan], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without ``--allow-dirty-tree``, ``--worker aider --apply`` must
    reach the A.7 precheck path (parity with the legacy
    ``ai-cockpit run`` surface)."""
    repo, plan = plan_repo
    called: list[str] = []

    def _fake_precheck(root: str, *, worker_name: str = "aider") -> None:
        called.append(worker_name)

    def _fake_run_graph(**_: object) -> dict[str, object]:
        return {"final_summary": "stubbed by test"}

    monkeypatch.setattr(
        "ai_cockpit.cli._enforce_dirty_tree_precheck", _fake_precheck
    )
    monkeypatch.setattr("ai_cockpit.cli.run_graph", _fake_run_graph)
    runner = CliRunner()
    result = runner.invoke(
        cli_main,
        [
            "plans", "run", plan.plan_id, "slice-a",
            "--root", str(repo), "--no-checkpoint",
            "--worker", "aider", "--apply",
        ],
    )
    assert result.exit_code == 0, result.output
    assert called == ["aider"], "A.7 precheck must run when flag is absent"


def test_plans_run_writes_memory_suggestion_when_state_is_done(
    plan_repo: tuple[Path, Plan], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bug G regression (2026-05-17 v0.4 gate attempt 8): after a
    successful ``plans run`` the memory pipeline must write a
    suggestion under ``<root>/.ai-cockpit/suggestions/``. Legacy
    ``ai-cockpit run`` had this wired since PR #15 / v0.2 step 5a,
    but B.6 PR #50 (``plans run``) shipped without it — making
    B.5 §3 Q1 ('≥1 done suggestion applied via accept_suggestion')
    unsatisfiable through the gate's plan-driven path.
    """

    repo, plan = plan_repo
    state_seen: list[object] = []

    def _fake_run_graph(**_: object) -> dict[str, object]:
        return {
            "idea": "Fix bugs",
            "mvp_spec": "Fix calc.py add to return a + b",
            "decision": "done",
            "git_diff": "-return a - b\n+return a + b\n",
            "final_summary": "stubbed by test",
        }

    def _fake_generate(project_root: str, state: object):
        from ai_cockpit.memory.suggestions import Suggestion

        state_seen.append((project_root, state))
        return Suggestion(
            id="20260517T999999-done-stub",
            target="project.md",
            operation="append",
            content="stub suggestion",
            rationale="test fixture",
            created_at="2026-05-17T14:00:00+00:00",
        )

    monkeypatch.setattr("ai_cockpit.cli.run_graph", _fake_run_graph)
    monkeypatch.setattr("ai_cockpit.cli.generate_and_write", _fake_generate)
    runner = CliRunner()
    result = runner.invoke(
        cli_main,
        [
            "plans", "run", plan.plan_id, "slice-a",
            "--root", str(repo), "--no-checkpoint", "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output
    assert len(state_seen) == 1, (
        "Bug G regression: plans run must call generate_and_write "
        f"exactly once after run_graph returns; got {state_seen!r}"
    )
    entry = state_seen[0]
    assert isinstance(entry, tuple) and len(entry) == 2
    captured_root, captured_state = entry
    assert captured_root == str(repo)
    assert isinstance(captured_state, dict)
    assert captured_state["decision"] == "done"
    assert "memory suggestion written: 20260517T999999-done-stub" in result.output


def test_plans_run_skips_memory_suggestion_with_no_suggest(
    plan_repo: tuple[Path, Plan], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``plans run --no-suggest`` must NOT call generate_and_write —
    symmetric guard against accidentally always-on suggestion writes."""

    repo, plan = plan_repo
    calls: list[object] = []

    def _fake_run_graph(**_: object) -> dict[str, object]:
        return {"decision": "done", "final_summary": "ok"}

    def _fake_generate(*_args: object, **_kw: object) -> object:
        calls.append("called")
        raise AssertionError("generate_and_write must not be called under --no-suggest")

    monkeypatch.setattr("ai_cockpit.cli.run_graph", _fake_run_graph)
    monkeypatch.setattr("ai_cockpit.cli.generate_and_write", _fake_generate)
    runner = CliRunner()
    result = runner.invoke(
        cli_main,
        [
            "plans", "run", plan.plan_id, "slice-a",
            "--root", str(repo), "--no-checkpoint", "--dry-run",
            "--no-suggest",
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls == [], "--no-suggest must skip the memory pipeline"
    assert "memory suggestion written" not in result.output
