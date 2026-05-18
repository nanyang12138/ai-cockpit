"""Integration tests for v0.5 row #11 sub-gate a-2 — ``ai-cockpit chat``.

Sub-gate a-1 (PR #110) shipped the spawn helper + unit tests; this
file covers the CLI subcommand wiring on top of it: `--backend
builtin` rejected with a typed message, cursor-missing UsageError,
`--no-track-cost` info line, exit-code propagation, dirty-paths-on-
exit reporting.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from click.testing import CliRunner

from ai_cockpit import cli as cli_module
from ai_cockpit.cli import main
from ai_cockpit.cursor_adapter import chat as chat_module


def _fake_chat_result(
    *,
    exit_code: int = 0,
    cursor_binary: str | None = "/tmp/fake-cursor",
    system_prompt_bytes: int = 0,
    truncated_files: tuple[str, ...] = (),
    dirty_paths_on_exit: tuple[str, ...] = (),
) -> chat_module.ChatSpawnResult:
    return chat_module.ChatSpawnResult(
        exit_code=exit_code,
        cursor_binary=cursor_binary,
        system_prompt_bytes=system_prompt_bytes,
        truncated_files=truncated_files,
        dirty_paths_on_exit=dirty_paths_on_exit,
    )


def test_backend_builtin_errors_clearly(tmp_path: Path) -> None:
    """``--backend builtin`` is sub-gate b; sub-gate a rejects it
    with a typed UsageError pointing at the open-gate signal."""
    result = CliRunner().invoke(
        main, ["chat", "--root", str(tmp_path), "--backend", "builtin"]
    )
    assert result.exit_code != 0
    assert "sub-gate b" in result.output
    assert "builtin" in result.output
    assert "open-gate v0.5-row-11-impl-b" in result.output


def test_chat_no_cursor_binary_errors(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """No cursor on PATH → typed UsageError naming the candidate binaries
    and pointing the operator at --binary / sub-gate b."""
    import shutil as _sh
    monkeypatch.setattr(_sh, "which", lambda _name: None)
    result = CliRunner().invoke(main, ["chat", "--root", str(tmp_path)])
    assert result.exit_code != 0
    assert "no Cursor binary" in result.output
    assert "--binary" in result.output


def test_chat_no_track_cost_emits_info_line(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """``--no-track-cost`` is a forward-compat no-op in sub-gate a; the
    info line must surface so the operator knows it's currently inert."""
    monkeypatch.setattr(cli_module, "spawn_cursor_chat", lambda *a, **k: _fake_chat_result())
    result = CliRunner().invoke(
        main, ["chat", "--root", str(tmp_path), "--no-track-cost"]
    )
    assert result.exit_code == 0, result.output
    assert "--no-track-cost noted" in result.stderr


def test_chat_propagates_cursor_exit_code(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Q5: cursor's exit code becomes ai-cockpit's exit code."""
    monkeypatch.setattr(
        cli_module, "spawn_cursor_chat",
        lambda *a, **k: _fake_chat_result(exit_code=42),
    )
    result = CliRunner().invoke(main, ["chat", "--root", str(tmp_path)])
    assert result.exit_code == 42


def test_chat_reports_dirty_paths_on_exit(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Q1 layer 2: if cursor wrote files, the CLI must surface them
    with revert hints."""
    monkeypatch.setattr(
        cli_module, "spawn_cursor_chat",
        lambda *a, **k: _fake_chat_result(
            system_prompt_bytes=100, dirty_paths_on_exit=("src/foo.py", "README.md"),
        ),
    )
    result = CliRunner().invoke(main, ["chat", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "working tree gained" in result.stderr
    assert "src/foo.py" in result.stderr
    assert "git checkout -- src/foo.py" in result.stderr
    assert "README.md" in result.stderr


def test_chat_emits_memory_injection_info_line(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """When memory injection produced bytes, the CLI prints an info line
    so the operator knows context was loaded."""
    monkeypatch.setattr(
        cli_module, "spawn_cursor_chat",
        lambda *a, **k: _fake_chat_result(system_prompt_bytes=2048),
    )
    result = CliRunner().invoke(main, ["chat", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "injected 2048 bytes" in result.stderr


def test_chat_warns_on_truncation(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Q4: when memory exceeds 64 KB and files are truncated, the CLI
    surfaces a warning naming them."""
    monkeypatch.setattr(
        cli_module, "spawn_cursor_chat",
        lambda *a, **k: _fake_chat_result(
            system_prompt_bytes=64_000,
            truncated_files=(".ai-cockpit/memory/big.md",),
        ),
    )
    result = CliRunner().invoke(main, ["chat", "--root", str(tmp_path)])
    assert result.exit_code == 0
    assert "memory budget" in result.stderr
    assert "big.md" in result.stderr


def test_chat_passes_question_to_spawn(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Q3 one-shot: positional QUESTION arg reaches spawn_cursor_chat
    as the ``question`` kwarg."""
    captured: dict[str, Any] = {}

    def fake_spawn(project_root, *, question=None, binary_override=None, **kwargs):
        captured["root"] = project_root
        captured["question"] = question
        captured["binary"] = binary_override
        return _fake_chat_result()

    monkeypatch.setattr(cli_module, "spawn_cursor_chat", fake_spawn)
    result = CliRunner().invoke(
        main,
        ["chat", "--root", str(tmp_path), "what", "does", "cli.py", "do?"],
    )
    assert result.exit_code == 0, result.output
    assert captured["question"] == "what does cli.py do?"


def test_chat_passes_binary_override_to_spawn(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """--binary forwards to spawn's binary_override kwarg."""
    captured: dict[str, Any] = {}

    def fake_spawn(project_root, *, question=None, binary_override=None, **kwargs):
        captured["binary"] = binary_override
        return _fake_chat_result()

    monkeypatch.setattr(cli_module, "spawn_cursor_chat", fake_spawn)
    result = CliRunner().invoke(
        main,
        ["chat", "--root", str(tmp_path), "--binary", "/opt/my-cursor"],
    )
    assert result.exit_code == 0, result.output
    assert captured["binary"] == "/opt/my-cursor"


def test_chat_help_lists_backend_and_binary(tmp_path: Path) -> None:
    """Surface contract: --help mentions --backend cursor|builtin and
    --binary."""
    result = CliRunner().invoke(main, ["chat", "--help"])
    assert result.exit_code == 0
    assert "--backend" in result.output
    assert "cursor" in result.output
    assert "builtin" in result.output
    assert "--binary" in result.output
    assert "read-only" in result.output.lower() or "Read-only" in result.output
