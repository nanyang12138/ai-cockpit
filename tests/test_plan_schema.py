"""Validation, round-trip, and loader coverage for B.6 plan artifacts."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from ai_cockpit.planner_interactive.types import PlanDraft
from ai_cockpit.plans import (
    Plan,
    PlanFileError,
    PlanSchemaError,
    load_plan,
    plan_path,
    save_plan,
)
from ai_cockpit.plans.schema import from_planner_draft, parse_plan, slugify


def _base() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "plan_id": "demo-plan",
        "created_at": "2026-05-16T12:00:00+00:00",
        "idea": "Decompose a complex idea into reviewable slices.",
        "acceptance_criteria": ["The plan covers every documented invariant."],
        "slices": [
            {
                "id": "slice-1",
                "depends_on": [],
                "title": "First slice",
                "why": "Anchor the demonstration plan.",
                "scope_must": ["Do the first measurable thing."],
                "scope_out": ["Do not modify unrelated modules."],
                "dod": ["Tests cover the new behavior."],
                "files_budget": 4,
                "loc_budget": 200,
                "test_commands": ["pytest -q"],
            },
            {
                "id": "slice-2",
                "depends_on": ["slice-1"],
                "title": "Second slice",
                "why": "Builds on the first slice.",
                "scope_must": ["Extend behavior introduced by slice-1."],
                "scope_out": ["No daemon, no UI, no cloud."],
                "dod": ["Anti-deception test still green."],
                "files_budget": 3,
                "loc_budget": 150,
                "test_commands": [],
            },
        ],
    }


def _top(**over: Any) -> dict[str, Any]:
    payload = _base()
    payload.update(over)
    return payload


def _slc(idx: int, **fields: Any) -> dict[str, Any]:
    payload = _base()
    payload["slices"][idx] = {**payload["slices"][idx], **fields}
    return payload


def test_happy_path_parses() -> None:
    plan = parse_plan(_base())
    assert plan.plan_id == "demo-plan"
    assert [s.id for s in plan.slices] == ["slice-1", "slice-2"]
    assert plan.slices[1].depends_on == ["slice-1"]


@pytest.mark.parametrize(
    "payload",
    [
        _top(schema_version=2),
        _top(plan_id=""),
        _top(plan_id="Bad_Id"),
        _top(plan_id="with space"),
        _top(plan_id="UPPER"),
        _top(plan_id="x" * 49),
        _top(acceptance_criteria=[]),
        _top(slices=[]),
        _top(created_at="2026-05-16T12:00:00"),
        _top(created_at="yesterday afternoon"),
        _top(sneaky_field="should be rejected"),
        _slc(0, files_budget=0),
        _slc(0, files_budget=9),
        _slc(0, loc_budget=0),
        _slc(0, loc_budget=401),
        _slc(0, scope_out=[]),
        _slc(0, depends_on=["slice-2"]),
        _slc(0, sneaky="should reject"),
    ],
)
def test_rejects_invalid_payloads(payload: dict[str, Any]) -> None:
    with pytest.raises(PlanSchemaError):
        parse_plan(payload)


def test_duplicate_slice_id_rejected() -> None:
    payload = _base()
    payload["slices"].append(deepcopy(payload["slices"][0]))
    with pytest.raises(PlanSchemaError, match="duplicate slice id"):
        parse_plan(payload)


def test_plan_is_frozen() -> None:
    plan = parse_plan(_base())
    with pytest.raises(ValidationError):
        plan.plan_id = "mutated"  # type: ignore[misc]


def test_from_planner_draft_round_trip() -> None:
    draft = PlanDraft.fixture("Refactor the planner pipeline for clarity")
    plan = from_planner_draft(draft)
    assert isinstance(plan, Plan)
    assert plan.plan_id == draft.plan_id
    assert [s.id for s in plan.slices] == [s.id for s in draft.slices]


def test_from_planner_draft_propagates_validation_error() -> None:
    bad = PlanDraft(plan_id="bad", idea="x", acceptance_criteria=[], slices=[])
    with pytest.raises(ValueError):
        from_planner_draft(bad)


def test_slugify_strips_and_truncates() -> None:
    assert slugify("Hello, World!") == "hello-world"
    long_slug = slugify("A " * 100)
    assert len(long_slug) <= 48
    assert long_slug.startswith("a-a-a")
    assert not long_slug.endswith("-")


def test_save_then_load_round_trip(tmp_path: Path) -> None:
    plan = parse_plan(_base())
    path = plan_path(tmp_path, plan.plan_id)
    save_plan(path, plan)
    assert load_plan(path) == plan
    assert [p.name for p in path.parent.iterdir()] == [f"{plan.plan_id}.plan.yaml"]


def test_load_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(PlanFileError, match="not found"):
        load_plan(plan_path(tmp_path, "nope"))


@pytest.mark.parametrize(
    ("body", "match"),
    [
        ("- just\n- a list\n", "must be a mapping"),
        ("plan_id: [unterminated\n", "not valid YAML"),
    ],
)
def test_load_rejects_bad_yaml(tmp_path: Path, body: str, match: str) -> None:
    path = plan_path(tmp_path, "bad")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    with pytest.raises(PlanFileError, match=match):
        load_plan(path)


def test_load_revalidates_hand_edits(tmp_path: Path) -> None:
    plan = parse_plan(_base())
    path = plan_path(tmp_path, plan.plan_id)
    save_plan(path, plan)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw["slices"][0]["files_budget"] = 99
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    with pytest.raises(PlanSchemaError):
        load_plan(path)


def test_plan_path_layout(tmp_path: Path) -> None:
    assert plan_path(tmp_path, "demo") == tmp_path / "docs" / "plans" / "demo.plan.yaml"
