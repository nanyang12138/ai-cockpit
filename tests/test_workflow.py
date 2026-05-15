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
