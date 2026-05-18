"""Summary rendering for the CLI run loop (v0.5 tier 1+2).

Two output modes:

- ``text`` (default): structured layout with optional ANSI coloring
  on a TTY (honors ``NO_COLOR``). Decision is a bracket token
  (``[DONE]`` / ``[ASK_HUMAN]`` / …) for grep.
- ``plain``: the v0.1 column-aligned shape, byte-identical to the
  pre-v0.5 ``render_summary`` output. ``final_summary`` always stores
  this shape so checkpoint replay + grep workflows keep working.

Spec §12 boundary: CLI text formatting, not a UI / daemon.
``print_summary`` writes to stdout once and returns. Pure stdlib +
``click.style`` (no ``rich`` / ``colorama``). Tier 3 (``json``,
``quiet``, "Next Steps") ships in a follow-up PR.
"""

from __future__ import annotations

import os
import shutil
import sys
import textwrap
from typing import Any

import click

from ai_cockpit.state import TaskState

__all__ = [
    "print_summary", "render_summary_plain", "render_summary_text",
    "is_color_enabled",
]


_MIN_WIDTH, _MAX_WIDTH, _DEFAULT_WIDTH = 60, 100, 72
_DECISION_FG: dict[str, str] = {
    "done": "green", "retry": "yellow", "ask_human": "red", "stop": "magenta",
}
_RISK_FG: dict[str, str] = {"low": "green", "medium": "yellow", "high": "red"}


def is_color_enabled(*, stream: Any = None) -> bool:
    """True iff ANSI codes should be emitted. Honors ``NO_COLOR`` and
    only colors a real TTY — non-TTY pipes (CliRunner, redirects) get
    plain text so substring grep keeps working."""
    if os.environ.get("NO_COLOR"):
        return False
    target = stream if stream is not None else sys.stdout
    isatty = getattr(target, "isatty", None)
    try:
        return bool(isatty and isatty())
    except (ValueError, OSError):
        return False


def _terminal_width() -> int:
    try:
        cols = shutil.get_terminal_size(fallback=(_DEFAULT_WIDTH, 24)).columns
    except (ValueError, OSError):
        cols = _DEFAULT_WIDTH
    return max(_MIN_WIDTH, min(cols, _MAX_WIDTH))


def _style(text: str, *, color: bool, **kwargs: Any) -> str:
    return click.style(text, **kwargs) if color else text


def _wrap(text: str, *, indent: str, width: int) -> list[str]:
    """Indent + wrap *text* while preserving its line breaks."""
    out: list[str] = []
    for line in text.splitlines() or [""]:
        if not line.strip():
            out.append("")
            continue
        wrapped = textwrap.wrap(
            line, width=max(_MIN_WIDTH, width - len(indent)),
            break_long_words=False, break_on_hyphens=False,
        ) or [""]
        out.extend(indent + w for w in wrapped)
    return out


def _decision_token(decision: str, *, color: bool) -> str:
    fg = _DECISION_FG.get(decision, "white")
    return _style(f"[{(decision or 'unknown').upper()}]",
                  color=color, fg=fg, bold=True)


def _bool_token(value: bool, *, color: bool) -> str:
    if value:
        return _style("pass", color=color, fg="green", bold=True)
    return _style("FAIL", color=color, fg="red", bold=True)


def _risk_token(risk: str, *, color: bool) -> str:
    r = (risk or "unknown").lower()
    fg = _RISK_FG.get(r, "white")
    bold = r == "high"
    return _style(r, color=color, fg=fg, bold=bold)


def _cmd_status_token(exit_code: int, *, color: bool) -> str:
    if exit_code == 0:
        return _style("[ok]      ", color=color, fg="green")
    return _style(f"[FAIL {exit_code:>2}] ", color=color, fg="red", bold=True)


def _section_divider(title: str, *, width: int, color: bool) -> list[str]:
    bar = _style("-" * width, color=color, fg="bright_black")
    return ["", bar, _style(f"  {title}", color=color, bold=True), bar]


# ---------------------------------------------------------------------------
# Plain renderer — v0.1-compatible (byte-stable; used for final_summary)
# ---------------------------------------------------------------------------


def render_summary_plain(state: TaskState) -> str:
    """Return the v0.1-compatible plain text summary.

    Stored verbatim in ``final_summary`` so the substring
    ``"AI Cockpit — Run Summary"`` is always present and downstream
    pipe-grep / checkpoint replay continues to work.
    """
    review: dict[str, Any] = dict(state.get("review_result") or {})
    verification: dict[str, Any] = dict(state.get("verification_result") or {})
    decision = state.get("decision", "ask_human")
    criteria = state.get("acceptance_criteria") or []
    issues = review.get("issues") or []
    notes = review.get("notes") or ""

    criteria_block = "\n".join(f"  - {c}" for c in criteria) or "  (none)"
    issues_block = "\n".join(f"  - {i}" for i in issues) or "  (none)"
    commands = list(verification.get("commands") or [])
    if not commands:
        commands_block = "  (no verification commands ran)"
    else:
        commands_block = "\n".join(
            "  - ["
            + ("ok" if c["exit_code"] == 0 else f"FAIL ({c['exit_code']})")
            + "] " + c["command"]
            for c in commands
        )

    git_status_raw = (verification.get("git_status") or "").rstrip()
    if not git_status_raw:
        git_status = "  (clean working tree)"
    else:
        git_status = "\n".join(f"  {line}" for line in git_status_raw.splitlines())

    parts = [
        "=" * 72,
        "AI Cockpit — Run Summary",
        "=" * 72,
        f"Mode:        {state.get('mode', 'exploration')}",
        f"Loops:       {state.get('loop_count', 0)} / {state.get('max_loops', 1)}",
        f"Decision:    {decision}",
        "",
        "Idea:",
        f"  {state.get('idea', '') or state.get('user_input', '')}",
        "",
        "MVP Spec:",
        *("  " + line for line in (state.get("mvp_spec") or "").splitlines()),
        "",
        "Acceptance Criteria:",
        criteria_block,
        "",
        "Implementation Slice:",
        f"  {state.get('implementation_slice', '')}",
        "",
        "Coder Result:",
        *("  " + line for line in (state.get("coder_result") or "").splitlines()),
        "",
        "Verification:",
        f"  passed: {verification.get('passed', False)}",
        commands_block,
        "  git status --short:",
        git_status,
        "",
        "Review:",
        f"  passed: {review.get('passed', False)}",
        f"  risk:   {review.get('risk_level', 'unknown')}",
        "  issues:",
        issues_block,
    ]
    if notes:
        parts += ["  notes:", f"    {notes}"]
    suggested = review.get("suggested_fix") or ""
    if suggested:
        parts += ["  suggested_fix:", f"    {suggested}"]
    parts += ["", "=" * 72, ""]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Text renderer — sectioned + colored
# ---------------------------------------------------------------------------


def render_summary_text(state: TaskState, *, color: bool | None = None,
                        width: int | None = None) -> str:
    """Render the colored / structured text view.

    When ``color`` is ``None`` it is auto-detected from stdout. When
    ``color`` is ``False`` the output is identical bytes to a TTY
    render minus ANSI escapes — same shape, no codes.
    """
    if color is None:
        color = is_color_enabled()
    w = width if width is not None else _terminal_width()

    review: dict[str, Any] = dict(state.get("review_result") or {})
    verification: dict[str, Any] = dict(state.get("verification_result") or {})
    decision = state.get("decision") or "ask_human"
    mode = state.get("mode") or "exploration"
    loops = state.get("loop_count", 0)
    max_loops = state.get("max_loops", 1)
    idea = state.get("idea") or state.get("user_input") or ""
    mvp_spec = state.get("mvp_spec") or ""
    impl_slice = state.get("implementation_slice") or ""
    coder_result = state.get("coder_result") or ""
    criteria = state.get("acceptance_criteria") or []
    issues = review.get("issues") or []
    notes = review.get("notes") or ""
    suggested_fix = review.get("suggested_fix") or ""

    heavy = _style("=" * w, color=color, fg="cyan", bold=True)
    lines: list[str] = [
        heavy,
        _style("  AI Cockpit — Run Summary", color=color, bold=True),
        heavy,
        "",
        f"  Decision:  {_decision_token(decision, color=color)}    "
        f"Mode: {mode}    Loops: {loops} / {max_loops}",
    ]

    lines.extend(_section_divider("Idea", width=w, color=color))
    lines.extend(_wrap(idea or "(no idea recorded)", indent="  ", width=w))

    lines.extend(_section_divider("Plan", width=w, color=color))
    if mvp_spec:
        lines.append(_style("  MVP Spec:", color=color, bold=True))
        lines.extend(_wrap(mvp_spec, indent="    ", width=w))
        lines.append("")
    if criteria:
        lines.append(_style("  Acceptance Criteria:", color=color, bold=True))
        check = _style("[ok]", color=color, fg="cyan")
        for c in criteria:
            wrapped = _wrap(c, indent="          ", width=w)
            if wrapped:
                lines.append(f"    {check}  {wrapped[0].lstrip()}")
                lines.extend(wrapped[1:])
        lines.append("")
    if impl_slice:
        lines.append(_style("  Implementation Slice:", color=color, bold=True))
        lines.extend(_wrap(impl_slice, indent="    ", width=w))

    lines.extend(_section_divider("Execution", width=w, color=color))
    if coder_result:
        lines.append(_style("  Coder:", color=color, bold=True))
        lines.extend(_wrap(coder_result, indent="    ", width=w))
        lines.append("")
    lines.append(
        f"  Verification:  {_bool_token(bool(verification.get('passed', False)), color=color)}"
    )
    cmds = list(verification.get("commands") or [])
    if not cmds:
        lines.append("    (no verification commands ran)")
    else:
        for c in cmds:
            lines.append(f"    {_cmd_status_token(int(c['exit_code']), color=color)}{c['command']}")
    lines.append("")
    lines.append(_style("  git status --short:", color=color, bold=True))
    git_status_raw = (verification.get("git_status") or "").rstrip()
    if not git_status_raw:
        lines.append("    (clean working tree)")
    else:
        lines.extend(f"    {ln}" for ln in git_status_raw.splitlines())

    lines.extend(_section_divider("Review", width=w, color=color))
    lines.append(
        f"  Verdict:  {_bool_token(bool(review.get('passed', False)), color=color)}"
    )
    lines.append(
        f"  Risk:     {_risk_token(review.get('risk_level', 'unknown'), color=color)}"
    )
    lines.append(_style("  Issues:", color=color, bold=True))
    if issues:
        for i in issues:
            wrapped = _wrap(i, indent="      ", width=w)
            if wrapped:
                lines.append(f"    - {wrapped[0].lstrip()}")
                lines.extend(wrapped[1:])
    else:
        lines.append("    (none)")
    if notes:
        lines.append(_style("  Notes:", color=color, bold=True))
        lines.extend(_wrap(notes, indent="    ", width=w))
    if suggested_fix:
        lines.append(_style("  Suggested fix:", color=color, bold=True))
        lines.extend(_wrap(suggested_fix, indent="    ", width=w))

    lines.append("")
    lines.append(heavy)
    lines.append("")
    return "\n".join(lines)


def print_summary(state: TaskState) -> str:
    """Dispatch on ``state['output_format']`` and print to stdout.

    Returns the v0.1-compatible plain text rendering for storage in
    ``final_summary`` regardless of the chosen format.
    """
    fmt = (state.get("output_format") or "text").lower()
    plain = render_summary_plain(state)
    click.echo(plain if fmt == "plain" else render_summary_text(state))
    return plain
