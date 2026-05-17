"""Tests for B.9c LLM-backed builtin planner + schema save."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from ai_cockpit.llm.prompts import (
    build_reviewer_evidence,
    build_reviewer_messages,
)
from ai_cockpit.planner_interactive.backends import BuiltinPlannerBackend
from ai_cockpit.planner_interactive.prompts import (
    PLANNER_SYSTEM,
    build_planner_messages,
)
from ai_cockpit.planner_interactive.tools import default_tool_registry
from ai_cockpit.planner_interactive.types import PlannerRequest, save_plan_atomic

_VALID_DRAFT: dict[str, object] = {
    "plan_id": "valid-plan",
    "idea": "ship a small feature",
    "acceptance_criteria": ["users can see the feature"],
    "slices": [
        {
            "id": "slice-1",
            "title": "implement the feature",
            "why": "needed to demo the LLM-backed planner end-to-end",
            "scope_must": ["write the minimal code path"],
            "scope_out": ["no UI changes"],
            "dod": ["pytest passes"],
            "files_budget": 3,
            "loc_budget": 150,
            "depends_on": [],
            "test_commands": ["pytest"],
        }
    ],
}


class _ScriptedLLM:
    """Tiny ``LLMProvider`` stand-in used to script planner replies."""

    name = "scripted"

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def complete(self, *, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self._replies.pop(0) if self._replies else ""


def _request(root: Path, *, worker_name: str | None = None) -> PlannerRequest:
    return PlannerRequest(
        idea="ship feature",
        project_root=root,
        memory_context="prior notes",
        output_path=None,
        llm_mode="auto",
        backend="builtin",
        max_slices=None,
        max_turns=12,
        max_tool_bytes=12_000,
        worker_name=worker_name,
    )


def test_prompt_includes_schema_tool_inventory_feedback_and_draft(
    tmp_path: Path,
) -> None:
    tools = default_tool_registry(tmp_path)
    system, user = build_planner_messages(
        idea="add login",
        memory_context="prior notes",
        tools=tools.values(),
        feedback="please add a verifier slice",
        current_draft={"plan_id": "prior", "slices": []},
    )
    assert system == PLANNER_SYSTEM
    for fragment in (
        "add login",
        "prior notes",
        "read_file",
        "ripgrep",
        '"plan_id"',
        '"files_budget"',
        "please add a verifier slice",
        '"plan_id": "prior"',
    ):
        assert fragment in user, fragment


def test_builtin_backend_llm_path_parses_and_validates(tmp_path: Path) -> None:
    backend = BuiltinPlannerBackend(llm_mode="auto")
    llm = _ScriptedLLM([json.dumps(_VALID_DRAFT)])
    backend.bind_llm(llm)
    response = backend.start(_request(tmp_path))
    assert response.draft is not None
    assert response.draft.plan_id == "valid-plan"
    assert response.draft.slices[0].files_budget == 3
    assert "draft updated by LLM" in response.message
    assert len(llm.calls) == 1


def test_builtin_backend_keeps_previous_draft_on_invalid_json(
    tmp_path: Path,
) -> None:
    backend = BuiltinPlannerBackend(llm_mode="auto")
    backend.bind_llm(_ScriptedLLM(["not json at all"]))
    response = backend.start(_request(tmp_path))
    assert response.draft is None
    assert "not valid JSON" in response.message


def test_builtin_backend_rejects_payload_failing_schema(tmp_path: Path) -> None:
    bad_slice = dict(_VALID_DRAFT["slices"][0], files_budget=99)  # type: ignore[index]
    bad_payload = dict(_VALID_DRAFT, slices=[bad_slice])
    backend = BuiltinPlannerBackend(llm_mode="auto")
    backend.bind_llm(_ScriptedLLM([json.dumps(bad_payload)]))
    response = backend.start(_request(tmp_path))
    assert "failed validation" in response.message
    assert response.draft is None


def test_builtin_backend_rejects_missing_plan_id(tmp_path: Path) -> None:
    no_id = {k: v for k, v in _VALID_DRAFT.items() if k != "plan_id"}
    backend = BuiltinPlannerBackend(llm_mode="auto")
    backend.bind_llm(_ScriptedLLM([json.dumps(no_id)]))
    response = backend.start(_request(tmp_path))
    assert "failed validation" in response.message
    assert "plan_id" in response.message


def test_builtin_backend_falls_back_on_llm_exception(tmp_path: Path) -> None:
    class _BoomLLM:
        name = "boom"

        def complete(self, *, system: str, user: str) -> str:
            raise RuntimeError("upstream 502")

    backend = BuiltinPlannerBackend(llm_mode="auto")
    backend.bind_llm(_BoomLLM())
    response = backend.start(_request(tmp_path))
    assert "planner LLM call failed" in response.message
    assert "upstream 502" in response.message
    assert response.draft is None


def test_respond_revises_draft_and_save_writes_yaml(tmp_path: Path) -> None:
    revised = dict(_VALID_DRAFT, plan_id="revised-plan")
    backend = BuiltinPlannerBackend(llm_mode="auto")
    backend.bind_llm(_ScriptedLLM([json.dumps(_VALID_DRAFT), json.dumps(revised)]))
    backend.start(_request(tmp_path))
    backend.respond("rename the plan id")
    draft = backend.draft()
    assert draft is not None and draft.plan_id == "revised-plan"

    out_path = tmp_path / "docs" / "plans" / "revised-plan.plan.yaml"
    save_plan_atomic(out_path, draft, max_slices=None)
    data = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["plan_id"] == "revised-plan"
    assert data["slices"][0]["loc_budget"] == 150


def test_builtin_backend_injects_worker_quirks_when_worker_name_set(
    tmp_path: Path,
) -> None:
    """Bug E regression (2026-05-17 v0.4 gate attempt 6):

    ``ai-cockpit plan --worker aider`` flows ``worker_name="aider"`` into
    ``PlannerRequest`` which the builtin backend MUST forward into
    ``build_planner_messages`` so the user message gains a "Worker quirks
    to design around" block. Without this wiring (prior to PR #82), B.2
    catalog growth was theatrical for the most common interactive
    planning surface — exactly what the 2026-05-17 gate run surfaced
    when no PR #80 / PR #81 hint reached the planner LLM during plan
    REPL.
    """

    backend = BuiltinPlannerBackend(llm_mode="auto")
    llm = _ScriptedLLM([json.dumps(_VALID_DRAFT)])
    backend.bind_llm(llm)
    backend.start(_request(tmp_path, worker_name="aider"))
    assert len(llm.calls) == 1, "scripted LLM must have been called once"
    _system, user = llm.calls[0]
    assert "Worker quirks to design around" in user, (
        "B.2 hint block missing from interactive planner user message; "
        "PlannerRequest.worker_name was not plumbed into "
        "build_planner_messages — Bug E regression."
    )
    assert "current backend: aider" in user
    assert "pytest -v" in user, (
        "PR #81 tightened test_command_path quirk should be visible in "
        "the planner message body when worker_name='aider'."
    )


def test_builtin_backend_no_quirk_block_when_worker_name_omitted(
    tmp_path: Path,
) -> None:
    """Symmetric guard: when the operator does not pass ``--worker``,
    the planner stays B.9 contract-Q1-clean (worker-agnostic, no quirk
    block). Defends against an accidental "always inject aider quirks"
    regression."""

    backend = BuiltinPlannerBackend(llm_mode="auto")
    llm = _ScriptedLLM([json.dumps(_VALID_DRAFT)])
    backend.bind_llm(llm)
    backend.start(_request(tmp_path))  # worker_name defaults to None
    _system, user = llm.calls[0]
    assert "Worker quirks to design around" not in user
    assert "current backend:" not in user


def test_planner_tool_output_does_not_leak_to_reviewer_prompt() -> None:
    """§11 anti-deception: planner conversation/tool output must NOT
    enter the reviewer LLM prompt bytes."""

    sentinel = "PLANNER_TOOL_SECRET_SHOULD_NOT_REACH_REVIEWER"
    state = {
        "mvp_spec": "build feature",
        "acceptance_criteria": ["users see it"],
        "verification_result": {
            "passed": True,
            "git_status": "clean",
            "git_diff": "",
            "commands": [
                {"command": "pytest", "exit_code": 0, "stdout": "ok", "stderr": ""}
            ],
        },
        # Planner-side bookkeeping that must NOT enter the reviewer prompt.
        "planner_transcript": sentinel,
        "planner_tool_outputs": [sentinel],
        "plan_draft": {"idea": sentinel, "slices": []},
    }
    evidence = build_reviewer_evidence(state)
    system, user = build_reviewer_messages(evidence)
    assert sentinel not in (system + "\n" + user)
