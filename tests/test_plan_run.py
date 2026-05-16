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
