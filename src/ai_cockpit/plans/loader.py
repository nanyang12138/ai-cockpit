"""Atomic load/save helpers for ``docs/plans/<plan_id>.plan.yaml``.

A hand-edited plan that introduces a schema violation must refuse to
load (B.6 §4); :func:`load_plan` always re-runs :func:`parse_plan`, and
:func:`save_plan` always validates before writing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .schema import Plan, PlanSchemaError, parse_plan


class PlanFileError(OSError):
    """Raised when a plan file is missing, unreadable, or non-mapping YAML."""


def plan_path(project_root: Path, plan_id: str) -> Path:
    """Canonical ``docs/plans/<plan_id>.plan.yaml`` path under ``project_root``."""
    return project_root / "docs" / "plans" / f"{plan_id}.plan.yaml"


def load_plan(path: Path) -> Plan:
    """Read ``path`` and return a validated :class:`Plan`."""
    if not path.is_file():
        raise PlanFileError(f"plan file not found: {path}")
    try:
        payload: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PlanFileError(f"plan file is not valid YAML: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PlanFileError(f"plan file root must be a mapping: {path}")
    return parse_plan(payload)


def save_plan(path: Path, plan: Plan) -> None:
    """Validate ``plan`` and atomically write its YAML to ``path``."""
    payload = plan.model_dump()
    parse_plan(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    tmp_path.replace(path)


__all__ = ["PlanFileError", "PlanSchemaError", "load_plan", "plan_path", "save_plan"]
