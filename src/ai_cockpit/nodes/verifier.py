"""Verifier node: deterministic evidence collection.

Captures `git status --short`, `git diff`, and runs any user-provided
test commands. Each command's exit code, stdout, and stderr are preserved
verbatim so the reviewer judges facts, not summaries.
"""

from __future__ import annotations

from ai_cockpit.state import TaskState, VerificationResult
from ai_cockpit.tools.git import git_diff, git_status_short
from ai_cockpit.tools.shell import run_command


def verifier_node(state: TaskState) -> TaskState:
    """Collect git evidence and (optionally) run test commands."""

    project_root = state.get("project_root", ".")
    test_commands = list(state.get("test_commands", []) or [])
    dry_run = bool(state.get("dry_run", False))

    status = git_status_short(project_root)
    diff = git_diff(project_root)

    command_results = []
    if not dry_run:
        for cmd in test_commands:
            command_results.append(run_command(cmd, cwd=project_root))

    all_passed = all(r["exit_code"] == 0 for r in command_results)
    verification: VerificationResult = {
        "passed": all_passed,
        "commands": command_results,
        "git_diff": diff,
        "git_status": status,
    }

    return {
        "git_status": status,
        "git_diff": diff,
        "verification_result": verification,
    }
