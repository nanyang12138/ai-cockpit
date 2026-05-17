"""B.10a — read-only Cursor CLI discovery.

Only safe sub-commands are invoked: ``<binary> --version`` (with
``-v`` fallback) and ``<binary> --help``. We never run ``--print``,
``--mode``, or anything else that would contact a remote LLM or
mutate files. Per contract §9 the probe is fully injectable so tests
can substitute a fake runner and never hit the real CLI.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

DEFAULT_CANDIDATE_BINARIES: tuple[str, ...] = ("agent", "cursor-agent", "cursor")
_PROBE_TIMEOUT_SECONDS: float = 10.0
_MODE_TOKEN_RE = re.compile(r"\b(plan|ask|agent|edit|code|chat)\b", re.IGNORECASE)
_VERSION_LINE_RE = re.compile(r"v?(\d+\.\d+(?:\.\d+)?(?:[-+][\w.]+)?)")

_Runner = Callable[[Sequence[str]], "subprocess.CompletedProcess[str]"]


@dataclass(frozen=True)
class CursorAdapterStatus:
    """One snapshot from ``ai-cockpit cursor status``.

    Tri-state booleans distinguish "not probed" (``None``) from
    "probed and absent" (``False``).
    """
    binary_name: str | None
    binary_path: str | None
    available: bool
    version: str | None = None
    supported_modes: tuple[str, ...] = ()
    json_print_advertised: bool | None = None
    trust_flag_advertised: bool | None = None
    resume_flag_advertised: bool | None = None
    errors: tuple[str, ...] = field(default_factory=tuple)


def _default_runner(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - args are flag-only probes
        list(args), capture_output=True, text=True,
        timeout=_PROBE_TIMEOUT_SECONDS, check=False,
    )


def _resolve_binary(
    override: str | None, candidates: Sequence[str]
) -> tuple[str | None, str | None, list[str]]:
    errors: list[str] = []
    if override:
        path = shutil.which(override) or (override if "/" in override else None)
        if path is None:
            errors.append(f"binary {override!r} not found on PATH")
        return override, path, errors
    for name in candidates:
        path = shutil.which(name)
        if path is not None:
            return name, path, errors
        errors.append(f"binary {name!r} not found on PATH")
    return None, None, errors


def _safe_run(runner: _Runner, args: Sequence[str], errors: list[str]) -> str | None:
    """Probe a sub-command; common failures become an ``errors`` entry."""
    try:
        result = runner(args)
    except (FileNotFoundError, OSError) as exc:
        errors.append(f"{' '.join(args)}: {exc}")
        return None
    except subprocess.TimeoutExpired:
        errors.append(f"{' '.join(args)}: timed out after {_PROBE_TIMEOUT_SECONDS}s")
        return None
    text = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0 and not text.strip():
        errors.append(f"{' '.join(args)}: exit {result.returncode} (no output)")
        return None
    return text


def _parse_version(text: str | None) -> str | None:
    if not text:
        return None
    for line in text.splitlines():
        match = _VERSION_LINE_RE.search(line)
        if match:
            return match.group(1)
    return None


def _parse_modes(help_text: str | None) -> tuple[str, ...]:
    """Pick ``--mode`` values from each ``--mode`` block.

    A block is the line that mentions ``--mode`` plus any continuation
    lines that are indented deeper than the ``--mode`` line and do not
    introduce another ``--flag``. This matches both compact help
    (``--mode plan|ask``) and the cursor-agent style where the choices
    appear on a wrapped continuation line such as
    ``--mode <mode>\\n      (choices: "plan", "ask")``.
    """
    if not help_text:
        return ()
    seen: dict[str, None] = {}
    lines = help_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if "--mode" in line.lower():
            mode_indent = len(line) - len(line.lstrip())
            for tok in _MODE_TOKEN_RE.findall(line):
                seen.setdefault(tok.lower(), None)
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                stripped = nxt.lstrip()
                if not stripped:
                    break
                nxt_indent = len(nxt) - len(stripped)
                if nxt_indent <= mode_indent or stripped.startswith("--"):
                    break
                for tok in _MODE_TOKEN_RE.findall(nxt):
                    seen.setdefault(tok.lower(), None)
                j += 1
            i = j
        else:
            i += 1
    return tuple(seen)


def _flag(help_text: str | None, *needles: str, all_required: bool = False) -> bool | None:
    """Tri-state flag presence check."""
    if not help_text or not help_text.strip():
        return None
    low = help_text.lower()
    return (all if all_required else any)(n.lower() in low for n in needles)


def probe_cursor_adapter(
    *,
    binary_override: str | None = None,
    candidate_names: Sequence[str] = DEFAULT_CANDIDATE_BINARIES,
    runner: _Runner | None = None,
) -> CursorAdapterStatus:
    """Run the read-only Cursor discovery probe.

    ``available=False`` means no candidate binary resolved; downstream
    B.10 backends MUST treat that as "fall back to builtin / aider"
    rather than crash.
    """
    run = runner or _default_runner
    name, path, errors = _resolve_binary(binary_override, candidate_names)
    if path is None:
        return CursorAdapterStatus(
            binary_name=name, binary_path=None, available=False, errors=tuple(errors),
        )
    version_text = _safe_run(run, [path, "--version"], errors)
    if version_text is None:
        version_text = _safe_run(run, [path, "-v"], errors)
    help_text = _safe_run(run, [path, "--help"], errors)
    return CursorAdapterStatus(
        binary_name=name,
        binary_path=path,
        available=True,
        version=_parse_version(version_text),
        supported_modes=_parse_modes(help_text),
        json_print_advertised=_flag(help_text, "--print", "--output-format", all_required=True),
        trust_flag_advertised=_flag(help_text, "--yolo", "--trust"),
        resume_flag_advertised=_flag(help_text, "--resume", "session"),
        errors=tuple(errors),
    )
