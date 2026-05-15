"""Tests for the read-only memory loader."""

from __future__ import annotations

from pathlib import Path

from ai_cockpit.memory.loader import load_memory


def test_load_memory_returns_empty_when_dir_missing(tmp_path: Path) -> None:
    assert load_memory(tmp_path) == ""


def test_load_memory_concatenates_present_files(tmp_path: Path) -> None:
    mem = tmp_path / ".ai-cockpit" / "memory"
    mem.mkdir(parents=True)
    (mem / "user.md").write_text("user content\n")
    (mem / "preferences.md").write_text("prefer small diffs\n")

    result = load_memory(tmp_path)

    assert "## user.md" in result
    assert "user content" in result
    assert "## preferences.md" in result
    assert "prefer small diffs" in result
    assert "project.md" not in result


def test_load_memory_skips_empty_files(tmp_path: Path) -> None:
    mem = tmp_path / ".ai-cockpit" / "memory"
    mem.mkdir(parents=True)
    (mem / "user.md").write_text("   \n\n")
    (mem / "project.md").write_text("hello")

    result = load_memory(tmp_path)
    assert "user.md" not in result
    assert "## project.md" in result
    assert "hello" in result
