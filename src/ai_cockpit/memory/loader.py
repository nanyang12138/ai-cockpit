"""Load markdown memory files from `.ai-cockpit/memory/`.

v0.1 is read-only: we never write back to memory files. Missing files are
skipped silently rather than raising, so a fresh project still works.
"""

from __future__ import annotations

from pathlib import Path

MEMORY_FILES: tuple[str, ...] = ("user.md", "project.md", "preferences.md")


def memory_dir(project_root: Path | str) -> Path:
    return Path(project_root) / ".ai-cockpit" / "memory"


def load_memory(project_root: Path | str) -> str:
    """Concatenate available memory files into a single context blob.

    Returns an empty string if `.ai-cockpit/memory/` does not exist or
    contains no recognized files.
    """

    base = memory_dir(project_root)
    if not base.is_dir():
        return ""

    chunks: list[str] = []
    for name in MEMORY_FILES:
        path = base / name
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not content:
            continue
        chunks.append(f"## {name}\n\n{content}")

    return "\n\n".join(chunks)
