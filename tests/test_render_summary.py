"""v0.5 summary-rendering tests (tier 1+2: colored / structured text).

Cover: plain (v0.1-compatible) shape, text shape with section dividers
and status tokens, ``is_color_enabled`` gating against TTY / NO_COLOR,
and the ``print_summary`` dispatcher's text vs plain branches. Also
pin the hard invariant that ``final_summary`` retains the literal
``"AI Cockpit — Run Summary"`` substring in both rendering paths —
existing 343-baseline checkpoint replay + grep workflows depend on it.

Future tier 3 (``json``, ``quiet``, "Next Steps" hints) ships in the
follow-up PR.
"""

from __future__ import annotations

import io
import os
from typing import Any
from unittest.mock import patch

import click

from ai_cockpit.nodes.summary import summary_node
from ai_cockpit.render import (
    is_color_enabled,
    print_summary,
    render_summary_plain,
    render_summary_text,
)
from ai_cockpit.state import TaskState


def _sample_state(**overrides: Any) -> TaskState:
    base: TaskState = {
        "mode": "exploration",
        "loop_count": 1,
        "max_loops": 1,
        "decision": "done",
        "idea": "Build a tool that turns vague ideas into MVP specs.",
        "mvp_spec": "Minimum viable product: ...",
        "acceptance_criteria": ["criterion 1", "criterion 2"],
        "implementation_slice": "First slice: scaffold the CLI.",
        "coder_result": "Stub worker: preview only.",
        "verification_result": {
            "passed": True,
            "commands": [
                {"command": "pytest -q", "exit_code": 0, "stdout": "", "stderr": ""},
                {"command": "ruff check .", "exit_code": 0, "stdout": "", "stderr": ""},
            ],
            "git_diff": "",
            "git_status": "",
        },
        "review_result": {
            "passed": True,
            "issues": [],
            "risk_level": "low",
            "suggested_fix": "",
            "notes": "Looks good.",
        },
    }
    base.update(overrides)  # type: ignore[typeddict-item]
    return base


# ---------------------------------------------------------------------------
# Plain renderer: v0.1 compatibility (substring contract)
# ---------------------------------------------------------------------------


def test_plain_renderer_contains_v01_header() -> None:
    out = render_summary_plain(_sample_state())
    assert "AI Cockpit — Run Summary" in out
    assert "Mode:        exploration" in out
    assert "Decision:    done" in out


def test_plain_renderer_renders_commands_with_ok_marker() -> None:
    out = render_summary_plain(_sample_state())
    assert "- [ok] pytest -q" in out
    assert "- [ok] ruff check ." in out


def test_plain_renderer_renders_failing_command_with_exit_code() -> None:
    state = _sample_state()
    state["verification_result"] = {
        "passed": False,
        "commands": [
            {"command": "pytest -q", "exit_code": 7, "stdout": "", "stderr": ""},
        ],
        "git_diff": "",
        "git_status": "",
    }
    out = render_summary_plain(state)
    assert "- [FAIL (7)] pytest -q" in out


def test_plain_renderer_clean_tree_shows_marker() -> None:
    out = render_summary_plain(_sample_state())
    assert "(clean working tree)" in out


def test_plain_renderer_empty_commands_shows_marker() -> None:
    state = _sample_state()
    state["verification_result"] = {
        "passed": True, "commands": [], "git_diff": "", "git_status": "",
    }
    out = render_summary_plain(state)
    assert "(no verification commands ran)" in out


# ---------------------------------------------------------------------------
# Text renderer: colored / structured layout
# ---------------------------------------------------------------------------


def test_text_renderer_uncolored_contains_section_titles() -> None:
    out = render_summary_text(_sample_state(), color=False)
    assert "AI Cockpit — Run Summary" in out
    for section in ("Idea", "Plan", "Execution", "Review"):
        assert section in out, f"section {section!r} missing"


def test_text_renderer_uncolored_has_no_ansi_escapes() -> None:
    out = render_summary_text(_sample_state(), color=False)
    assert "\x1b[" not in out


def test_text_renderer_colored_emits_ansi_escapes() -> None:
    out = render_summary_text(_sample_state(), color=True)
    assert "\x1b[" in out
    # The decision token "[DONE]" must still appear as a literal substring
    # so external pipelines that grep on it keep working.
    assert "[DONE]" in out


def test_text_renderer_decision_token_renders_for_each_status() -> None:
    for decision, token in (
        ("done", "[DONE]"),
        ("retry", "[RETRY]"),
        ("ask_human", "[ASK_HUMAN]"),
        ("stop", "[STOP]"),
    ):
        state = _sample_state(decision=decision)
        out = render_summary_text(state, color=False)
        assert token in out, f"decision={decision!r} did not render expected token"


def test_text_renderer_failing_verification_shows_fail_token() -> None:
    state = _sample_state()
    state["verification_result"] = {
        "passed": False,
        "commands": [
            {"command": "pytest -q", "exit_code": 1, "stdout": "", "stderr": ""},
        ],
        "git_diff": "", "git_status": " M src/foo.py",
    }
    state["review_result"] = {
        "passed": False, "issues": ["something is off"],
        "risk_level": "high", "suggested_fix": "", "notes": "",
    }
    out = render_summary_text(state, color=False)
    assert "FAIL" in out
    assert "pytest -q" in out
    assert "src/foo.py" in out
    assert "high" in out


# ---------------------------------------------------------------------------
# Color gating
# ---------------------------------------------------------------------------


def test_is_color_enabled_off_on_non_tty() -> None:
    stream = io.StringIO()
    assert is_color_enabled(stream=stream) is False


def test_is_color_enabled_honors_no_color_env() -> None:
    class _FakeTTY:
        def isatty(self) -> bool:
            return True

    with patch.dict(os.environ, {"NO_COLOR": "1"}):
        assert is_color_enabled(stream=_FakeTTY()) is False


def test_is_color_enabled_on_tty_without_no_color() -> None:
    class _FakeTTY:
        def isatty(self) -> bool:
            return True

    env = {k: v for k, v in os.environ.items() if k != "NO_COLOR"}
    with patch.dict(os.environ, env, clear=True):
        assert is_color_enabled(stream=_FakeTTY()) is True


# ---------------------------------------------------------------------------
# print_summary dispatcher: stdout shape per format + final_summary invariant
# ---------------------------------------------------------------------------


def _capture_stdout(fn: Any, *args: Any, **kwargs: Any) -> str:
    captured: list[str] = []

    def _fake_echo(message: Any = "", **_kw: Any) -> None:
        captured.append(str(message))

    with patch.object(click, "echo", _fake_echo):
        fn(*args, **kwargs)
    return "\n".join(captured)


def test_print_summary_default_uses_text_format() -> None:
    state = _sample_state()
    out = _capture_stdout(print_summary, state)
    assert "AI Cockpit — Run Summary" in out
    assert "Idea" in out


def test_print_summary_plain_format_matches_v01_shape() -> None:
    state = _sample_state()
    state["output_format"] = "plain"
    out = _capture_stdout(print_summary, state)
    assert "Mode:        exploration" in out
    assert "Decision:    done" in out


def test_print_summary_unknown_format_falls_back_to_text() -> None:
    state = _sample_state()
    state["output_format"] = "no-such-format"
    out = _capture_stdout(print_summary, state)
    assert "AI Cockpit — Run Summary" in out
    assert "Idea" in out


def test_print_summary_always_returns_plain_text_for_final_summary() -> None:
    """Regardless of output_format, the return value contains the v0.1
    header so ``final_summary`` retains the literal substring that the
    343-baseline tests + checkpoint replay + grep workflows rely on."""
    for fmt in ("text", "plain"):
        state = _sample_state()
        state["output_format"] = fmt
        with patch.object(click, "echo", lambda *_a, **_kw: None):
            returned = print_summary(state)
        assert "AI Cockpit — Run Summary" in returned, (
            f"final_summary lost the v0.1 header in format={fmt!r}"
        )


def test_summary_node_writes_final_summary_in_text_mode() -> None:
    state = _sample_state()
    with patch.object(click, "echo", lambda *_a, **_kw: None):
        update = summary_node(state)
    assert "final_summary" in update
    assert "AI Cockpit — Run Summary" in update["final_summary"]
