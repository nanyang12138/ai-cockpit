"""Shared types for the interactive planner REPL."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import yaml

_SLUG_RE = re.compile(r"^[a-z0-9-]{1,48}$")


class PlanValidationError(ValueError):
    """Raised when a draft plan is not safe to save."""


@dataclass(frozen=True)
class PlanSlice:
    """One executable slice in a future multi-step plan."""

    id: str
    title: str
    why: str
    scope_must: list[str]
    scope_out: list[str]
    dod: list[str]
    files_budget: int = 8
    loc_budget: int = 400
    depends_on: list[str] = field(default_factory=list)
    test_commands: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "depends_on": self.depends_on,
            "title": self.title,
            "why": self.why,
            "scope_must": self.scope_must,
            "scope_out": self.scope_out,
            "dod": self.dod,
            "files_budget": self.files_budget,
            "loc_budget": self.loc_budget,
            "test_commands": self.test_commands,
        }


@dataclass(frozen=True)
class PlanDraft:
    """In-memory B.6-compatible plan artifact."""

    plan_id: str
    idea: str
    acceptance_criteria: list[str]
    slices: list[PlanSlice]
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds")
    )

    @classmethod
    def fixture(cls, idea: str) -> PlanDraft:
        slug = _slugify(idea) or "interactive-plan"
        return cls(
            plan_id=slug,
            idea=idea,
            acceptance_criteria=["Human reviews and accepts the saved plan."],
            slices=[
                PlanSlice(
                    id="slice-1",
                    title="Review and refine the first implementation slice",
                    why="Deterministic fixture for the B.9a interactive planner shell.",
                    scope_must=["Turn the idea into one small, reviewable next step."],
                    scope_out=["Do not modify source files during planning."],
                    dod=["A valid plan artifact is saved under docs/plans/."],
                    test_commands=[],
                )
            ],
        )

    def validate(self, *, max_slices: int | None = None) -> None:
        if not _SLUG_RE.fullmatch(self.plan_id):
            raise PlanValidationError("plan_id must match ^[a-z0-9-]{1,48}$")
        if not self.acceptance_criteria:
            raise PlanValidationError("acceptance_criteria must not be empty")
        if not self.slices:
            raise PlanValidationError("slices must not be empty")
        if max_slices is not None and len(self.slices) > max_slices:
            raise PlanValidationError(
                f"slices count {len(self.slices)} exceeds --max-slices {max_slices}"
            )
        seen: set[str] = set()
        for plan_slice in self.slices:
            if not _SLUG_RE.fullmatch(plan_slice.id):
                raise PlanValidationError(f"slice id {plan_slice.id!r} is invalid")
            if plan_slice.id in seen:
                raise PlanValidationError(f"duplicate slice id: {plan_slice.id}")
            missing = [dep for dep in plan_slice.depends_on if dep not in seen]
            if missing:
                raise PlanValidationError(
                    f"slice {plan_slice.id} depends on unknown or later slice(s): "
                    + ", ".join(missing)
                )
            if not plan_slice.scope_out:
                raise PlanValidationError(f"slice {plan_slice.id} scope_out is required")
            if not 1 <= plan_slice.files_budget <= 8:
                raise PlanValidationError(
                    f"slice {plan_slice.id} files_budget must be in [1, 8]"
                )
            if not 1 <= plan_slice.loc_budget <= 400:
                raise PlanValidationError(
                    f"slice {plan_slice.id} loc_budget must be in [1, 400]"
                )
            seen.add(plan_slice.id)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "plan_id": self.plan_id,
            "created_at": self.created_at,
            "idea": self.idea,
            "acceptance_criteria": self.acceptance_criteria,
            "slices": [plan_slice.to_dict() for plan_slice in self.slices],
        }

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.to_dict(), sort_keys=False, allow_unicode=True)


@dataclass(frozen=True)
class PlannerRequest:
    """Initial request passed from the CLI into the planner REPL.

    ``worker_name`` (Bug E fix, 2026-05-17 v0.4 gate attempt 6): the
    intended downstream apply-capable worker (typically ``aider`` or
    ``cursor``). When non-empty the builtin backend forwards
    ``quirks_for(worker_name)`` into ``build_planner_messages`` so
    the planner LLM sees B.2 hint bullets. ``None`` keeps the
    pre-B.2 message shape — backward-compatible with B.9 contract
    Q1 ("interactive planner does not know which worker by default").
    """

    idea: str
    project_root: Path
    memory_context: str
    output_path: Path | None
    llm_mode: str
    backend: str
    max_slices: int | None
    max_turns: int
    max_tool_bytes: int
    worker_name: str | None = None


@dataclass(frozen=True)
class PlannerResponse:
    """Text plus optional draft returned by a planner backend."""

    message: str
    draft: PlanDraft | None = None


class PlannerBackend(Protocol):
    """Minimal interface for future builtin/Cursor planner backends."""

    name: str

    def start(self, request: PlannerRequest) -> PlannerResponse:
        """Start a planning session."""
        ...

    def respond(self, text: str) -> PlannerResponse:
        """Respond to one user turn."""
        ...

    def draft(self) -> PlanDraft | None:
        """Return the current draft, if available."""
        ...


def default_plan_path(project_root: Path, draft: PlanDraft) -> Path:
    return project_root / "docs" / "plans" / f"{draft.plan_id}.plan.yaml"


def save_plan_atomic(path: Path, draft: PlanDraft, *, max_slices: int | None) -> None:
    draft.validate(max_slices=max_slices)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(draft.to_yaml(), encoding="utf-8")
    tmp_path.replace(path)


def _slugify(text: str) -> str:
    lowered = text.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    slug = re.sub(r"-+", "-", slug)
    return slug[:48].strip("-")
