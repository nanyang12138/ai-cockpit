"""Tests for v0.2 step 5a: memory auto-update suggestion library + hook.

Covers the library lifecycle (build/write/list/load/accept) plus the
post-run side-effect that writes a suggestion JSON without ever
auto-editing memory files (hard rule §3.2). The `ai-cockpit memory ...`
subcommands ship in step 5b; until then, suggestions are inspected and
applied programmatically.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from ai_cockpit.cli import main as cli_main
from ai_cockpit.memory.suggestions import (
    Suggestion,
    SuggestionError,
    accept_suggestion,
    applied_dir,
    build_suggestion_from_state,
    generate_and_write,
    list_suggestions,
    load_suggestion,
    suggestions_dir,
    write_suggestion,
)


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.test"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "tester"], cwd=path, check=True)
    (path / "README.md").write_text("hi")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)


def _state(**overrides):
    base = {
        "user_input": "ship a feature",
        "idea": "ship a feature",
        "mvp_spec": "Goal: ship feature\nNotes: tiny\n",
        "decision": "done",
    }
    base.update(overrides)
    return base


_FIXED_WHEN = datetime(2026, 5, 15, 8, 30, 0, tzinfo=UTC)


def test_build_suggestion_done_state_round_trip(tmp_path: Path) -> None:
    s = build_suggestion_from_state(_state(), when=_FIXED_WHEN)
    assert s is not None
    assert s.id == "20260515T083000-done-ship-a-feature"
    assert s.target == "project.md"
    assert s.operation == "append"
    assert "decision: done" in s.content
    assert "Goal: ship feature" in s.content
    assert s.created_at.startswith("2026-05-15T08:30:00")

    write_suggestion(tmp_path, s)
    listed = list_suggestions(tmp_path)
    assert [item.id for item in listed] == [s.id]
    assert load_suggestion(tmp_path, s.id) == s


@pytest.mark.parametrize(
    "overrides",
    [
        {"decision": "retry"},
        {"decision": "stop"},
        {"mvp_spec": ""},
        {"idea": "", "user_input": ""},
    ],
)
def test_build_suggestion_skips_uninteresting_runs(overrides: dict) -> None:
    assert build_suggestion_from_state(_state(**overrides)) is None


def test_build_suggestion_keeps_ask_human_with_real_diff() -> None:
    """ask_human runs that produced a real diff are informative and kept.

    Example from real-LLM validation 2026-05-15: aider made edits but
    the reviewer rejected unverified lint/test criteria — the diff is
    worth remembering in project.md.
    """

    s = build_suggestion_from_state(
        _state(
            decision="ask_human",
            verification_result={
                "passed": True,
                "commands": [],
                "git_diff": "diff --git a/README.md b/README.md\n+ Requires Python 3.12+\n",
                "git_status": " M README.md",
            },
        )
    )
    assert s is not None and "decision: ask_human" in s.content


def test_build_suggestion_skips_ask_human_with_empty_diff() -> None:
    """ask_human + empty diff is pure noise: coder did nothing.

    This is the case where the stub worker (or a worker that failed
    to authenticate) didn't touch the working tree, so the reviewer
    correctly returned passed=False. Recording such runs in
    project.md only adds noise to ``ai-cockpit memory list``.
    """

    cases: list[dict[str, Any]] = [
        {"decision": "ask_human"},  # no verification_result at all
        {
            "decision": "ask_human",
            "verification_result": {
                "passed": False,
                "commands": [],
                "git_diff": "",
                "git_status": "",
            },
        },
        {
            "decision": "ask_human",
            "verification_result": {
                "passed": False,
                "commands": [],
                "git_diff": "   \n  ",
                "git_status": "",
            },
        },
    ]
    for overrides in cases:
        assert build_suggestion_from_state(_state(**overrides)) is None


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"target": "user.md.bak"}, "not in allowed"),
        ({"operation": "overwrite"}, "not supported"),
        ({"id": "../escape"}, "invalid suggestion id"),
        ({"content": "  "}, "content is empty"),
    ],
)
def test_validate_rejects_bad_blobs(kwargs: dict, match: str) -> None:
    base = dict(
        id="x1", created_at="2026-05-15T08:30:00+00:00",
        target="project.md", operation="append", content="hi", rationale="r",
    )
    base.update(kwargs)
    with pytest.raises(SuggestionError, match=match):
        Suggestion(**base).validate()


def test_write_refuses_duplicate_and_load_missing(tmp_path: Path) -> None:
    s = build_suggestion_from_state(_state(), when=_FIXED_WHEN)
    assert s is not None
    write_suggestion(tmp_path, s)
    with pytest.raises(SuggestionError, match="already exists"):
        write_suggestion(tmp_path, s)
    with pytest.raises(SuggestionError, match="not found"):
        load_suggestion(tmp_path, "20260101T000000-missing")


def test_list_skips_unparseable_files(tmp_path: Path) -> None:
    base = suggestions_dir(tmp_path)
    base.mkdir(parents=True)
    (base / "garbage.json").write_text("not json")
    (base / "bad-shape.json").write_text(json.dumps({"id": "x"}))
    assert list_suggestions(tmp_path) == []


def test_accept_appends_after_existing_and_archives(tmp_path: Path) -> None:
    mem = tmp_path / ".ai-cockpit" / "memory" / "project.md"
    mem.parent.mkdir(parents=True)
    mem.write_text("# Project memory\n\nExisting line.\n")

    s = build_suggestion_from_state(_state(), when=_FIXED_WHEN)
    assert s is not None
    write_suggestion(tmp_path, s)
    target = accept_suggestion(tmp_path, s.id)

    text = target.read_text()
    assert text.startswith("# Project memory\n")
    assert "Existing line." in text
    assert text.count("decision: done") == 1
    assert not (suggestions_dir(tmp_path) / f"{s.id}.json").exists()
    assert (applied_dir(tmp_path) / f"{s.id}.json").is_file()


def test_accept_unknown_id_raises(tmp_path: Path) -> None:
    with pytest.raises(SuggestionError):
        accept_suggestion(tmp_path, "nope")


def test_generate_and_write_skips_when_no_suggestion(tmp_path: Path) -> None:
    assert generate_and_write(tmp_path, _state(decision="retry")) is None
    assert not suggestions_dir(tmp_path).is_dir()


def test_run_default_writes_suggestion_and_does_not_touch_memory(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)
    result = CliRunner().invoke(
        cli_main,
        ["--root", str(tmp_path), "--max-loops", "1", "--dry-run",
         "--no-checkpoint", "smoke run for suggestion"],
    )
    assert result.exit_code == 0, result.output + (result.stderr or "")
    assert "memory suggestion written:" in (result.stderr or "")
    pending = list_suggestions(tmp_path)
    assert len(pending) == 1 and pending[0].target == "project.md"
    mem = tmp_path / ".ai-cockpit" / "memory" / "project.md"
    assert not mem.exists(), "running must NEVER auto-edit memory files"


def test_run_with_no_suggest_does_not_write(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    result = CliRunner().invoke(
        cli_main,
        ["--root", str(tmp_path), "--max-loops", "1", "--dry-run",
         "--no-checkpoint", "--no-suggest", "another smoke"],
    )
    assert result.exit_code == 0, result.output + (result.stderr or "")
    assert "memory suggestion written:" not in (result.stderr or "")
    assert list_suggestions(tmp_path) == []
