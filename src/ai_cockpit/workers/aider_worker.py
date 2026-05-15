"""AiderWorker — wraps the ``aider`` CLI as an ai-cockpit worker.

v0.3 step 2. Builds a single ``aider --message ...`` subprocess call
from the planner's ``implementation_slice`` + acceptance criteria and
captures stdout/stderr verbatim for the reviewer.

Safety contract (per V0_2_PLAN.md Step 2):

- ``request.dry_run`` short-circuits: the worker prints what it WOULD
  have asked aider to do and spawns no subprocess. The CLI's
  ``--worker aider`` defaults ``dry_run`` to True; ``--apply`` flips it.
- Subprocess inherits the current process env so ``LLM_*`` envs reach
  aider unchanged. Mapping them to aider's expected names is the user's
  job (documented in README).
- We pass ``--yes-always --no-stream --no-auto-commits`` to keep aider
  non-interactive and leave its diff uncommitted for the verifier.
- ``subprocess_runner`` is exposed as a dataclass field so tests can
  inject a fake runner without installing aider in CI.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from ai_cockpit.workers.base import WorkerRequest, WorkerResult

DEFAULT_AIDER_ARGS: tuple[str, ...] = (
    "--yes-always",
    "--no-stream",
    "--no-auto-commits",
)


def _default_runner(
    cmd: Sequence[str], *, cwd: str, env: dict[str, str], timeout: float | None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(cmd),
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


@dataclass
class AiderWorker:
    """Run a single aider invocation per ``WorkerRequest``."""

    name: str = "aider"
    executable: str = "aider"
    extra_args: tuple[str, ...] = ()
    timeout_seconds: float | None = 300.0
    subprocess_runner: Callable[..., Any] = field(default=_default_runner)

    def _build_message(self, request: WorkerRequest) -> str:
        criteria_block = ""
        if request.acceptance_criteria:
            criteria_block = "\n\nAcceptance criteria:\n" + "\n".join(
                f"- {c}" for c in request.acceptance_criteria
            )
        return (
            f"Objective: {request.objective}\n\n"
            f"Implementation slice: {request.implementation_slice}"
            f"{criteria_block}"
        )

    def _build_command(self, message: str) -> list[str]:
        return [self.executable, *DEFAULT_AIDER_ARGS, *self.extra_args, "--message", message]

    def run(self, request: WorkerRequest) -> WorkerResult:
        message = self._build_message(request)
        command = self._build_command(message)

        if request.dry_run:
            preview = (
                "AiderWorker preview (--apply NOT passed; nothing was executed).\n"
                f"command: {' '.join(command[:-1])} <MESSAGE>\n"
                "message:\n"
                f"{message}"
            )
            return WorkerResult(
                summary=preview,
                changed_files=[],
                notes="AiderWorker dry-run: no subprocess was spawned.",
            )

        env = dict(os.environ)
        try:
            completed = self.subprocess_runner(
                command,
                cwd=request.project_root,
                env=env,
                timeout=self.timeout_seconds,
            )
        except FileNotFoundError as exc:
            return WorkerResult(
                summary=(
                    "AiderWorker error: aider executable not found "
                    f"({self.executable!r}). Install with `pip install aider-chat` "
                    "and ensure the venv's bin directory is on PATH."
                ),
                changed_files=[],
                notes=f"FileNotFoundError: {exc}",
            )
        except subprocess.TimeoutExpired as exc:
            raw_partial = exc.stdout
            if isinstance(raw_partial, bytes):
                partial = raw_partial.decode("utf-8", errors="replace")
            else:
                partial = raw_partial or ""
            return WorkerResult(
                summary=(
                    "AiderWorker error: aider exceeded the configured timeout "
                    f"({self.timeout_seconds} s). Partial stdout below.\n\n"
                    f"{partial.strip()}"
                ),
                changed_files=[],
                notes="TimeoutExpired: aider was terminated by the worker.",
            )

        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        summary = (
            f"AiderWorker exit_code={completed.returncode}\n"
            f"command: {' '.join(command[:-1])} <MESSAGE>\n"
            "--- aider stdout ---\n"
            f"{stdout if stdout else '(empty)'}\n"
            "--- aider stderr ---\n"
            f"{stderr if stderr else '(empty)'}"
        )
        notes = (
            "aider invocation completed."
            if completed.returncode == 0
            else f"aider exited non-zero: {completed.returncode}."
        )
        return WorkerResult(summary=summary, changed_files=[], notes=notes)
