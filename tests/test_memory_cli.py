"""Tests for v0.2 step 5b: ``ai-cockpit memory {list,show,accept}`` and the
``_DefaultGroup`` shim that keeps the historical positional form working.

Hard-rule §3.2 guard: every test verifies that the only path which writes
to ``.ai-cockpit/memory/*.md`` is ``memory accept``. ``list`` / ``show`` /
``run`` (with suggestions on) must never modify any memory file.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from click.testing import CliRunner

from ai_cockpit.cli import main as cli_main
from ai_cockpit.memory.loader import memory_dir
from ai_cockpit.memory.suggestions import (
    Suggestion,
    applied_dir,
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


def _make_suggestion(
    project_root: Path,
    *,
    sid: str = "20260101T000000-done-test-idea",
    target: str = "project.md",
    content: str = "## entry\n\n- decision: done\n",
    rationale: str = "test fixture",
) -> Suggestion:
    s = Suggestion(
        id=sid,
        created_at="2026-01-01T00:00:00+00:00",
        target=target,
        operation="append",
        content=content,
        rationale=rationale,
    )
    write_suggestion(project_root, s)
    return s


def test_memory_list_empty(tmp_path: Path) -> None:
    """`memory list` on a fresh project prints the empty-state message."""

    result = CliRunner().invoke(cli_main, ["memory", "list", "--root", str(tmp_path)])

    assert result.exit_code == 0, result.output + (result.stderr or "")
    assert "no pending memory suggestions" in result.output


def test_memory_list_one_suggestion(tmp_path: Path) -> None:
    s = _make_suggestion(tmp_path, content="first line of body\n\nrest\n")

    result = CliRunner().invoke(cli_main, ["memory", "list", "--root", str(tmp_path)])

    assert result.exit_code == 0, result.output + (result.stderr or "")
    assert s.id in result.output
    assert "project.md" in result.output
    assert "append" in result.output
    assert "first line of body" in result.output


def test_memory_show_renders_full_content(tmp_path: Path) -> None:
    s = _make_suggestion(
        tmp_path,
        content="## 2026-01-01 — idea\n\n- decision: done\n",
        rationale="from-fixture",
    )

    result = CliRunner().invoke(
        cli_main, ["memory", "show", s.id, "--root", str(tmp_path)]
    )

    assert result.exit_code == 0, result.output + (result.stderr or "")
    assert f"id:         {s.id}" in result.output
    assert "target:     project.md" in result.output
    assert "operation:  append" in result.output
    assert "rationale:  from-fixture" in result.output
    assert "- decision: done" in result.output


def test_memory_show_unknown_exits_nonzero(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli_main, ["memory", "show", "nope-id", "--root", str(tmp_path)]
    )

    assert result.exit_code != 0
    assert "suggestion not found" in (result.output + (result.stderr or ""))


def test_memory_accept_applies_and_archives(tmp_path: Path) -> None:
    """`memory accept` is the ONE path that writes to memory/*.md."""

    s = _make_suggestion(tmp_path, content="## entry\n\n- new note\n")
    target_path = memory_dir(tmp_path) / "project.md"
    assert not target_path.exists(), (
        "pre-condition: no memory file before accept (hard-rule §3.2)"
    )

    result = CliRunner().invoke(
        cli_main, ["memory", "accept", s.id, "--root", str(tmp_path)]
    )

    assert result.exit_code == 0, result.output + (result.stderr or "")
    assert f"applied {s.id}" in result.output
    assert target_path.exists()
    assert "- new note" in target_path.read_text(encoding="utf-8")
    assert not (suggestions_dir(tmp_path) / f"{s.id}.json").exists()
    assert (applied_dir(tmp_path) / f"{s.id}.json").exists()


def test_memory_accept_unknown_exits_nonzero(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli_main, ["memory", "accept", "nope-id", "--root", str(tmp_path)]
    )

    assert result.exit_code != 0
    assert "suggestion not found" in (result.output + (result.stderr or ""))
    assert not (memory_dir(tmp_path) / "project.md").exists()


def test_memory_accept_full_lifecycle(tmp_path: Path) -> None:
    """End-to-end: list -> show -> accept -> list-empty -> file written."""

    s = _make_suggestion(tmp_path)

    listed = CliRunner().invoke(cli_main, ["memory", "list", "--root", str(tmp_path)])
    assert s.id in listed.output

    shown = CliRunner().invoke(
        cli_main, ["memory", "show", s.id, "--root", str(tmp_path)]
    )
    assert shown.exit_code == 0
    assert s.id in shown.output

    accepted = CliRunner().invoke(
        cli_main, ["memory", "accept", s.id, "--root", str(tmp_path)]
    )
    assert accepted.exit_code == 0

    relisted = CliRunner().invoke(
        cli_main, ["memory", "list", "--root", str(tmp_path)]
    )
    assert "no pending memory suggestions" in relisted.output

    target_path = memory_dir(tmp_path) / "project.md"
    assert target_path.exists()
    body = target_path.read_text(encoding="utf-8")
    assert "- decision: done" in body


def test_memory_list_shows_age_and_summary(tmp_path: Path) -> None:
    """A.2: list output gains an ``age:`` column per row plus a one-line
    aggregate ``total: N (done: A, ask_human: B)`` at the end, with
    rows sorted by ``created_at`` descending."""

    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    fixtures = [
        ("done", now - timedelta(days=2, hours=3), "oldest done idea"),
        ("ask_human", now - timedelta(hours=5), "middle ask_human idea"),
        ("done", now - timedelta(minutes=30), "newest done idea"),
    ]
    ids: list[str] = []
    for decision, when, slug in fixtures:
        sid = when.strftime("%Y%m%dT%H%M%S") + f"-{decision}-{slug.replace(' ', '-')}"
        ids.append(sid)
        s = Suggestion(
            id=sid,
            created_at=when.isoformat(timespec="seconds"),
            target="project.md",
            operation="append",
            content=f"## {slug}\n\n- decision: {decision}\n",
            rationale=f"auto-generated from run; decision={decision}",
        )
        write_suggestion(tmp_path, s)

    result = CliRunner().invoke(cli_main, ["memory", "list", "--root", str(tmp_path)])

    assert result.exit_code == 0, result.output + (result.stderr or "")
    out = result.output

    assert "total: 3 (done: 2, ask_human: 1)" in out

    for sid in ids:
        assert sid in out, f"missing {sid} in output:\n{out}"

    newest_pos = out.index(ids[2])
    middle_pos = out.index(ids[1])
    oldest_pos = out.index(ids[0])
    assert newest_pos < middle_pos < oldest_pos, (
        f"expected newest-first ordering; got positions "
        f"newest={newest_pos} middle={middle_pos} oldest={oldest_pos}\n{out}"
    )

    lines = [ln for ln in out.splitlines() if ln.startswith("age:")]
    assert len(lines) == 3, f"expected 3 row lines, got {len(lines)}:\n{out}"
    for ln in lines:
        assert "d " in ln and "h ago" in ln, f"bad age format in: {ln!r}"


def test_memory_list_skips_corrupt_json(tmp_path: Path) -> None:
    """A garbage JSON in the suggestions dir must not crash `memory list`."""

    base = suggestions_dir(tmp_path)
    base.mkdir(parents=True)
    (base / "broken.json").write_text("{not json", encoding="utf-8")
    _make_suggestion(tmp_path, sid="20260102T000000-done-good")

    result = CliRunner().invoke(cli_main, ["memory", "list", "--root", str(tmp_path)])

    assert result.exit_code == 0, result.output + (result.stderr or "")
    assert "20260102T000000-done-good" in result.output


def test_default_group_dispatches_positional_to_run(tmp_path: Path) -> None:
    """`ai-cockpit "idea" --flags` still routes to the `run` subcommand."""

    _init_git_repo(tmp_path)

    result = CliRunner().invoke(
        cli_main,
        ["--root", str(tmp_path), "--max-loops", "1", "--dry-run", "smoke idea"],
    )

    assert result.exit_code == 0, result.output + (result.stderr or "")
    assert "AI Cockpit — Run Summary" in result.output


def test_default_group_help_lists_subcommands() -> None:
    """`ai-cockpit --help` shows the group help with `run` and `memory`."""

    result = CliRunner().invoke(cli_main, ["--help"])

    assert result.exit_code == 0
    assert "run" in result.output
    assert "memory" in result.output


def test_run_subcommand_explicit_still_works(tmp_path: Path) -> None:
    """`ai-cockpit run "idea" --flags` is the explicit form of the default."""

    _init_git_repo(tmp_path)

    result = CliRunner().invoke(
        cli_main,
        [
            "run",
            "--root",
            str(tmp_path),
            "--max-loops",
            "1",
            "--dry-run",
            "smoke idea via run",
        ],
    )

    assert result.exit_code == 0, result.output + (result.stderr or "")
    assert "AI Cockpit — Run Summary" in result.output


def test_run_writes_suggestion_but_never_touches_memory(tmp_path: Path) -> None:
    """Hard-rule §3.2 re-asserted for the post-step-5b CLI shape:

    a default ``run`` invocation may write under ``.ai-cockpit/suggestions/``
    but MUST NOT create or modify anything under ``.ai-cockpit/memory/``.
    Only ``memory accept`` is allowed to do that.
    """

    _init_git_repo(tmp_path)

    result = CliRunner().invoke(
        cli_main,
        ["--root", str(tmp_path), "--max-loops", "1", "--dry-run", "an idea"],
    )

    assert result.exit_code == 0, result.output + (result.stderr or "")

    s_dir = suggestions_dir(tmp_path)
    assert s_dir.is_dir(), "run --suggest (default) should create suggestions dir"
    pending = list(s_dir.glob("*.json"))
    assert len(pending) == 1, f"expected one pending suggestion, got {pending}"
    blob = json.loads(pending[0].read_text(encoding="utf-8"))
    assert blob["target"] == "project.md"
    assert blob["operation"] == "append"

    mem = memory_dir(tmp_path)
    assert not mem.exists() or not any(mem.iterdir()), (
        "run must NEVER write to .ai-cockpit/memory/* (hard rule §3.2)"
    )
