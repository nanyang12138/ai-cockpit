"""Git-log dependency scanner for B.6 ``plans run`` (contract §5.2).

A slice's ``depends_on`` ids are validated by scanning ``git log`` for
trailing markers ``[<plan_id>/<dep_id>]``. Git log is the sole source
of truth — never trust the plan YAML or any cached state.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from ai_cockpit.tools.shell import run_command


class DependencyError(RuntimeError):
    """Raised when one or more required dep markers are absent from git log."""


_MARKER_TEMPLATE = "[{plan_id}/{slice_id}] from docs/plans/{plan_id}.plan.yaml"


def make_commit_marker(plan_id: str, slice_id: str) -> str:
    """Canonical trailing marker; identical bytes for write and lookup."""
    return _MARKER_TEMPLATE.format(plan_id=plan_id, slice_id=slice_id)


def find_plan_markers(project_root: Path | str, plan_id: str) -> set[str]:
    """Slice ids whose marker appears in ``git log``; empty on git failure."""
    result = run_command("git log --pretty=format:%B", cwd=project_root)
    if result["exit_code"] != 0:
        return set()
    pattern = re.compile(rf"\[{re.escape(plan_id)}/([a-z0-9-]+)\]")
    return set(pattern.findall(result["stdout"] or ""))


def check_dependencies(
    project_root: Path | str, plan_id: str, depends_on: Iterable[str],
) -> None:
    """Raise :class:`DependencyError` naming every unmerged dep."""
    deps = list(depends_on)
    if not deps:
        return
    found = find_plan_markers(project_root, plan_id)
    missing = [dep for dep in deps if dep not in found]
    if missing:
        raise DependencyError(
            f"plan {plan_id!r}: missing dep marker(s) in git log: "
            + ", ".join(missing)
            + " (each dep must be merged before its dependents can run)"
        )


__all__ = [
    "DependencyError",
    "check_dependencies",
    "find_plan_markers",
    "make_commit_marker",
]
