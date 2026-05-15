"""Read-only git helpers used by the verifier node.

We never call mutating git commands (no commit, push, checkout, reset).
"""

from __future__ import annotations

from pathlib import Path

from ai_cockpit.tools.shell import run_command


def git_status_short(project_root: Path | str) -> str:
    """Return ``git status --short`` output, or an explanatory string."""

    result = run_command("git status --short", cwd=project_root)
    if result["exit_code"] == 0:
        return result["stdout"]
    return f"<git status failed: exit={result['exit_code']}> {result['stderr'].strip()}"


def git_diff(project_root: Path | str) -> str:
    """Return ``git diff`` output (unstaged changes), or an explanatory string."""

    result = run_command("git diff", cwd=project_root)
    if result["exit_code"] == 0:
        return result["stdout"]
    return f"<git diff failed: exit={result['exit_code']}> {result['stderr'].strip()}"


def is_git_repo(project_root: Path | str) -> bool:
    """Return True if ``project_root`` is inside a git working tree."""

    result = run_command("git rev-parse --is-inside-work-tree", cwd=project_root)
    return result["exit_code"] == 0 and result["stdout"].strip() == "true"
