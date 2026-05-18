"""Tests for v0.5 row #10 sub-gate b — ``ai-cockpit init`` wizard.

Covers the DoD in
``docs/V0_5_ROW_10_CLI_ERGONOMICS_CONTRACT.md`` §8 sub-gate b:
    * 6-prompt wizard generates a valid ``config.yaml``
    * Output YAML round-trips through the sub-gate-a loader
    * Refuses to overwrite without ``--force``
    * ``--force`` backs up existing config before writing
    * Banner mentions env-var requirement (no credentials in config)
    * ``.gitignore`` append for ``config.local.yaml`` is idempotent
"""

from __future__ import annotations

from pathlib import Path

import yaml
from click.testing import CliRunner

from ai_cockpit.cli import main
from ai_cockpit.project_config import (
    ensure_gitignore_entry,
    load_project_config,
)

_DEFAULT_ANSWERS = "\n".join(["", "", "", "", "", ""]) + "\n"


def test_init_writes_valid_config_with_all_defaults(tmp_path: Path) -> None:
    """Pressing Enter on every prompt produces a loadable config."""
    result = CliRunner().invoke(
        main, ["init", "--root", str(tmp_path)], input=_DEFAULT_ANSWERS
    )
    assert result.exit_code == 0, result.output
    cfg_path = tmp_path / ".ai-cockpit" / "config.yaml"
    assert cfg_path.is_file()
    data = yaml.safe_load(cfg_path.read_text())
    assert data["schema_version"] == 1
    defaults = data["defaults"]
    # Cron-locked Q9 defaults: aider worker, auto LLM, apply=False,
    # workflow=bug-fix, max_loops=1, suggest=True.
    assert defaults["llm"] == "auto"
    assert defaults["worker"] == "aider"
    assert defaults["apply"] is False
    assert defaults["workflow"] == "bug-fix"
    assert defaults["max_loops"] == 1
    assert defaults["suggest"] is True


def test_init_output_roundtrips_through_loader(tmp_path: Path) -> None:
    """The generated YAML must be byte-compatible with sub-gate a's loader."""
    result = CliRunner().invoke(
        main, ["init", "--root", str(tmp_path)], input=_DEFAULT_ANSWERS
    )
    assert result.exit_code == 0
    cfg = load_project_config(tmp_path)
    assert not cfg.is_empty
    assert cfg.llm == "auto"
    assert cfg.worker == "aider"
    assert cfg.apply is False
    assert cfg.max_loops == 1


def test_init_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".ai-cockpit"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text("schema_version: 1\ndefaults: {}\n")
    result = CliRunner().invoke(
        main, ["init", "--root", str(tmp_path)], input=_DEFAULT_ANSWERS
    )
    assert result.exit_code != 0
    assert "already exists" in result.output
    assert "--force" in result.output


def test_init_force_backs_up_existing_config(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".ai-cockpit"
    cfg_dir.mkdir()
    original = "schema_version: 1\ndefaults:\n  llm: openai\n"
    (cfg_dir / "config.yaml").write_text(original)
    result = CliRunner().invoke(
        main,
        ["init", "--root", str(tmp_path), "--force"],
        input=_DEFAULT_ANSWERS,
    )
    assert result.exit_code == 0, result.output
    backups = list(cfg_dir.glob("config.yaml.bak.*"))
    assert len(backups) == 1
    assert backups[0].read_text() == original
    # New config is the wizard output (not the original).
    new = yaml.safe_load((cfg_dir / "config.yaml").read_text())
    assert new["defaults"]["llm"] == "auto"


def test_init_banner_mentions_env_vars(tmp_path: Path) -> None:
    """The wizard must remind the operator that creds live in env vars."""
    result = CliRunner().invoke(
        main, ["init", "--root", str(tmp_path)], input=_DEFAULT_ANSWERS
    )
    assert result.exit_code == 0
    assert "LLM_API_KEY" in result.output
    assert "NEVER" in result.output  # "credentials are NEVER accepted ..."


def test_init_appends_local_override_to_gitignore(tmp_path: Path) -> None:
    """A fresh repo with no .gitignore gets one with the override entry."""
    result = CliRunner().invoke(
        main, ["init", "--root", str(tmp_path)], input=_DEFAULT_ANSWERS
    )
    assert result.exit_code == 0
    gi = (tmp_path / ".gitignore").read_text()
    assert "**/.ai-cockpit/config.local.yaml" in gi


def test_gitignore_append_is_idempotent(tmp_path: Path) -> None:
    """Calling ensure_gitignore_entry twice writes the line only once."""
    changed_first = ensure_gitignore_entry(tmp_path)
    changed_second = ensure_gitignore_entry(tmp_path)
    assert changed_first is True
    assert changed_second is False
    gi = (tmp_path / ".gitignore").read_text()
    assert gi.count("**/.ai-cockpit/config.local.yaml") == 1


def test_gitignore_append_preserves_existing_content(tmp_path: Path) -> None:
    """An existing .gitignore is not clobbered; entry is appended."""
    gi_path = tmp_path / ".gitignore"
    gi_path.write_text("node_modules/\n*.pyc\n")
    ensure_gitignore_entry(tmp_path)
    body = gi_path.read_text()
    assert "node_modules/" in body
    assert "*.pyc" in body
    assert "**/.ai-cockpit/config.local.yaml" in body


def test_init_custom_answers_propagate(tmp_path: Path) -> None:
    """Non-default answers actually land in the YAML."""
    answers = "\n".join(
        [
            "none",         # LLM provider
            "cursor",       # worker
            "y",            # apply default
            "idea-to-mvp",  # workflow
            "5",            # max_loops
            "n",            # suggest
        ]
    ) + "\n"
    result = CliRunner().invoke(
        main, ["init", "--root", str(tmp_path)], input=answers
    )
    assert result.exit_code == 0, result.output
    data = yaml.safe_load(
        (tmp_path / ".ai-cockpit" / "config.yaml").read_text()
    )
    d = data["defaults"]
    assert (d["llm"], d["worker"], d["apply"]) == ("none", "cursor", True)
    assert (d["workflow"], d["max_loops"], d["suggest"]) == ("idea-to-mvp", 5, False)
