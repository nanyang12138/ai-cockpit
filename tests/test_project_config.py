"""Unit tests for v0.5 row #10 sub-gate a-1 — project-config loader.

Covers the loader/validator/credential-scan/simple-name/warning policy
in ``src/ai_cockpit/project_config.py``. CLI integration tests live
in sub-gate a-2 (separate PR).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_cockpit.project_config import (
    ProjectConfigError,
    load_project_config,
    resolve_workflow_value,
)


def _write_config(root: Path, body: str, *, local: bool = False) -> Path:
    cfg_dir = root / ".ai-cockpit"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    path = cfg_dir / ("config.local.yaml" if local else "config.yaml")
    path.write_text(body, encoding="utf-8")
    return path


def test_absent_config_returns_empty(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    cfg = load_project_config(tmp_path)
    assert cfg.is_empty
    assert cfg.project_path is None
    assert cfg.local_path is None
    assert "loaded defaults" not in capfd.readouterr().err


def test_schema_valid_load(tmp_path: Path, capfd: pytest.CaptureFixture[str]) -> None:
    _write_config(
        tmp_path,
        "schema_version: 1\ndefaults:\n  llm: auto\n  worker: aider\n"
        "  apply: true\n  max_loops: 2\n  workflow: bug-fix\n",
    )
    cfg = load_project_config(tmp_path)
    assert (cfg.llm, cfg.worker, cfg.apply, cfg.max_loops, cfg.workflow) == (
        "auto", "aider", True, 2, "bug-fix"
    )
    assert all(src == "P" for _, src in cfg.sources)
    err = capfd.readouterr().err
    assert "loaded defaults from" in err and "config.yaml" in err


def test_malformed_yaml_degrades(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    _write_config(tmp_path, "this is: : not valid: yaml\n  - bad")
    cfg = load_project_config(tmp_path)
    assert cfg.is_empty
    assert "error:" in capfd.readouterr().err


def test_credentials_at_top_level_raise(tmp_path: Path) -> None:
    _write_config(tmp_path, "LLM_API_KEY: oops-this-is-a-secret\n")
    with pytest.raises(ProjectConfigError, match="credential-like key"):
        load_project_config(tmp_path)


def test_credentials_nested_raise(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        "schema_version: 1\ndefaults:\n  llm: auto\nenv:\n"
        "  ANTHROPIC_API_KEY: leaked\n",
    )
    with pytest.raises(ProjectConfigError, match="ANTHROPIC_API_KEY"):
        load_project_config(tmp_path)


def test_rejected_defaults_keys_degrade(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    _write_config(tmp_path, "schema_version: 1\ndefaults:\n  thread_id: x\n")
    cfg = load_project_config(tmp_path)
    assert cfg.is_empty
    assert "not allowed" in capfd.readouterr().err


def test_unknown_defaults_key_degrades(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    _write_config(tmp_path, "schema_version: 1\ndefaults:\n  invented: 42\n")
    cfg = load_project_config(tmp_path)
    assert cfg.is_empty
    assert "unknown 'defaults:' keys" in capfd.readouterr().err


def test_type_mismatch_degrades(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    # YAML 1.1 ``apply: yes`` parses as bool True; use a quoted string for
    # an actual type mismatch.
    _write_config(tmp_path, 'schema_version: 1\ndefaults:\n  apply: "totally-on"\n')
    cfg = load_project_config(tmp_path)
    assert cfg.is_empty
    assert "must be a boolean" in capfd.readouterr().err


def test_choice_validation_degrades(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    _write_config(tmp_path, "schema_version: 1\ndefaults:\n  worker: foo\n")
    cfg = load_project_config(tmp_path)
    assert cfg.is_empty
    assert "must be one of" in capfd.readouterr().err


def test_max_loops_range_enforced(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    _write_config(tmp_path, "schema_version: 1\ndefaults:\n  max_loops: 99\n")
    cfg = load_project_config(tmp_path)
    assert cfg.is_empty
    assert "0..10" in capfd.readouterr().err


def test_schema_version_must_be_one(
    tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    _write_config(tmp_path, "schema_version: 7\ndefaults:\n  llm: auto\n")
    cfg = load_project_config(tmp_path)
    assert cfg.is_empty
    assert "schema_version" in capfd.readouterr().err


def test_local_overrides_project(tmp_path: Path) -> None:
    _write_config(tmp_path, "schema_version: 1\ndefaults:\n  worker: aider\n  llm: auto\n")
    _write_config(
        tmp_path, "schema_version: 1\ndefaults:\n  worker: cursor\n", local=True
    )
    cfg = load_project_config(tmp_path)
    assert (cfg.worker, cfg.llm) == ("cursor", "auto")
    assert (cfg.source_of("worker"), cfg.source_of("llm")) == ("L", "P")


def test_simple_name_workflow_resolution(tmp_path: Path) -> None:
    assert resolve_workflow_value("bug-fix", tmp_path) == str(
        tmp_path / ".ai-cockpit" / "workflows" / "bug-fix.yaml"
    )


def test_literal_path_workflow_passthrough(tmp_path: Path) -> None:
    assert resolve_workflow_value("/abs/path.yaml", tmp_path) == "/abs/path.yaml"
    assert resolve_workflow_value("rel/dir/x.yml", tmp_path) == "rel/dir/x.yml"


def test_empty_defaults_block_returns_empty_config(tmp_path: Path) -> None:
    """A YAML with no ``defaults:`` key parses as an empty ProjectConfig."""
    _write_config(tmp_path, "schema_version: 1\n")
    assert load_project_config(tmp_path).is_empty
