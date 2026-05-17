"""Tests for B.9a interactive planner CLI shell."""

from __future__ import annotations

from pathlib import Path

import yaml
from click.testing import CliRunner

from ai_cockpit.cli import main as cli_main


def test_plan_rejects_real_llm_without_tty(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli_main,
        ["plan", "ship interactive planner", "--root", str(tmp_path), "--llm", "auto"],
    )

    assert result.exit_code != 0
    assert "Interactive planner requires a TTY" in result.output


def test_plan_abort_writes_nothing(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli_main,
        ["plan", "ship interactive planner", "--root", str(tmp_path), "--llm", "none"],
        input="/abort\n",
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    assert "aborted; no plan written" in result.output
    assert not (tmp_path / "docs" / "plans").exists()


def test_plan_exit_aliases_each_quit_repl(tmp_path: Path) -> None:
    """``/abort`` plus ``/quit``, ``/exit``, ``/q`` all leave the REPL
    cleanly without writing a plan. Coverage for the B.10pty bugfix
    that lifted the literal-``/abort`` check to a small alias set so
    operators with muscle memory from other shells (vim, less, psql)
    don't get stuck in the prompt.
    """
    runner = CliRunner()
    for command in ("/quit", "/exit", "/q"):
        result = runner.invoke(
            cli_main,
            ["plan", "ship interactive planner", "--root", str(tmp_path), "--llm", "none"],
            input=f"{command}\n",
            catch_exceptions=False,
        )
        assert result.exit_code == 0, (command, result.output)
        assert "aborted; no plan written" in result.output, command
        assert not (tmp_path / "docs" / "plans").exists(), command


def test_plan_help_lists_quit_aliases(tmp_path: Path) -> None:
    """``/help`` advertises the new exit aliases so they're discoverable."""
    result = CliRunner().invoke(
        cli_main,
        ["plan", "ship interactive planner", "--root", str(tmp_path), "--llm", "none"],
        input="/help\n/abort\n",
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert "/quit" in result.output and "/exit" in result.output
    assert "/q" in result.output


def test_plan_cursor_backend_falls_back_when_unavailable(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    result = CliRunner().invoke(
        cli_main,
        [
            "plan",
            "ship cursor backend",
            "--root",
            str(tmp_path),
            "--llm",
            "none",
            "--backend",
            "cursor",
        ],
        input="/abort\n",
    )

    assert result.exit_code != 0
    assert "Cursor CLI not available" in result.output
    assert "--backend builtin" in result.output


def test_plan_save_writes_fixture_plan(tmp_path: Path) -> None:
    output = tmp_path / "custom.plan.yaml"
    result = CliRunner().invoke(
        cli_main,
        [
            "plan",
            "ship interactive planner",
            "--root",
            str(tmp_path),
            "--llm",
            "none",
            "--output",
            str(output),
        ],
        input="/save\n",
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    assert f"saved plan: {output}" in result.output
    data = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["plan_id"] == "ship-interactive-planner"
    assert data["idea"] == "ship interactive planner"
    assert data["acceptance_criteria"]
    assert data["slices"][0]["id"] == "slice-1"
    assert data["slices"][0]["scope_out"] == [
        "Do not modify source files during planning."
    ]


def test_plan_save_uses_default_docs_plans_path(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli_main,
        ["plan", "add workflows list", "--root", str(tmp_path), "--llm", "none"],
        input="/save\n",
        catch_exceptions=False,
    )

    expected = tmp_path / "docs" / "plans" / "add-workflows-list.plan.yaml"
    assert result.exit_code == 0, result.output
    assert expected.is_file()


def test_plan_subcommand_does_not_route_to_run(
    tmp_path: Path, monkeypatch
) -> None:
    called: dict[str, object] = {}
    monkeypatch.setattr("ai_cockpit.cli.run_graph", lambda **kw: called.update(kw))

    result = CliRunner().invoke(
        cli_main,
        ["plan", "do not run graph", "--root", str(tmp_path), "--llm", "none"],
        input="/abort\n",
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    assert called == {}
