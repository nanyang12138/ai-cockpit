"""Verifier node: deterministic evidence collection.

Captures `git status --short`, `git diff`, and runs any user-provided
test commands. Each command's exit code, stdout, and stderr are preserved
verbatim so the reviewer judges facts, not summaries.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from ai_cockpit.state import CommandResult, TaskState, VerificationResult
from ai_cockpit.tools.git import git_diff, git_status_short
from ai_cockpit.tools.shell import run_command

# Bug F (2026-05-17 v0.4 attempt 7): when the planner emits a path
# prefixed by the verifier's own cwd basename (e.g. cwd=.../examples/
# broken_calc and cmd='pytest -v examples/broken_calc'), pytest exits
# with 4 + "file or directory not found". This pattern is recoverable
# at runtime: detect it and append an operator-visible hint to stderr.
_PATH_NOT_FOUND_RE = re.compile(
    r"(?:no such file or directory|file or directory not found|errno\s*2)",
    re.IGNORECASE,
)


def _diagnose_path_doubling(
    cmd: str, cwd: Path, result: CommandResult
) -> str | None:
    """Return a hint string if the command looks like cwd-name doubling.

    Heuristic: if any argv token starts with ``<cwd.name>/`` or is
    exactly ``cwd.name``, and the same path is reachable from
    ``cwd.parent``, the planner likely emitted a repo-root-relative
    path while the verifier ran with cwd already inside that subdir.
    """

    if result["exit_code"] == 0:
        return None
    stderr_blob = (result.get("stderr") or "") + (result.get("stdout") or "")
    if not _PATH_NOT_FOUND_RE.search(stderr_blob):
        return None
    try:
        tokens = shlex.split(cmd)
    except ValueError:
        return None
    cwd_name = cwd.name
    if not cwd_name:
        return None
    for tok in tokens:
        if tok == cwd_name or tok.startswith(cwd_name + "/"):
            if (cwd.parent / tok).exists() and not (cwd / tok).exists():
                return (
                    f"\nai-cockpit-verifier hint: command argument {tok!r} "
                    f"does not exist under cwd '{cwd}' but DOES exist under "
                    f"'{cwd.parent}'. The verifier runs every test_command "
                    f"with cwd=--root ({cwd}); the planner likely emitted a "
                    "repo-root-relative path by mistake. Re-run the plan "
                    "with --worker <name> set so the B.2 quirk + the Bug F "
                    "verifier-cwd context block reach the planner, or edit "
                    "the saved plan yaml so test_commands omit the "
                    f"'{cwd_name}/' prefix (e.g. 'pytest -v' not "
                    f"'pytest {cwd_name} -v')."
                )
    return None


def verifier_node(state: TaskState) -> TaskState:
    """Collect git evidence and (optionally) run test commands."""

    project_root = state.get("project_root", ".")
    test_commands = list(state.get("test_commands", []) or [])
    dry_run = bool(state.get("dry_run", False))

    status = git_status_short(project_root)
    diff = git_diff(project_root)

    cwd_path = Path(project_root)
    command_results: list[CommandResult] = []
    if not dry_run:
        for cmd in test_commands:
            result = run_command(cmd, cwd=cwd_path)
            hint = _diagnose_path_doubling(cmd, cwd_path, result)
            if hint is not None:
                # Append, do not replace, so the original tool error
                # stays auditable on the reviewer evidence path.
                result = {
                    "command": result["command"],
                    "exit_code": result["exit_code"],
                    "stdout": result["stdout"],
                    "stderr": (result.get("stderr") or "") + hint,
                }
            command_results.append(result)

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
