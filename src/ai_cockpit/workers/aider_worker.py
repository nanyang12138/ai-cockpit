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

import json
import logging
import os
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import yaml

from ai_cockpit.workers.base import WorkerRequest, WorkerResult

log = logging.getLogger(__name__)

DEFAULT_AIDER_ARGS: tuple[str, ...] = (
    "--yes-always",
    "--no-stream",
    "--no-auto-commits",
)


def _detect_protocol(base: str | None, model: str | None) -> str:
    """Same detection used by ``ai_cockpit.llm.provider`` — pick Anthropic
    vs OpenAI from the env so the aider model string carries the right
    LiteLLM provider prefix."""

    explicit = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if explicit in {"anthropic", "openai"}:
        return explicit
    if base and "anthropic" in base.lower():
        return "anthropic"
    if model and model.lower().startswith("claude"):
        return "anthropic"
    return "openai"


def _aider_model_string(protocol: str, model: str) -> str:
    if "/" in model:
        return model
    return f"{protocol}/{model}"


def _parse_extra_headers() -> dict[str, str] | None:
    """Read ``LLM_API_EXTRA_HEADERS`` (JSON object) into a dict, or None.

    Matches the parser in ``ai_cockpit.llm.provider`` so the AMD APIM
    setup works identically across planner / reviewer / aider worker.
    """

    raw = os.environ.get("LLM_API_EXTRA_HEADERS", "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.warning(
            "LLM_API_EXTRA_HEADERS is not valid JSON (%s); aider will not "
            "receive any custom headers",
            exc,
        )
        return None
    if not isinstance(parsed, dict):
        log.warning(
            "LLM_API_EXTRA_HEADERS must be a JSON object, got %s; "
            "aider will not receive any custom headers",
            type(parsed).__name__,
        )
        return None
    return {str(k): str(v) for k, v in parsed.items()}


def _write_model_settings_file(model_name: str, extra_headers: dict[str, str]) -> str:
    """Materialize a one-entry aider model-settings YAML and return its path.

    Aider's ``--model-settings-file`` consumes a list of ModelSettings
    entries. ``extra_params`` is splatted into the underlying LiteLLM
    completion call, so ``extra_params.extra_headers`` is the documented
    path to inject HTTP headers like Azure APIM's
    ``Ocp-Apim-Subscription-Key`` (confirmed against aider 0.86's
    ``aider.models.ModelSettings``).
    """

    payload = [
        {
            "name": model_name,
            "extra_params": {"extra_headers": extra_headers},
        }
    ]
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".aider-settings.yml", delete=False
    )
    try:
        yaml.safe_dump(payload, tmp, sort_keys=False)
    finally:
        tmp.close()
    return tmp.name


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

    def _build_command(
        self,
        message: str,
        *,
        model: str | None = None,
        model_settings_file: str | None = None,
    ) -> list[str]:
        cmd: list[str] = [self.executable, *DEFAULT_AIDER_ARGS]
        if model:
            cmd.extend(["--model", model])
        if model_settings_file:
            cmd.extend(["--model-settings-file", model_settings_file])
        cmd.extend(self.extra_args)
        cmd.extend(["--message", message])
        return cmd

    def _resolve_apim_bridge(self) -> tuple[str | None, str | None]:
        """If APIM headers are configured, return (model_string, settings_path).

        Otherwise return (None, None) and the worker falls back to whatever
        aider auto-detects from its own env vars. Either branch keeps the
        worker generic — nothing about the AMD endpoint is hardcoded.
        """

        headers = _parse_extra_headers()
        model_name = os.environ.get("LLM_MODEL_NAME", "").strip()
        if not headers or not model_name:
            return None, None
        protocol = _detect_protocol(os.environ.get("LLM_API_BASE"), model_name)
        model_string = _aider_model_string(protocol, model_name)
        settings_path = _write_model_settings_file(model_string, headers)
        return model_string, settings_path

    def run(self, request: WorkerRequest) -> WorkerResult:
        message = self._build_message(request)
        model, settings_path = self._resolve_apim_bridge()
        command = self._build_command(
            message, model=model, model_settings_file=settings_path
        )

        def _cleanup() -> None:
            if settings_path:
                try:
                    os.unlink(settings_path)
                except OSError:
                    pass

        if request.dry_run:
            preview = (
                "AiderWorker preview (--apply NOT passed; nothing was executed).\n"
                f"command: {' '.join(command[:-1])} <MESSAGE>\n"
                "message:\n"
                f"{message}"
            )
            _cleanup()
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
            _cleanup()
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
            _cleanup()
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

        _cleanup()
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
