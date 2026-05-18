"""B.10/chat — Cursor-backed interactive chat (v0.5 row #11 sub-gate a).

Spawns cursor's interactive mode (or a one-shot Q&A) with the project's
``.ai-cockpit/memory/*.md`` injected as context. Memory-injection
strategy depends on the chat shape (the locked Q4 system-prompt flag
was build-specific and rejected by some cursor binaries, so this
module uses build-agnostic delivery instead — surfaced 2026-05-18
07:59 UTC):

  * One-shot (``ai-cockpit chat "<question>"``): memory is prepended
    to the question text; cursor receives one combined positional
    argument so no flag negotiation is required.
  * Interactive (``ai-cockpit chat``): memory is written to
    ``<root>/.ai-cockpit/history/chat-context-<thread>.md`` and the
    path is reported on stderr so the operator can paste it into
    cursor's first message manually.

Read-only enforcement is now single-layer per the same surfacing:
``git status --porcelain`` snapshot before chat, diff after, report
any new uncommitted paths on exit. The contract-§3-Q1 "primary"
layer (cursor's own ``--read-only`` flag) was dropped because the
flag name is build-specific and the layer-2 detection catches the
same misbehaviour after the fact.

Contract: ``docs/V0_5_ROW_11_CHAT_MODE_CONTRACT.md`` (LOCKED).
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from ai_cockpit.checkpoint import new_thread_id
from ai_cockpit.cursor_adapter.discovery import DEFAULT_CANDIDATE_BINARIES

# Q4: 64 KB cap on injected memory; over-cap files truncated alphabetically.
MEMORY_BUDGET_BYTES = 64 * 1024


@dataclass(frozen=True)
class ChatSpawnResult:
    """One chat session's outcome (returned to the caller for reporting)."""

    exit_code: int
    cursor_binary: str | None
    system_prompt_bytes: int
    truncated_files: tuple[str, ...]
    dirty_paths_on_exit: tuple[str, ...]
    # Path to the temp file containing the project memory dump, if any.
    # Populated only in interactive mode when memory was non-empty; the
    # caller surfaces this path to the operator so they can paste it
    # into cursor's first message manually. ``None`` in one-shot mode
    # (memory was prepended directly to the question instead).
    memory_context_file: str | None = None

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
    question: str | None,
) -> list[str]:
    """Compose the argv for the cursor subprocess.

    Build-agnostic: ``[binary]`` for interactive, ``[binary, question]``
    for one-shot. No flag negotiation — memory injection is handled
    out-of-band (prepended to ``question`` upstream, or written to a
    temp file in interactive mode and surfaced to the operator).
    """
    args: list[str] = [binary]
    if question:
        args.append(question)
    return args


def _write_memory_context_file(
    project_root: str,
    body: str,
) -> str:
    """Write the memory dump to a thread-tagged file under history/.

    Returns the absolute path so the caller can surface it on stderr.
    ``.ai-cockpit/history/`` is already gitignored under A.8.
    """
    history_dir = Path(project_root) / ".ai-cockpit" / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    path = history_dir / f"chat-context-{new_thread_id()}.md"
    path.write_text(body, encoding="utf-8")
    return str(path)


def spawn_cursor_chat(
    project_root: str | Path,
    *,
    question: str | None = None,
    binary_override: str | None = None,
    runner: _RunnerProtocol = _default_runner,
) -> ChatSpawnResult:
    """Spawn cursor in interactive (or one-shot) mode with memory injected.

    Memory-injection strategy (build-agnostic):
      * One-shot (``question`` given): memory text is prepended to
        ``question`` and passed as a single positional argument.
      * Interactive (``question`` is None): memory is written to a
        per-thread temp file under ``.ai-cockpit/history/``; the path
        is returned in ``memory_context_file`` so the caller can show
        it to the operator.

    Returns a ``ChatSpawnResult`` whose ``dirty_paths_on_exit`` is the
    set of paths that became dirty during the chat session (the
    fallback read-only enforcement layer per Q1).
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
            memory_context_file=None,
        )

    memory_text, truncated = compose_system_prompt(project_root_str)
    memory_context_file: str | None = None
    final_question = question
    if memory_text and question is not None:
        # One-shot: prepend memory to the question so cursor receives
        # one combined positional argument.
        final_question = f"{memory_text}\n\n---\n\n{question}"
    elif memory_text and question is None:
        # Interactive: write memory to a temp file; surface the path.
        memory_context_file = _write_memory_context_file(
            project_root_str, memory_text
        )

    pre_dirty = set(_dirty_paths(project_root_str))
    args = build_cursor_args(binary, final_question)
    exit_code = runner(args, project_root_str)
    post_dirty = _dirty_paths(project_root_str)
    new_dirty = tuple(
        p for p in post_dirty
        if p not in pre_dirty
        # The memory_context_file is our own write; don't report it as
        # cursor-caused dirtiness. .ai-cockpit/history/* is already on
        # the row #10 follow-up dirty-tree allow-list.
        and (memory_context_file is None or not p.endswith(Path(memory_context_file).name))
    )

    return ChatSpawnResult(
        exit_code=exit_code,
        cursor_binary=binary,
        system_prompt_bytes=len(memory_text),
        truncated_files=truncated,
        dirty_paths_on_exit=new_dirty,
        memory_context_file=memory_context_file,
    )
