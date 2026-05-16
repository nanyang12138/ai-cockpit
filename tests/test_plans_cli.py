"""B.6c — ``plans list`` / ``plans show`` read-only walker tests."""

from __future__ import annotations

import shlex
from pathlib import Path

import pytest
from click.testing import CliRunner

from ai_cockpit.cli import main as cli_main
from ai_cockpit.plans import Plan, Slice, make_commit_marker, save_plan
from ai_cockpit.tools.shell import run_command


def _git(cmd: str, cwd: Path) -> None:
    result = run_command(cmd, cwd=cwd)
    assert result["exit_code"] == 0, f"{cmd}: {result['stderr']!r}"


def _slice(sid: str, deps: list[str], title: str = "") -> Slice:
    return Slice(
        id=sid,
        depends_on=deps,
        title=title or f"slice {sid}",
        why=f"why-{sid}",
        scope_must=[f"do-{sid}"],
        scope_out=["nothing else"],
        dod=[f"{sid} merged"],
        files_budget=1,
        loc_budget=10,
        test_commands=[],
    )


def _make_plan(plan_id: str, slice_ids: list[str]) -> Plan:
    slices: list[Slice] = []
    for idx, sid in enumerate(slice_ids):
        deps = [slice_ids[idx - 1]] if idx else []
        slices.append(_slice(sid, deps, title=f"title-{sid}"))
    return Plan(
        plan_id=plan_id,
        created_at="2026-05-16T16:30:00+00:00",
        idea=f"Fixture plan {plan_id}.",
        acceptance_criteria=[f"{plan_id} ships end-to-end"],
        slices=slices,
    )


@pytest.fixture
def plan_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("git init -q -b main", cwd=repo)
    _git("git config user.email cron@test", cwd=repo)
    _git("git config user.name cron-test", cwd=repo)
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    _git("git add README.md", cwd=repo)
    _git("git commit -q -m seed", cwd=repo)
    return repo


def _save(repo: Path, plan: Plan) -> None:
    save_plan(repo / "docs" / "plans" / f"{plan.plan_id}.plan.yaml", plan)


def _commit_marker(repo: Path, plan_id: str, slice_id: str) -> None:
    marker = make_commit_marker(plan_id, slice_id)
    fname = f"{slice_id}.txt"
    (repo / fname).write_text(slice_id + "\n", encoding="utf-8")
    _git(f"git add {fname}", cwd=repo)
    _git(f"git commit -q -m {shlex.quote(slice_id + ': ' + marker)}", cwd=repo)


def test_plans_list_empty_when_no_plans_dir(plan_repo: Path) -> None:
    result = CliRunner().invoke(cli_main, ["plans", "list", "--root", str(plan_repo)])
    assert result.exit_code == 0, result.output
    assert "no plans found" in result.output


def test_plans_list_reports_total_done_next_from_git_log(plan_repo: Path) -> None:
    plan = _make_plan("demo", ["alpha", "beta", "gamma"])
    _save(plan_repo, plan)
    _commit_marker(plan_repo, "demo", "alpha")
    result = CliRunner().invoke(cli_main, ["plans", "list", "--root", str(plan_repo)])
    assert result.exit_code == 0, result.output
    lines = result.output.strip().splitlines()
    assert lines[0] == "plan_id\tcreated_at\ttotal\tdone\tnext"
    row = lines[1].split("\t")
    assert row[0] == "demo"
    assert row[2] == "3"
    assert row[3] == "1"
    assert row[4] == "beta"


def test_plans_list_next_dash_when_all_slices_merged(plan_repo: Path) -> None:
    plan = _make_plan("done-plan", ["only"])
    _save(plan_repo, plan)
    _commit_marker(plan_repo, "done-plan", "only")
    result = CliRunner().invoke(cli_main, ["plans", "list", "--root", str(plan_repo)])
    assert result.exit_code == 0, result.output
    row = result.output.strip().splitlines()[1].split("\t")
    assert row[3] == "1" and row[4] == "-"


def test_plans_list_warns_on_large_plan(plan_repo: Path) -> None:
    ids = [f"s{i:02d}" for i in range(21)]
    _save(plan_repo, _make_plan("big", ids))
    result = CliRunner().invoke(cli_main, ["plans", "list", "--root", str(plan_repo)])
    assert result.exit_code == 0, result.output
    assert "WARN" in result.output and "21 slices" in result.output


def test_plans_list_surfaces_invalid_plan(plan_repo: Path) -> None:
    plans_dir = plan_repo / "docs" / "plans"
    plans_dir.mkdir(parents=True)
    (plans_dir / "broken.plan.yaml").write_text("not: a plan\n", encoding="utf-8")
    result = CliRunner().invoke(cli_main, ["plans", "list", "--root", str(plan_repo)])
    assert result.exit_code == 0, result.output
    assert "INVALID" in result.output


def test_plans_show_marks_done_and_undone_slices(plan_repo: Path) -> None:
    plan = _make_plan("demo", ["alpha", "beta"])
    _save(plan_repo, plan)
    _commit_marker(plan_repo, "demo", "alpha")
    result = CliRunner().invoke(
        cli_main, ["plans", "show", "demo", "--root", str(plan_repo)],
    )
    assert result.exit_code == 0, result.output
    assert "plan_id: demo" in result.output
    assert "[✓] alpha: title-alpha" in result.output
    assert "[✗] beta: title-beta" in result.output


def test_plans_show_missing_plan_errors_cleanly(plan_repo: Path) -> None:
    result = CliRunner().invoke(
        cli_main, ["plans", "show", "nope", "--root", str(plan_repo)],
    )
    assert result.exit_code != 0
    assert "nope" in result.output
