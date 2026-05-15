"""Tiny, safe wrapper around `subprocess.run` for verifier commands.

We intentionally keep this minimal: no pipes, no shell expansion tricks
beyond what `shell=True` already gives, and a hard timeout so a bad test
command cannot wedge the workflow.
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from ai_cockpit.state import CommandResult


def run_command(
    command: str,
    *,
    cwd: Path | str,
    timeout: float = 120.0,
) -> CommandResult:
    """Run `command` in `cwd` and capture exit code, stdout, stderr.

    Uses `shell=True` so users can pass natural commands like
    ``python -m pytest -q``. Failures and timeouts are converted into a
    structured `CommandResult` rather than raising, so the verifier can
    record evidence either way.
    """

    cwd_path = Path(cwd)
    try:
        completed = subprocess.run(
            command,
            shell=True,
            cwd=str(cwd_path),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return CommandResult(
            command=command,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            command=command,
            exit_code=124,
            stdout=exc.stdout or "" if isinstance(exc.stdout, str) else "",
            stderr=f"Command timed out after {timeout}s",
        )
    except FileNotFoundError as exc:
        return CommandResult(
            command=command,
            exit_code=127,
            stdout="",
            stderr=str(exc),
        )


def quote(arg: str) -> str:
    """Convenience wrapper to shell-quote a single arg."""

    return shlex.quote(arg)
