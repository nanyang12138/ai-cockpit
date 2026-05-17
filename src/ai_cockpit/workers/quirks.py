"""Worker-quirk catalog consumed by the planner prompt (B.2).

The planner needs to know the behavioural fingerprint of the worker
backend that will run the slice. Acceptance criteria like "no other
files modified" are brittle against ``aider`` (it auto-edits
``.gitignore`` on each invocation, see §15.1) and against ``cursor``
agent (workspace scan stamps a session-id file). B.2 closes the
structural gap by handing the planner a short hint list at message-
build time — *avoidance* hints, never schema relaxations.

§9 hard boundary: the catalog must never reach the reviewer prompt.
``build_reviewer_messages`` does not import this module and the
companion test asserts the reviewer system+user pair contains no
quirk substring.

Catalog growth policy:

* Each worker bucket caps at 6 entries (``_HINT_BUDGET``); new quirks
  replace the oldest stale entry rather than appending unbounded.
* Each ``human_summary`` clips to 80 chars to honour the
  per-bullet budget the prompt builder enforces (B.2 contract Q2).
* ``criteria_to_avoid`` carries up to 3 illustrative bad criteria for
  human reviewers; they are NOT injected into the prompt — only the
  ``human_summary`` is.

Unknown worker names return ``[]`` and emit a single INFO log line;
this keeps B.1 successor backends forward-compatible without breaking
the existing CLI surface (B.2 contract Q3).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

_HINT_BUDGET: int = 6
_HINT_CHAR_BUDGET: int = 80


@dataclass(frozen=True)
class WorkerQuirk:
    """A single behavioural quirk the planner must design around."""

    id: str
    human_summary: str
    criteria_to_avoid: tuple[str, ...] = ()
    replacement_hint: str = ""


_AIDER_GITIGNORE = WorkerQuirk(
    id="aider.gitignore",
    human_summary=(
        "aider may edit .gitignore each run; do not require an "
        "exact-N-file diff or 'no other files modified'."
    ),
    criteria_to_avoid=(
        "Diff touches exactly 1 file.",
        "No other files are modified.",
        "Working tree changes are limited to the listed paths.",
    ),
    replacement_hint=(
        "Phrase diff-size criteria around the *target* files (e.g. "
        "'src/foo.py contains the new helper'), not the global tree shape."
    ),
)

_CURSOR_WORKSPACE_SCAN = WorkerQuirk(
    id="cursor.workspace_scan",
    human_summary=(
        "cursor agent scans the workspace each turn (~19k input tokens); "
        "avoid per-turn token caps."
    ),
    criteria_to_avoid=(
        "Each turn uses fewer than N input tokens.",
        "Worker output stays under a per-turn cost ceiling.",
    ),
    replacement_hint=(
        "Cost is enforced per-run by B.3's cost dashboard, not per-turn "
        "by the planner; phrase budgets in dollars-per-slice instead."
    ),
)

# Surfaced by the 2026-05-17 v0.4 exit-gate attempts 3 + 4: the
# planner emitted ``pytest examples/broken_calc -v`` as a slice-level
# test_command, but the verifier runs with ``cwd=examples/broken_calc``
# under ``--root examples/broken_calc``, so the command resolves to
# ``cd examples/broken_calc && pytest examples/broken_calc -v`` →
# exit 4 "file or directory not found". The quirk is worker-agnostic
# (it's a planner-emission convention issue, not aider-specific) but
# it shows up via the worker's verification commands, so we surface
# it on every apply-capable worker bucket.
#
# Ergonomics note (attempt 4 / 5 calibration, PR #81): ``human_summary``
# MUST stay under ``_HINT_CHAR_BUDGET`` (80 chars) **including the
# concrete good→bad example**, because the clip in ``_clip()`` would
# otherwise truncate exactly the example that makes the hint
# behaviour-changing. The first version of this quirk landed at 153
# chars and got clipped to 80 just before the example, which left the
# planner LLM with only the abstract "don't prefix with project_root"
# fragment — interpreted as "improve test discovery" instead of "drop
# the path prefix". The current phrasing is 79 chars including the
# concrete "'pytest -v' not 'pytest <root> -v'" pair.
_TESTCMD_PATH_RELATIVE_TO_CWD = WorkerQuirk(
    id="verifier.test_command_path_relative_to_root",
    human_summary=(
        "test_command's cwd = --root dir; emit 'pytest -v' "
        "not 'pytest <dir>/ -v'."
    ),
    criteria_to_avoid=(
        "pytest <project_root_subdir> -v",
        "ruff check <project_root>/<file>",
        "python -m pytest examples/<fixture>/",
    ),
    replacement_hint=(
        "Emit test_commands relative to the verifier's cwd (which is "
        "always --root): 'pytest -v', 'ruff check .', 'python -m "
        "pytest -q'. The verifier already cd's into --root."
    ),
)


WORKER_QUIRKS: dict[str, tuple[WorkerQuirk, ...]] = {
    "aider": (_AIDER_GITIGNORE, _TESTCMD_PATH_RELATIVE_TO_CWD),
    "cursor": (_CURSOR_WORKSPACE_SCAN, _TESTCMD_PATH_RELATIVE_TO_CWD),
    "stub": (),
}


def _clip(text: str, limit: int = _HINT_CHAR_BUDGET) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def format_worker_hints_block(
    hints: list[str] | None, worker_name: str | None
) -> str | None:
    """Render the planner hint subsection, or ``None`` if empty.

    Shared by both prompt builders to keep clip discipline (≤6 bullets,
    each ≤``_HINT_CHAR_BUDGET`` chars) in a single place. Returning
    ``None`` lets the builder skip appending an empty block entirely.
    """

    if not hints:
        return None
    bullets: list[str] = []
    for raw in hints[:_HINT_BUDGET]:
        text = _clip(raw or "")
        if text:
            bullets.append(f"- {text}")
    if not bullets:
        return None
    label = (worker_name or "unspecified").strip().lower() or "unspecified"
    return (
        f"Worker quirks to design around (current backend: {label}):\n"
        + "\n".join(bullets)
    )


def quirks_for(worker_name: str | None) -> list[str]:
    """Return the human-summary strings for ``worker_name``.

    * Empty / ``None`` / unknown names → ``[]`` plus an INFO log line.
    * Known names → up to ``_HINT_BUDGET`` clipped human summaries.

    The result is deliberately a plain ``list[str]`` so prompt builders
    can serialise it without importing the dataclass (keeping the §9
    boundary lean — only the reviewer-irrelevant text crosses).
    """

    if not worker_name:
        return []
    key = worker_name.strip().lower()
    bucket = WORKER_QUIRKS.get(key)
    if bucket is None:
        log.info(
            "worker_quirks: no catalog entry for worker=%r; "
            "planner will see no worker hints.",
            worker_name,
        )
        return []
    return [_clip(q.human_summary) for q in bucket[:_HINT_BUDGET]]


__all__ = [
    "WORKER_QUIRKS",
    "WorkerQuirk",
    "format_worker_hints_block",
    "quirks_for",
]
