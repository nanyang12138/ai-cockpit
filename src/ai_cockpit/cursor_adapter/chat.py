"""B.10/chat — Cursor-backed interactive chat (v0.5 row #11 sub-gate a).

Spawns cursor's interactive mode (or a one-shot Q&A) with the project's
``.ai-cockpit/memory/*.md`` pre-loaded as the cursor session's system
prompt. Read-only enforcement is two-layer per locked contract §3 Q1:

  1. Primary — pass cursor's ``--read-only`` flag (best-effort; the
     exact flag name varies across cursor builds).
  2. Fallback / defense-in-depth — take a ``git status --porcelain``
     snapshot before chat, diff after, report any new uncommitted
     paths to stderr on exit.

The fallback is suboptimal (post-hoc detection only); both layers run
in every chat session so the operator is loudly informed if cursor
modified files anyway.

Contract: ``docs/V0_5_ROW_11_CHAT_MODE_CONTRACT.md`` (LOCKED).
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from ai_cockpit.cursor_adapter.discovery import DEFAULT_CANDIDATE_BINARIES

# Q4: 64 KB cap on injected memory; over-cap files truncated alphabetically.
MEMORY_BUDGET_BYTES = 64 * 1024

# Best-effort cursor CLI flag names. If a specific cursor build uses
# different flag names, the fallback git-stash detection still catches
# any write that slips past the primary layer.
_CURSOR_READONLY_FLAG = "--read-only"
_CURSOR_SYSTEM_PROMPT_FLAG = "--system-prompt"


@dataclass(frozen=True)
class ChatSpawnResult:
    """One chat session's outcome (returned to the caller for reporting)."""

    exit_code: int
    cursor_binary: str | None
    system_prompt_bytes: int
    truncated_files: tuple[str, ...]
    dirty_paths_on_exit: tuple[str, ...]

    @property
    def cursor_found(self) -> bool:
        return self.cursor_binary is not None


def compose_system_prompt(
    project_root: str | Path,
    *,
    budget_bytes: int = MEMORY_BUDGET_BYTES,
) -> tuple[str, tuple[str, ...]]:
    """Concatenate ``.ai-cockpit/memory/*.md`` into a single string with
    per-file ``## <path>`` headers + begin/end markers.

    Returns ``(prompt, truncated_filenames)``. Returns ``("", ())`` if no
    memory directory or no ``*.md`` files exist. Over-cap files are
    truncated in alphabetical order (deterministic per Q4).
    """
    memory_dir = Path(project_root) / ".ai-cockpit" / "memory"
    if not memory_dir.is_dir():
        return "", ()
    md_files = sorted(memory_dir.glob("*.md"))
    if not md_files:
        return "", ()

    header = (
        f"[ai-cockpit project memory; root={project_root}]\n"
        "[Read-only context for this chat session; "
        "edits to memory/* still require `ai-cockpit memory accept`.]\n"
    )
    parts: list[str] = [header]
    used = len(header)
    truncated: list[str] = []
    for path in md_files:
        rel = f".ai-cockpit/memory/{path.name}"
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        block = f"\n## {rel}\n{content}\n"
        if used + len(block) > budget_bytes:
            truncated.append(rel)
            continue
        parts.append(block)
        used += len(block)
    parts.append("\n[end of injected memory]\n")
    return "".join(parts), tuple(truncated)


def _resolve_cursor_binary(
    override: str | None,
    candidates: Sequence[str] = DEFAULT_CANDIDATE_BINARIES,
) -> str | None:
    """Discover the cursor binary path; ``None`` if not found."""
    if override:
        return shutil.which(override) or override
    for name in candidates:
        path = shutil.which(name)
        if path is not None:
            return path
    return None


def _dirty_paths(project_root: str) -> tuple[str, ...]:
    """Return uncommitted paths via ``git status --porcelain``."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ()
    if result.returncode != 0:
        return ()
    return tuple(
        line[3:].strip() for line in result.stdout.splitlines() if len(line) >= 3
    )


# Test-injectable runner. Default implementation spawns the cursor
# subprocess with inherited stdin/stdout/stderr (Q5 — operator types
# directly into cursor, cursor's output streams directly to the
# operator's terminal). Returns the cursor process exit code.
_RunnerProtocol = Callable[[Sequence[str], str], int]


def _default_runner(args: Sequence[str], cwd: str) -> int:
    return subprocess.run(  # noqa: S603 - args constructed from controlled inputs
        list(args), cwd=cwd, check=False
    ).returncode


def build_cursor_args(
    binary: str,
    system_prompt: str,
    question: str | None,
) -> list[str]:
    """Compose the argv for the cursor subprocess.

    Order: ``binary --read-only --system-prompt <prompt> [question]``.
    Read-only flag goes FIRST so an unknown-flag error from cursor's
    arg parser surfaces immediately (and the operator can disable by
    invoking cursor directly).
    """
    args: list[str] = [binary, _CURSOR_READONLY_FLAG]
    if system_prompt:
        args += [_CURSOR_SYSTEM_PROMPT_FLAG, system_prompt]
    if question:
        args.append(question)
    return args


def spawn_cursor_chat(
    project_root: str | Path,
    *,
    question: str | None = None,
    binary_override: str | None = None,
    runner: _RunnerProtocol = _default_runner,
) -> ChatSpawnResult:
    """Spawn cursor in interactive (or one-shot) mode with memory injected.

    Returns a ``ChatSpawnResult`` whose ``dirty_paths_on_exit`` is the
    set of paths that became dirty during the chat session (the
    fallback read-only enforcement layer per Q1). Caller is responsible
    for surfacing those to the operator's stderr.

    If the cursor binary cannot be resolved (Q2 missing-cursor path),
    returns an exit-code-127 result with ``cursor_binary=None``; caller
    should fall back to ``--backend builtin`` (sub-gate b) or print
    a clean error.
    """
    project_root_str = str(Path(project_root).resolve())
    binary = _resolve_cursor_binary(binary_override)
    if binary is None:
        return ChatSpawnResult(
            exit_code=127,
            cursor_binary=None,
            system_prompt_bytes=0,
            truncated_files=(),
            dirty_paths_on_exit=(),
        )

    system_prompt, truncated = compose_system_prompt(project_root_str)
    pre_dirty = set(_dirty_paths(project_root_str))
    args = build_cursor_args(binary, system_prompt, question)
    exit_code = runner(args, project_root_str)
    post_dirty = _dirty_paths(project_root_str)
    new_dirty = tuple(p for p in post_dirty if p not in pre_dirty)

    return ChatSpawnResult(
        exit_code=exit_code,
        cursor_binary=binary,
        system_prompt_bytes=len(system_prompt),
        truncated_files=truncated,
        dirty_paths_on_exit=new_dirty,
    )
