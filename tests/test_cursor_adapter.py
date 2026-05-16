"""B.10a — Cursor adapter discovery + ``ai-cockpit cursor status`` tests.

Per the B.10 contract §9 these tests MUST use fake binaries on PATH
(or an injected runner) and MUST NEVER invoke the real Cursor CLI.
"""

from __future__ import annotations

import os
import stat
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from click.testing import CliRunner

from ai_cockpit.cli import _render_cursor_status
from ai_cockpit.cli import main as cli_main
from ai_cockpit.cursor_adapter import (
    CursorAdapterStatus,
    probe_cursor_adapter,
)

_RunnerT = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]
_HELP_FULL = (
    "Options:\n"
    "  --mode plan|ask|agent   Select mode\n"
    "  --print                 Non-interactive print\n"
    "  --output-format=json    Emit JSON envelope\n"
    "  --yolo                  Skip trust prompt (dangerous)\n"
    "  --resume <session-id>   Continue a previous session\n"
)


def _fake_runner(table: dict[tuple[str, ...], tuple[int, str, str]]) -> _RunnerT:
    def runner(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
        rc, out, err = table.get(tuple(args[1:]), (2, "", "unknown probe"))
        return subprocess.CompletedProcess(
            args=list(args), returncode=rc, stdout=out, stderr=err
        )
    return runner


def _make_fake_binary(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


@pytest.fixture
def empty_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("PATH", str(tmp_path))
    return tmp_path


def test_no_binary_reports_unavailable(empty_path: Path) -> None:
    status = probe_cursor_adapter(runner=_fake_runner({}))
    assert isinstance(status, CursorAdapterStatus)
    assert status.available is False
    assert status.binary_path is None and status.binary_name is None
    assert any("not found on PATH" in e for e in status.errors)
    assert status.version is None and status.supported_modes == ()
    assert status.json_print_advertised is None


def test_prefers_agent_over_cursor_agent(empty_path: Path) -> None:
    _make_fake_binary(empty_path, "agent")
    _make_fake_binary(empty_path, "cursor-agent")
    status = probe_cursor_adapter(
        runner=_fake_runner({
            ("--version",): (0, "agent 1.2.3\n", ""),
            ("--help",): (0, "Options:\n  --mode plan|ask\n", ""),
        })
    )
    assert status.available is True and status.binary_name == "agent"
    assert status.binary_path is not None and status.binary_path.endswith("/agent")
    assert status.version == "1.2.3"
    assert set(status.supported_modes) == {"plan", "ask"}


def test_binary_override_path_and_missing(empty_path: Path) -> None:
    _make_fake_binary(empty_path, "weirdcli")
    ok = probe_cursor_adapter(
        binary_override="weirdcli",
        runner=_fake_runner({("--version",): (0, "weirdcli v0.9\n", ""),
                             ("--help",): (0, "", "")}),
    )
    assert ok.binary_name == "weirdcli" and ok.version == "0.9"
    miss = probe_cursor_adapter(
        binary_override="definitely-not-installed", runner=_fake_runner({})
    )
    assert miss.available is False
    assert any("definitely-not-installed" in e for e in miss.errors)


def test_short_v_fallback_and_timeout(empty_path: Path) -> None:
    _make_fake_binary(empty_path, "agent")
    status = probe_cursor_adapter(runner=_fake_runner({
        ("--version",): (2, "", ""), ("-v",): (0, "v2.0.0-beta\n", ""),
        ("--help",): (0, "Usage: agent\n", ""),
    }))
    assert status.version == "2.0.0-beta"

    def boom(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd=list(args), timeout=1.0)

    timed = probe_cursor_adapter(runner=boom)
    assert timed.available is True and timed.version is None
    assert any("timed out" in e for e in timed.errors)


@pytest.mark.parametrize(
    ("help_text", "expected", "modes_subset"),
    [(_HELP_FULL, True, {"plan", "ask"}),
     ("Usage: agent (nothing else)\n", False, set())],
)
def test_flag_advertisements_tri_state(
    empty_path: Path, help_text: str, expected: bool, modes_subset: set[str],
) -> None:
    _make_fake_binary(empty_path, "agent")
    status = probe_cursor_adapter(runner=_fake_runner({
        ("--version",): (0, "agent 0.1\n", ""), ("--help",): (0, help_text, ""),
    }))
    assert status.json_print_advertised is expected
    assert status.trust_flag_advertised is expected
    assert status.resume_flag_advertised is expected
    assert modes_subset.issubset(set(status.supported_modes))


def test_render_and_cli_unavailable(empty_path: Path) -> None:
    rendered = "\n".join(_render_cursor_status(CursorAdapterStatus(
        binary_name="agent", binary_path="/usr/local/bin/agent", available=True,
        version=None, supported_modes=(), json_print_advertised=None,
        trust_flag_advertised=False, resume_flag_advertised=True,
    )))
    for needle in (
        "binary_name: agent", "available: yes", "version: unknown",
        "supported_modes: -", "json_print_advertised: unknown",
        "trust_flag_advertised: no", "resume_flag_advertised: yes",
    ):
        assert needle in rendered
    result = CliRunner().invoke(cli_main, ["cursor", "status"])
    assert result.exit_code == 0, result.output
    assert "available: no" in result.output and "hint:" in result.output


def test_cli_cursor_status_with_fake_binary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = tmp_path / "agent"
    fake.write_text(
        "#!/bin/sh\ncase \"$1\" in\n"
        "  --version) echo 'agent 9.9.9' ;;\n"
        "  --help) printf 'Options:\\n  --mode plan|ask\\n  --print --output-format\\n"
        "  --yolo\\n  --resume <id>\\n' ;;\nesac\n",
        encoding="utf-8",
    )
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))
    result = CliRunner().invoke(cli_main, ["cursor", "status"])
    assert result.exit_code == 0, result.output
    for needle in (
        "binary_name: agent", "available: yes", "version: 9.9.9",
        "json_print_advertised: yes", "trust_flag_advertised: yes",
        "resume_flag_advertised: yes",
    ):
        assert needle in result.output


def test_cli_cursor_group_help_lists_status() -> None:
    result = CliRunner().invoke(cli_main, ["cursor", "--help"])
    assert result.exit_code == 0 and "status" in result.output
