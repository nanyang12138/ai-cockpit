"""Read-only tools exposed to the B.9 interactive planner.

These tools never write, never shell out beyond fixed read-only ``git``
calls, and never touch the network. Output is clipped to ``max_bytes``
so the planner cannot overload context. B.9c will route LLM tool calls
through this registry; B.9b only ships the shape.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ai_cockpit.tools.git import git_status_short as _git_status_short
from ai_cockpit.tools.shell import run_command

DEFAULT_MAX_BYTES = 12_000
DEFAULT_MAX_RESULTS = 100
RIPGREP_MAX_FILES_SCANNED = 200
SKIP_DIR_PARTS = frozenset({".git", "node_modules", ".venv", "__pycache__"})


class PlannerToolError(RuntimeError):
    """Raised when a tool call breaks a safety invariant."""


@dataclass(frozen=True)
class ToolResult:
    output: str
    truncated: bool = False


@dataclass(frozen=True)
class PlannerTool:
    name: str
    description: str
    call: Callable[..., ToolResult]


def _resolve_under_root(root: Path, candidate: str | Path) -> Path:
    root_resolved = root.resolve()
    raw = Path(candidate)
    target = raw if raw.is_absolute() else (root / raw)
    resolved = target.resolve()
    if not resolved.is_relative_to(root_resolved):
        raise PlannerToolError(
            f"path {str(candidate)!r} escapes project root {str(root_resolved)!r}"
        )
    return resolved


def _clip(text: str, *, max_bytes: int) -> ToolResult:
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return ToolResult(output=text)
    head = encoded[:max_bytes].decode("utf-8", errors="replace")
    return ToolResult(output=head + "\n... [clipped]", truncated=True)


def _is_under_skip_dir(path: Path) -> bool:
    return any(part in SKIP_DIR_PARTS for part in path.parts)


def read_file(
    root: Path, path: str | Path, *, max_bytes: int = DEFAULT_MAX_BYTES
) -> ToolResult:
    target = _resolve_under_root(root, path)
    if not target.is_file():
        raise PlannerToolError(f"not a regular file: {str(path)!r}")
    try:
        head = target.read_bytes()[: max_bytes + 1024]
    except OSError as exc:
        raise PlannerToolError(f"could not read {str(path)!r}: {exc}") from exc
    if b"\x00" in head[:8192]:
        raise PlannerToolError(f"binary file refused: {str(path)!r}")
    try:
        text = head.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PlannerToolError(f"non-UTF-8 file refused: {str(path)!r}") from exc
    return _clip(text, max_bytes=max_bytes)


def glob_files(
    root: Path,
    pattern: str,
    *,
    max_results: int = DEFAULT_MAX_RESULTS,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> ToolResult:
    if pattern.startswith("/") or ".." in Path(pattern).parts:
        raise PlannerToolError(f"unsafe glob pattern: {pattern!r}")
    root_resolved = root.resolve()
    matches: list[str] = []
    for entry in sorted(root_resolved.glob(pattern)):
        if not entry.is_relative_to(root_resolved) or _is_under_skip_dir(entry):
            continue
        matches.append(str(entry.relative_to(root_resolved)))
        if len(matches) >= max_results:
            break
    return _clip("\n".join(matches) if matches else "<no matches>", max_bytes=max_bytes)


def ripgrep_search(
    root: Path,
    pattern: str,
    path: str | Path | None = None,
    *,
    max_results: int = DEFAULT_MAX_RESULTS,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> ToolResult:
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        raise PlannerToolError(f"invalid regex {pattern!r}: {exc}") from exc
    scope_root = _resolve_under_root(root, path) if path is not None else root.resolve()
    root_resolved = root.resolve()
    files: list[Path] = (
        [scope_root]
        if scope_root.is_file()
        else [
            f
            for f in sorted(scope_root.rglob("*"))
            if f.is_file() and not _is_under_skip_dir(f)
        ][:RIPGREP_MAX_FILES_SCANNED]
    )
    hits: list[str] = []
    truncated = False
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = f.relative_to(root_resolved) if f.is_relative_to(root_resolved) else f
        for line_num, line in enumerate(text.splitlines(), start=1):
            if compiled.search(line):
                hits.append(f"{rel}:{line_num}:{line}")
                if len(hits) >= max_results:
                    truncated = True
                    break
        if truncated:
            break
    body = "\n".join(hits) if hits else "<no matches>"
    clipped = _clip(body, max_bytes=max_bytes)
    return ToolResult(output=clipped.output, truncated=clipped.truncated or truncated)


def git_status(root: Path, *, max_bytes: int = DEFAULT_MAX_BYTES) -> ToolResult:
    return _clip(_git_status_short(root), max_bytes=max_bytes)


def git_log(
    root: Path, *, limit: int = 20, max_bytes: int = DEFAULT_MAX_BYTES
) -> ToolResult:
    safe_limit = max(1, min(int(limit), 100))
    result = run_command(f"git log --oneline -n {safe_limit}", cwd=root)
    if result["exit_code"] != 0:
        return ToolResult(
            output=(
                f"<git log failed: exit={result['exit_code']}> "
                f"{result['stderr'].strip()}"
            )
        )
    return _clip(result["stdout"], max_bytes=max_bytes)


def read_existing_plans(root: Path, *, max_bytes: int = DEFAULT_MAX_BYTES) -> ToolResult:
    plans_dir = (root / "docs" / "plans").resolve()
    if not plans_dir.is_dir():
        return ToolResult(output="<no docs/plans/ directory yet>")
    root_resolved = root.resolve()
    rows: list[str] = []
    for plan_path in sorted(plans_dir.glob("*.plan.yaml")):
        try:
            size = plan_path.stat().st_size
        except OSError:
            continue
        rows.append(f"{plan_path.relative_to(root_resolved)} ({size} bytes)")
    return _clip("\n".join(rows) if rows else "<no plan files yet>", max_bytes=max_bytes)


_TOOL_DESCRIPTIONS: tuple[tuple[str, str], ...] = (
    ("read_file", "Read a UTF-8 file inside the project root."),
    ("glob", "Match files under the project root by glob pattern."),
    ("ripgrep", "Search files under the project root for a regex."),
    ("git_status", "Show 'git status --short' for the project."),
    ("git_log", "Show recent 'git log --oneline' entries."),
    ("read_existing_plans", "List existing docs/plans/*.plan.yaml files."),
)


def default_tool_registry(
    root: Path, *, max_tool_bytes: int = DEFAULT_MAX_BYTES
) -> dict[str, PlannerTool]:
    """Return the read-only tools available to the B.9 planner."""

    callables: dict[str, Callable[..., ToolResult]] = {
        "read_file": lambda p: read_file(root, p, max_bytes=max_tool_bytes),
        "glob": lambda pattern: glob_files(root, pattern, max_bytes=max_tool_bytes),
        "ripgrep": lambda pattern, path=None: ripgrep_search(
            root, pattern, path=path, max_bytes=max_tool_bytes
        ),
        "git_status": lambda: git_status(root, max_bytes=max_tool_bytes),
        "git_log": lambda limit=20: git_log(root, limit=limit, max_bytes=max_tool_bytes),
        "read_existing_plans": lambda: read_existing_plans(root, max_bytes=max_tool_bytes),
    }
    return {
        name: PlannerTool(name, desc, callables[name])
        for name, desc in _TOOL_DESCRIPTIONS
    }
