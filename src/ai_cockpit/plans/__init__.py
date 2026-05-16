"""Canonical B.6 plan-artifact schema and atomic loader.

Owns the on-disk shape from ``docs/B_6_CONTRACT.md`` §4. The B.9
interactive planner mirrors the same shape in
``ai_cockpit.planner_interactive.types``;
:func:`ai_cockpit.plans.schema.from_planner_draft` adapts that draft into
this module's canonical :class:`Plan` without touching B.9 code.
"""

from .dependencies import (
    DependencyError,
    check_dependencies,
    find_plan_markers,
    make_commit_marker,
)
from .loader import PlanFileError, load_plan, plan_path, save_plan
from .schema import Plan, PlanSchemaError, Slice, from_planner_draft

__all__ = [
    "DependencyError",
    "Plan",
    "PlanFileError",
    "PlanSchemaError",
    "Slice",
    "check_dependencies",
    "find_plan_markers",
    "from_planner_draft",
    "load_plan",
    "make_commit_marker",
    "plan_path",
    "save_plan",
]
