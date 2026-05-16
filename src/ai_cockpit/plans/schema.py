"""Pydantic schema for B.6 plan artifacts (``docs/plans/*.plan.yaml``).

Canonical source of truth for the shape defined in
``docs/B_6_CONTRACT.md`` §4. Every "Validation rules" bullet maps to a
single validator below; violations raise :class:`PlanSchemaError` and
never produce a partial object.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

if TYPE_CHECKING:
    from ai_cockpit.planner_interactive.types import PlanDraft

_SLUG_PATTERN = r"^[a-z0-9-]+$"
_SLUG_MAX = 48

Slug = Annotated[
    str,
    StringConstraints(pattern=_SLUG_PATTERN, min_length=1, max_length=_SLUG_MAX),
]


class PlanSchemaError(ValueError):
    """Raised when a plan dict cannot be parsed into a valid :class:`Plan`."""


class Slice(BaseModel):
    """One executable slice as defined in B.6 §4."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Slug
    depends_on: list[Slug] = Field(default_factory=list)
    title: str = Field(min_length=1)
    why: str = Field(min_length=1)
    scope_must: list[str] = Field(min_length=1)
    scope_out: list[str] = Field(min_length=1)
    dod: list[str] = Field(min_length=1)
    files_budget: int = Field(ge=1, le=8)
    loc_budget: int = Field(ge=1, le=400)
    test_commands: list[str] = Field(default_factory=list)


class Plan(BaseModel):
    """B.6-compatible plan artifact persisted under ``docs/plans/``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1)
    plan_id: Slug
    created_at: str
    idea: str = Field(min_length=1)
    acceptance_criteria: list[str] = Field(min_length=1, max_length=10)
    slices: list[Slice] = Field(min_length=1)

    @field_validator("schema_version")
    @classmethod
    def _check_schema_version(cls, value: int) -> int:
        if value != 1:
            raise ValueError("schema_version must equal 1")
        return value

    @field_validator("created_at")
    @classmethod
    def _check_created_at(cls, value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"created_at is not ISO-8601: {value!r}") from exc
        if parsed.tzinfo is None:
            raise ValueError("created_at must include timezone information")
        return value

    @model_validator(mode="after")
    def _check_slice_topology(self) -> Plan:
        seen: set[str] = set()
        for plan_slice in self.slices:
            if plan_slice.id in seen:
                raise ValueError(f"duplicate slice id: {plan_slice.id}")
            forward = [dep for dep in plan_slice.depends_on if dep not in seen]
            if forward:
                raise ValueError(
                    f"slice {plan_slice.id} depends on later/unknown slice(s): "
                    + ", ".join(forward)
                )
            seen.add(plan_slice.id)
        return self


def parse_plan(payload: dict[str, Any]) -> Plan:
    """Parse a raw dict into a :class:`Plan` or raise :class:`PlanSchemaError`."""
    try:
        return Plan.model_validate(payload)
    except ValidationError as exc:
        raise PlanSchemaError(str(exc)) from exc


def from_planner_draft(draft: PlanDraft, *, max_slices: int | None = None) -> Plan:
    """Adapt a B.9 ``PlanDraft`` into a canonical :class:`Plan`."""
    draft.validate(max_slices=max_slices)
    return parse_plan(draft.to_dict())


_SLUGIFY_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Best-effort filename-safe slug for derived plan ids."""
    collapsed = _SLUGIFY_NON_ALNUM.sub("-", text.lower()).strip("-")
    return collapsed[:_SLUG_MAX].strip("-")
