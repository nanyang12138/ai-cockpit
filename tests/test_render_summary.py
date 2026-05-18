"""v0.5 summary-rendering tests.

Tier 1+2 (sub-gate a, PR #113): plain (v0.1-compatible) shape, text
shape with section dividers and status tokens, ``is_color_enabled``
gating against TTY / NO_COLOR, and the ``print_summary`` dispatcher's
text vs plain branches.

Tier 3 (sub-gate b, this file's later sections): JSON / quiet output
formats and the "Next Steps" actionable-hint section in text mode.

The hard invariant pinned across both tiers: ``final_summary`` retains
the literal ``"AI Cockpit — Run Summary"`` substring in every
rendering path — existing checkpoint replay + grep workflows depend
on it.
"""

from __future__ import annotations

import io
import json
import os
from typing import Any
from unittest.mock import patch

import click

from ai_cockpit.nodes.summary import summary_node
from ai_cockpit.render import (
    is_color_enabled,
    print_summary,
    render_summary_json,
    render_summary_plain,
    render_summary_quiet,
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


# ---------------------------------------------------------------------------
# Tier 3 — JSON renderer
# ---------------------------------------------------------------------------


def test_json_renderer_is_valid_json_and_contains_decision() -> None:
    payload = json.loads(render_summary_json(_sample_state()))
    assert payload["decision"] == "done"
    assert payload["mode"] == "exploration"
    assert payload["verification"]["passed"] is True
    assert payload["review"]["passed"] is True
    assert payload["acceptance_criteria"] == ["criterion 1", "criterion 2"]


def test_json_renderer_includes_metrics_when_present() -> None:
    state = _sample_state()
    state["metrics"] = {"tokens_sent": 1234.0, "cost_session_usd": 0.07}
    payload = json.loads(render_summary_json(state))
    assert payload["metrics"]["tokens_sent"] == 1234.0
    assert payload["metrics"]["cost_session_usd"] == 0.07


def test_json_renderer_no_ansi_escapes_anywhere() -> None:
    out = render_summary_json(_sample_state())
    assert "\x1b[" not in out


def test_json_renderer_renders_verification_commands_with_exit_codes() -> None:
    state = _sample_state()
    state["verification_result"] = {
        "passed": False,
        "commands": [
            {"command": "pytest -q", "exit_code": 1, "stdout": "", "stderr": ""},
            {"command": "ruff check .", "exit_code": 0, "stdout": "", "stderr": ""},
        ],
        "git_diff": "", "git_status": "",
    }
    payload = json.loads(render_summary_json(state))
    assert payload["verification"]["passed"] is False
    cmds = payload["verification"]["commands"]
    assert len(cmds) == 2
    assert cmds[0] == {"command": "pytest -q", "exit_code": 1}
    assert cmds[1] == {"command": "ruff check .", "exit_code": 0}


# ---------------------------------------------------------------------------
# Tier 3 — Quiet renderer
# ---------------------------------------------------------------------------


def test_quiet_renderer_is_single_line_with_decision_token() -> None:
    out = render_summary_quiet(_sample_state(), color=False).rstrip("\n")
    assert "\n" not in out
    assert "[DONE]" in out
    assert "verification=pass" in out
    assert "review=pass" in out
    assert "risk=low" in out


def test_quiet_renderer_fail_state_renders_compactly() -> None:
    state = _sample_state(decision="ask_human")
    state["verification_result"] = {
        "passed": False, "commands": [], "git_diff": "", "git_status": "",
    }
    state["review_result"] = {
        "passed": False, "issues": [], "risk_level": "high",
        "suggested_fix": "", "notes": "",
    }
    out = render_summary_quiet(state, color=False)
    assert "[ASK_HUMAN]" in out
    assert "verification=fail" in out
    assert "review=fail" in out
    assert "risk=high" in out


# ---------------------------------------------------------------------------
# Tier 3 — "Next Steps" actionable hints in text renderer
# ---------------------------------------------------------------------------


def test_next_steps_section_appears_on_ask_human() -> None:
    state = _sample_state(decision="ask_human")
    state["verification_result"] = {
        "passed": False,
        "commands": [
            {"command": "pytest -q", "exit_code": 1, "stdout": "", "stderr": ""},
        ],
        "git_diff": "", "git_status": "",
    }
    state["review_result"] = {
        "passed": False, "issues": ["something is off"],
        "risk_level": "high", "suggested_fix": "", "notes": "",
    }
    out = render_summary_text(state, color=False)
    assert "Next Steps" in out
    assert "ai-cockpit memory list" in out
    assert "ai-cockpit run" in out
    # Diagnostic hint about the failing command appears as a comment.
    assert "verification failed on" in out


def test_next_steps_section_appears_on_done_with_memory_hint() -> None:
    out = render_summary_text(_sample_state(), color=False)
    assert "Next Steps" in out
    assert "ai-cockpit memory list" in out
    assert "git status --short" in out


def test_next_steps_section_appears_on_retry_with_max_loops_hint() -> None:
    out = render_summary_text(_sample_state(decision="retry"), color=False)
    assert "Next Steps" in out
    assert "--max-loops" in out


# ---------------------------------------------------------------------------
# Tier 3 — print_summary dispatcher for json + quiet
# ---------------------------------------------------------------------------


def test_print_summary_json_format_emits_parseable_json() -> None:
    state = _sample_state()
    state["output_format"] = "json"
    out = _capture_stdout(print_summary, state)
    payload = json.loads(out)
    assert payload["decision"] == "done"
    assert payload["verification"]["passed"] is True


def test_print_summary_quiet_format_is_one_line() -> None:
    state = _sample_state()
    state["output_format"] = "quiet"
    out = _capture_stdout(print_summary, state).rstrip("\n")
    assert "\n" not in out
    assert "[DONE]" in out
    assert "verification=pass" in out


def test_print_summary_final_summary_invariant_holds_for_all_formats() -> None:
    """Tier 3 expands the format set; the v0.1 substring invariant still
    must hold on the returned ``final_summary`` text for every format."""
    for fmt in ("text", "plain", "json", "quiet"):
        state = _sample_state()
        state["output_format"] = fmt
        with patch.object(click, "echo", lambda *_a, **_kw: None):
            returned = print_summary(state)
        assert "AI Cockpit — Run Summary" in returned, (
            f"final_summary lost the v0.1 header in format={fmt!r}"
        )
