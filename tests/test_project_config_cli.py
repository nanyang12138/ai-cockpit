"""Integration tests for v0.5 row #10 sub-gate a-2 — CLI ↔ project_config.

Sub-gate a-1 (PR #101) shipped the loader and its unit tests. This file
covers the CLI-side wiring: ``run`` / ``plan`` / ``status`` now back-fill
DEFAULT-source flags from ``ProjectConfig``, and the ``apply: true``
stderr warning fires only when the value comes from the committed file.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from ai_cockpit.cli import main


def _write_config(root: Path, body: str, *, local: bool = False) -> Path:
    cfg_dir = root / ".ai-cockpit"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    path = cfg_dir / ("config.local.yaml" if local else "config.yaml")
    path.write_text(body, encoding="utf-8")
    return path


def test_status_reports_resolved_defaults(tmp_path: Path) -> None:
    """``ai-cockpit status`` lists each resolved default with a source marker."""
    _write_config(
        tmp_path,
        "schema_version: 1\ndefaults:\n  llm: auto\n  worker: aider\n  apply: true\n",
    )
    result = CliRunner().invoke(main, ["status", "--root", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "project_config:" in result.output
    assert "resolved_defaults:" in result.output
    assert "llm: 'auto' (P)" in result.output
    assert "worker: 'aider' (P)" in result.output
    assert "warning: --apply on by default" in result.output


def test_status_reports_local_override_marker(tmp_path: Path) -> None:
    """When the same key is in both files, source marker flips to 'L'."""
    _write_config(tmp_path, "schema_version: 1\ndefaults:\n  worker: aider\n")
    _write_config(
        tmp_path, "schema_version: 1\ndefaults:\n  worker: cursor\n", local=True
    )
    result = CliRunner().invoke(main, ["status", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "worker: 'cursor' (L)" in result.output


def test_status_invalid_config_reports_inline(tmp_path: Path) -> None:
    """Q5 credential leak: status shows INVALID without crashing."""
    _write_config(tmp_path, "LLM_API_KEY: leaked\n")
    result = CliRunner().invoke(main, ["status", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "project_config: INVALID" in result.output


def test_run_uses_config_when_flag_default_sourced(tmp_path: Path) -> None:
    """When CLI flag is at its Click default, ProjectConfig value wins."""
    _write_config(
        tmp_path,
        "schema_version: 1\ndefaults:\n  worker: aider\n",
    )
    # No --worker on the CLI; config says aider; but no --apply, so aider
    # stays in preview-only mode (no real spawn). The run completes.
    result = CliRunner().invoke(
        main,
        ["run", "smoke test", "--root", str(tmp_path), "--no-checkpoint"],
    )
    assert result.exit_code == 0, result.output
    # The preview-only info line proves worker was resolved to aider.
    assert "worker=aider preview-only" in result.stderr


def test_run_cli_flag_overrides_config(tmp_path: Path) -> None:
    """``--no-apply`` on CLI overrides ``apply: true`` from config (Q3)."""
    _write_config(tmp_path, "schema_version: 1\ndefaults:\n  apply: true\n")
    # ``--worker aider --no-apply`` should be preview-only despite config
    # setting apply=true.
    result = CliRunner().invoke(
        main,
        [
            "run", "smoke test",
            "--root", str(tmp_path),
            "--no-checkpoint",
            "--worker", "aider",
            "--no-apply",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "preview-only" in result.stderr
    # And the warning that says "config sets apply=true" MUST NOT fire,
    # because the operator explicitly overrode on this invocation.
    assert "project config sets apply=true" not in result.stderr


def test_apply_warning_fires_when_config_supplies_true(tmp_path: Path) -> None:
    """Q6: warning fires when apply=true came from config (not from CLI)."""
    _write_config(
        tmp_path,
        "schema_version: 1\ndefaults:\n  worker: aider\n  apply: true\n",
    )
    result = CliRunner().invoke(
        main,
        ["run", "smoke test", "--root", str(tmp_path), "--no-checkpoint"],
    )
    # The run itself may exit non-zero because aider isn't installed in the
    # test env, but the warning MUST be on stderr regardless.
    assert "project config sets apply=true" in result.stderr


def test_credentials_in_config_fail_run_with_typed_error(tmp_path: Path) -> None:
    """Q5: any LLM_/ANTHROPIC_/OPENAI_ key raises ProjectConfigError →
    Click UsageError exit 2."""
    _write_config(tmp_path, "ANTHROPIC_API_KEY: oops\n")
    result = CliRunner().invoke(
        main,
        ["run", "smoke test", "--root", str(tmp_path), "--no-checkpoint"],
    )
    assert result.exit_code != 0
    assert "credential-like key" in result.output or "credential-like key" in (
        result.stderr or ""
    )


def test_workflow_simple_name_in_config_resolves(tmp_path: Path) -> None:
    """Q8: a bare workflow name in config resolves to the canonical path."""
    workflows = tmp_path / ".ai-cockpit" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "custom.yaml").write_text(
        "name: custom\nmode: task\nmax_loops: 3\n"
        "nodes: [intake, planner, coder, verifier, reviewer, decision, summary]\n",
        encoding="utf-8",
    )
    _write_config(
        tmp_path,
        "schema_version: 1\ndefaults:\n  workflow: custom\n",
    )
    result = CliRunner().invoke(
        main, ["run", "smoke test", "--root", str(tmp_path), "--no-checkpoint"]
    )
    assert result.exit_code == 0, result.output
    # Mode in the run summary should reflect the loaded workflow (task).
    # v0.5 summary renderer uses inline ``Mode: task`` layout; older plain
    # mode keeps the column-aligned form. Match both.
    assert ("Mode: task" in result.output) or ("Mode:        task" in result.output)


def test_plan_back_fills_llm_from_config(tmp_path: Path) -> None:
    """``ai-cockpit plan`` also reads ProjectConfig for its applicable keys."""
    _write_config(tmp_path, "schema_version: 1\ndefaults:\n  llm: none\n")
    # llm=none is required because the runner doesn't have a TTY for the
    # interactive planner. With config setting llm=none, no --llm needed.
    result = CliRunner().invoke(
        main,
        [
            "plan", "smoke idea for plan",
            "--root", str(tmp_path),
            "--max-turns", "1",
        ],
        input="/quit\n",
    )
    # We don't require a specific exit code (the planner REPL has its own
    # paths), but the stderr must show the config was loaded.
    assert "loaded defaults from" in result.stderr


@pytest.mark.parametrize(
    "config_apply,cli_args,expected_apply_in_msg",
    [
        # Config apply=true, no CLI override → apply is True (no preview-only)
        ("true", [], False),
        # Config apply=true, CLI --no-apply → apply is False (preview-only)
        ("true", ["--no-apply"], True),
        # Config apply=false, CLI --apply → apply is True
        ("false", ["--apply"], False),
    ],
)
def test_precedence_chain_for_apply(
    tmp_path: Path,
    config_apply: str,
    cli_args: list[str],
    expected_apply_in_msg: bool,
) -> None:
    """End-to-end: CLI > config precedence for the new --apply/--no-apply pair."""
    _write_config(
        tmp_path,
        f"schema_version: 1\ndefaults:\n  worker: aider\n  apply: {config_apply}\n",
    )
    result = CliRunner().invoke(
        main,
        ["run", "test", "--root", str(tmp_path), "--no-checkpoint", *cli_args],
    )
    assert result.exit_code == 0, result.output
    if expected_apply_in_msg:
        assert "preview-only" in result.stderr
    else:
        # apply=True means worker WILL be invoked. In the test env aider
        # may not be installed; we just assert the WILL-be-invoked stderr
        # was emitted (not the preview-only one).
        assert "WILL be" in result.stderr
