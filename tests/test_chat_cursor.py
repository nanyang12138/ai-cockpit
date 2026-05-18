"""Unit tests for v0.5 row #11 sub-gate a-1 — chat-mode helpers.

Sub-gate a-1 covers ``src/ai_cockpit/cursor_adapter/chat.py`` only —
``compose_system_prompt``, ``build_cursor_args``, ``spawn_cursor_chat``.
CLI integration tests (``ai-cockpit chat`` subcommand wiring) live in
sub-gate a-2 (separate PR) which actually adds the click command.

Covers contract §8 sub-gate a DoD bullets that pertain to the spawn
helper (memory injection composition, argv composition, dirty-tree
fallback detection, cursor-binary-missing graceful path).
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ai_cockpit.cursor_adapter.chat import (
    MEMORY_BUDGET_BYTES,
    build_cursor_args,
    compose_system_prompt,
    spawn_cursor_chat,
)


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.test"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "tester"], cwd=path, check=True)
    (path / "README.md").write_text("hi\n")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)


# ---------------------------------------------------------------------------
# compose_system_prompt
# ---------------------------------------------------------------------------


def test_compose_empty_when_no_memory_dir(tmp_path: Path) -> None:
    prompt, truncated = compose_system_prompt(tmp_path)
    assert prompt == ""
    assert truncated == ()


def test_compose_empty_when_no_md_files(tmp_path: Path) -> None:
    (tmp_path / ".ai-cockpit" / "memory").mkdir(parents=True)
    prompt, truncated = compose_system_prompt(tmp_path)
    assert prompt == ""
    assert truncated == ()


def test_compose_includes_per_file_headers(tmp_path: Path) -> None:
    mem = tmp_path / ".ai-cockpit" / "memory"
    mem.mkdir(parents=True)
    (mem / "project.md").write_text("Always run pytest -q.\n")
    (mem / "conventions.md").write_text("PRs <=8 files.\n")
    prompt, truncated = compose_system_prompt(tmp_path)
    assert "## .ai-cockpit/memory/conventions.md" in prompt
    assert "## .ai-cockpit/memory/project.md" in prompt
    assert "Always run pytest -q." in prompt
    assert "PRs <=8 files." in prompt
    assert "[end of injected memory]" in prompt
    assert truncated == ()


def test_compose_truncates_alphabetically_when_over_budget(tmp_path: Path) -> None:
    mem = tmp_path / ".ai-cockpit" / "memory"
    mem.mkdir(parents=True)
    (mem / "aaa-first.md").write_text("a" * 100)
    (mem / "zzz-last.md").write_text("z" * 100)
    # Header (~190 bytes) + one file block (~140 bytes) + end marker fits
    # under 400; a second file block would exceed.
    prompt, truncated = compose_system_prompt(tmp_path, budget_bytes=400)
    assert "aaa-first.md" in prompt
    assert "zzz-last.md" not in prompt
    assert truncated == (".ai-cockpit/memory/zzz-last.md",)


# ---------------------------------------------------------------------------
# build_cursor_args (post 2026-05-18 07:59 UTC fix: build-agnostic; no
# --read-only / --system-prompt flags. See chat.py module docstring.)
# ---------------------------------------------------------------------------


def test_build_args_interactive_has_no_flags() -> None:
    """Interactive mode: argv is just ``[binary]`` — no flags at all,
    so any cursor build accepts it."""
    args = build_cursor_args("/usr/bin/cursor", None)
    assert args == ["/usr/bin/cursor"]


def test_build_args_one_shot_appends_question() -> None:
    args = build_cursor_args("/bin/cursor", "what does cli.py do?")
    assert args == ["/bin/cursor", "what does cli.py do?"]
    # No --read-only or --system-prompt anywhere.
    assert "--read-only" not in args
    assert "--system-prompt" not in args


# ---------------------------------------------------------------------------
# spawn_cursor_chat
# ---------------------------------------------------------------------------


def _fake_runner_factory(captured: list[Sequence[str]], exit_code: int = 0):
    def runner(args: Sequence[str], cwd: str) -> int:
        captured.append(tuple(args))
        return exit_code
    return runner


def test_spawn_returns_127_when_no_binary_discovered(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """``shutil.which`` fails for every candidate AND no override:
    ``cursor_found`` is False and exit code is 127."""
    import shutil as _sh
    monkeypatch.setattr(_sh, "which", lambda _name: None)
    result = spawn_cursor_chat(tmp_path)
    assert result.exit_code == 127
    assert result.cursor_binary is None
    assert not result.cursor_found


def test_spawn_interactive_writes_memory_to_temp_file(tmp_path: Path) -> None:
    """Interactive (no question): memory is written to
    .ai-cockpit/history/chat-context-<thread>.md; cursor is spawned
    with no flags."""
    mem = tmp_path / ".ai-cockpit" / "memory"
    mem.mkdir(parents=True)
    (mem / "project.md").write_text("Use pytest -q.\n")
    captured: list[Sequence[str]] = []
    result = spawn_cursor_chat(
        tmp_path,
        binary_override="/tmp/fake-cursor",
        runner=_fake_runner_factory(captured),
    )
    assert len(captured) == 1
    assert captured[0] == ("/tmp/fake-cursor",)  # NO flags, NO args
    assert result.memory_context_file is not None
    assert Path(result.memory_context_file).is_file()
    assert "Use pytest -q." in Path(result.memory_context_file).read_text()
    assert result.system_prompt_bytes > 0


def test_spawn_one_shot_prepends_memory_to_question(tmp_path: Path) -> None:
    """One-shot (question given): memory is prepended to the question;
    cursor receives one combined positional argument."""
    mem = tmp_path / ".ai-cockpit" / "memory"
    mem.mkdir(parents=True)
    (mem / "project.md").write_text("Use pytest -q.\n")
    captured: list[Sequence[str]] = []
    result = spawn_cursor_chat(
        tmp_path,
        question="what does foo do?",
        binary_override="/tmp/fake-cursor",
        runner=_fake_runner_factory(captured),
    )
    args = captured[0]
    assert args[0] == "/tmp/fake-cursor"
    assert len(args) == 2  # binary + combined question, no flags
    combined = args[1]
    assert "Use pytest -q." in combined
    assert "what does foo do?" in combined
    # memory should appear BEFORE the question in the combined text
    assert combined.index("Use pytest -q.") < combined.index("what does foo do?")
    # No temp file in one-shot mode (memory went directly to cursor argv).
    assert result.memory_context_file is None


def test_spawn_one_shot_without_memory_passes_question_verbatim(tmp_path: Path) -> None:
    """No .ai-cockpit/memory/* → question is passed unchanged."""
    captured: list[Sequence[str]] = []
    spawn_cursor_chat(
        tmp_path,
        question="bare question?",
        binary_override="/tmp/fake-cursor",
        runner=_fake_runner_factory(captured),
    )
    assert captured[0] == ("/tmp/fake-cursor", "bare question?")


def test_spawn_detects_dirty_after_chat(tmp_path: Path) -> None:
    """Defense-in-depth Q1 layer 2: spawn detects new dirty paths."""
    _init_git_repo(tmp_path)

    def dirty_runner(args: Sequence[str], cwd: str) -> int:
        (Path(cwd) / "sneaky_edit.py").write_text("cursor wrote this\n")
        return 0

    result = spawn_cursor_chat(
        tmp_path, binary_override="/tmp/fake-cursor", runner=dirty_runner
    )
    assert "sneaky_edit.py" in result.dirty_paths_on_exit


def test_spawn_propagates_runner_exit_code(tmp_path: Path) -> None:
    """Q5: cursor's exit code becomes ``ChatSpawnResult.exit_code``."""
    captured: list[Sequence[str]] = []
    result = spawn_cursor_chat(
        tmp_path,
        binary_override="/tmp/fake-cursor",
        runner=_fake_runner_factory(captured, exit_code=42),
    )
    assert result.exit_code == 42


def test_memory_budget_constant_is_64kb() -> None:
    """Q4 lock: 64 KB cap on injected memory."""
    assert MEMORY_BUDGET_BYTES == 64 * 1024
