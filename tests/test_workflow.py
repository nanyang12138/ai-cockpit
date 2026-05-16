"""Tests for the v0.2 step 4 workflow loader and CLI integration."""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import pytest
from click.testing import CliRunner

from ai_cockpit.cli import main as cli_main
from ai_cockpit.workflow import (
    CANONICAL_NODE_ORDER,
    WorkflowError,
    default_workflow_path,
    load_default_workflow,
    load_workflow,
    parse_workflow,
)


def _base(**ovr: object) -> dict[str, object]:
    data: dict[str, object] = {"name": "demo", "mode": "exploration", "max_loops": 1, "nodes": list(CANONICAL_NODE_ORDER)}
    data.update(ovr)
    return data


# --- workflow.py unit tests --------------------------------------------------


def test_repo_yaml_matches_canonical_order() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    w = load_workflow(default_workflow_path(repo_root))
    assert w.node_order == CANONICAL_NODE_ORDER
    assert (w.mode, w.max_loops) == ("exploration", 1)


def test_bug_fix_workflow_is_valid_and_seeds_test_commands() -> None:
    """v0.3 micro-step #2: bug-fix.yaml must parse, match the graph
    topology, and ship a non-empty default verifier.test_commands so the
    reviewer's lint/tests evidence is collected by default."""

    repo_root = Path(__file__).resolve().parents[1]
    bug_fix = repo_root / ".ai-cockpit" / "workflows" / "bug-fix.yaml"
    assert bug_fix.is_file(), "bug-fix.yaml must ship in the repo"

    w = load_workflow(bug_fix)
    assert w.node_order == CANONICAL_NODE_ORDER
    assert w.mode == "task"
    assert w.max_loops >= 2, "bug-fix mode should allow worker iteration"
    cmds = w.verifier_test_commands()
    assert cmds, "bug-fix workflow must seed test commands"
    joined = " | ".join(cmds)
    assert "pytest" in joined
    assert "ruff" in joined


def test_parse_workflow_valid_and_verifier_test_commands() -> None:
    w = parse_workflow(_base(mode="task", max_loops=2))
    assert (w.mode, w.max_loops, w.defaults, w.verifier_test_commands()) == (
        "task", 2, {}, ()
    )
    w = parse_workflow(_base(defaults={"verifier": {"test_commands": ["a", "b"]}}))
    assert w.verifier_test_commands() == ("a", "b")


@pytest.mark.parametrize(
    "data, match",
    [
        (
            _base(nodes=["intake", "rogue", "planner", "coder", "verifier", "reviewer", "decision", "summary"]),
            "out of sync",
        ),
        (_base(mode="swarm"), "mode must be one of"),
        (_base(max_loops=-1), ">= 0"),
        (_base(defaults={"bogus": {}}), "unknown node"),
        ({"mode": "exploration", "max_loops": 1, "nodes": list(CANONICAL_NODE_ORDER)}, "name"),
    ],
)
def test_parse_workflow_rejects_invalid(data: dict[str, object], match: str) -> None:
    with pytest.raises(WorkflowError, match=match):
        parse_workflow(data)


def test_load_workflow_io_errors(tmp_path: Path) -> None:
    with pytest.raises(WorkflowError, match="not found"):
        load_workflow(tmp_path / "nope.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: demo\nmode: [\n")
    with pytest.raises(WorkflowError, match="invalid YAML"):
        load_workflow(bad)
    assert load_default_workflow(tmp_path) is None


# --- CLI integration tests ---------------------------------------------------


def _init_git(path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.test"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "tester"], cwd=path, check=True)
    (path / "README.md").write_text("hi")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)


def _write_default_workflow(repo: Path, body: str) -> Path:
    wf = repo / ".ai-cockpit" / "workflows"
    wf.mkdir(parents=True, exist_ok=True)
    p = wf / "idea-to-mvp.yaml"
    p.write_text(textwrap.dedent(body).strip() + "\n")
    return p


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    _init_git(tmp_path)
    return tmp_path


def test_cli_layers_workflow_defaults_under_explicit_flags(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_default_workflow(
        repo,
        """
        name: idea-to-mvp
        mode: task
        max_loops: 4
        nodes: [intake, planner, coder, verifier, reviewer, decision, summary]
        defaults:
          verifier:
            test_commands: ["echo from-yaml"]
        """,
    )
    captured: dict[str, object] = {}
    monkeypatch.setattr("ai_cockpit.cli.run_graph", lambda **kw: captured.update(kw))
    runner = CliRunner()

    r = runner.invoke(cli_main, ["--root", str(repo), "--dry-run", "idea one"], catch_exceptions=False)
    assert r.exit_code == 0, r.output
    assert (captured["mode"], captured["max_loops"]) == ("task", 4)
    assert captured["test_commands"] == ["echo from-yaml"]

    captured.clear()
    r = runner.invoke(
        cli_main,
        [
            "--root", str(repo), "--dry-run",
            "--mode", "exploration", "--max-loops", "1",
            "--test-command", "echo explicit", "idea two",
        ],
        catch_exceptions=False,
    )
    assert r.exit_code == 0, r.output
    assert (captured["mode"], captured["max_loops"]) == ("exploration", 1)
    assert captured["test_commands"] == ["echo from-yaml", "echo explicit"]


def test_cli_node_drift_in_yaml_is_loud(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_default_workflow(
        repo,
        """
        name: idea-to-mvp
        mode: exploration
        max_loops: 1
        nodes: [intake, planner, rogue, coder, verifier, reviewer, decision, summary]
        """,
    )
    monkeypatch.setattr("ai_cockpit.cli.run_graph", lambda **_: {})
    r = CliRunner().invoke(cli_main, ["--root", str(repo), "--dry-run", "idea"])
    assert r.exit_code != 0 and "out of sync" in r.output


def test_cli_works_without_workflow_yaml(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr("ai_cockpit.cli.run_graph", lambda **kw: captured.update(kw))
    r = CliRunner().invoke(
        cli_main, ["--root", str(repo), "--dry-run", "idea three"], catch_exceptions=False
    )
    assert r.exit_code == 0, r.output
    assert (captured["mode"], captured["max_loops"], captured["test_commands"]) == (
        "exploration", 1, []
    )


def test_cli_explicit_workflow_path_override(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custom = tmp_path / "custom.yaml"
    custom.write_text(
        "name: custom\nmode: task\nmax_loops: 2\n"
        f"nodes: {list(CANONICAL_NODE_ORDER)}\n"
    )
    captured: dict[str, object] = {}
    monkeypatch.setattr("ai_cockpit.cli.run_graph", lambda **kw: captured.update(kw))
    r = CliRunner().invoke(
        cli_main,
        ["--root", str(repo), "--workflow", str(custom), "--dry-run", "idea"],
        catch_exceptions=False,
    )
    assert r.exit_code == 0, r.output
    assert (captured["mode"], captured["max_loops"]) == ("task", 2)


# --- A.4: `workflows list` / `workflows validate` subcommands ---------------


def test_workflows_list_on_repo_yamls() -> None:
    """`workflows list --root <repo>` should enumerate the two repo YAMLs."""
    repo_root = Path(__file__).resolve().parents[1]
    r = CliRunner().invoke(
        cli_main,
        ["workflows", "list", "--root", str(repo_root)],
        catch_exceptions=False,
    )
    assert r.exit_code == 0, r.output
    lines = r.output.strip().splitlines()
    assert lines[0] == "name\tmode\tmax_loops\ttest_commands_count"
    body = "\n".join(lines[1:])
    assert "idea-to-mvp\texploration\t1\t0" in body
    bug_fix_line = next(line for line in lines[1:] if line.startswith("bug-fix\t"))
    parts = bug_fix_line.split("\t")
    assert parts[1] == "task"
    assert int(parts[2]) >= 2
    assert int(parts[3]) >= 1


def test_workflows_list_no_dir_prints_marker(tmp_path: Path) -> None:
    r = CliRunner().invoke(
        cli_main,
        ["workflows", "list", "--root", str(tmp_path)],
        catch_exceptions=False,
    )
    assert r.exit_code == 0, r.output
    assert r.output.strip() == "no workflows found"


def test_workflows_list_reports_invalid_yaml_inline(tmp_path: Path) -> None:
    """Invalid YAMLs surface as a per-row INVALID marker, not a hard error."""
    wf_dir = tmp_path / ".ai-cockpit" / "workflows"
    wf_dir.mkdir(parents=True)
    good = wf_dir / "good.yaml"
    good.write_text(
        "name: good\nmode: exploration\nmax_loops: 1\n"
        f"nodes: {list(CANONICAL_NODE_ORDER)}\n"
    )
    bad = wf_dir / "bad.yaml"
    bad.write_text("name: bad\nmode: swarm\nmax_loops: 1\n"
                   f"nodes: {list(CANONICAL_NODE_ORDER)}\n")
    r = CliRunner().invoke(
        cli_main,
        ["workflows", "list", "--root", str(tmp_path)],
        catch_exceptions=False,
    )
    assert r.exit_code == 0, r.output
    out = r.output
    assert "good\texploration\t1\t0" in out
    bad_line = next(line for line in out.splitlines() if line.startswith("bad\t"))
    assert "INVALID" in bad_line and "mode must be one of" in bad_line


def test_workflows_validate_ok_on_repo_yamls() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    for fname in ("idea-to-mvp.yaml", "bug-fix.yaml"):
        path = repo_root / ".ai-cockpit" / "workflows" / fname
        r = CliRunner().invoke(
            cli_main,
            ["workflows", "validate", str(path)],
            catch_exceptions=False,
        )
        assert r.exit_code == 0, r.output
        assert r.output.strip() == "OK"


def test_workflows_validate_surfaces_workflow_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "name: bad\nmode: exploration\nmax_loops: 1\n"
        "nodes: [intake, planner, rogue, coder, verifier, reviewer, decision, summary]\n"
    )
    r = CliRunner().invoke(
        cli_main,
        ["workflows", "validate", str(bad)],
        catch_exceptions=False,
    )
    assert r.exit_code != 0
    assert "out of sync" in r.output


def test_workflows_validate_missing_file_is_usage_error(tmp_path: Path) -> None:
    missing = tmp_path / "nope.yaml"
    r = CliRunner().invoke(
        cli_main,
        ["workflows", "validate", str(missing)],
        catch_exceptions=False,
    )
    assert r.exit_code != 0


def test_default_group_does_not_route_workflows_to_run(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`ai-cockpit workflows ...` must NOT be silently rewritten to `run workflows ...`."""
    called: dict[str, object] = {}
    monkeypatch.setattr("ai_cockpit.cli.run_graph", lambda **kw: called.update(kw))
    r = CliRunner().invoke(
        cli_main,
        ["workflows", "list", "--root", str(repo)],
        catch_exceptions=False,
    )
    assert r.exit_code == 0, r.output
    assert called == {}, "run_graph should not have been invoked"
