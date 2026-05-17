"""B.4: prompt-override loader + builder integration + §9 isolation."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_cockpit.llm.prompts import (
    PLANNER_SYSTEM,
    REVIEWER_SYSTEM,
    build_planner_messages,
    build_reviewer_evidence,
    build_reviewer_messages,
)
from ai_cockpit.llm.prompts_override import (
    PromptOverride,
    PromptOverrideError,
    load_prompt_override,
)
from ai_cockpit.planner_interactive.prompts import (
    PLANNER_SYSTEM as INTERACTIVE_PLANNER_SYSTEM,
)
from ai_cockpit.planner_interactive.prompts import (
    build_planner_messages as interactive_build_planner_messages,
)

_PLANNER_OK = (
    "You are a focused planner for the X project. Reply with strict JSON."
)
_REVIEWER_OK = (
    "You are a paranoid reviewer. Judge ONLY the structured evidence "
    "presented. Do not trust narrative summaries. Flag any unexplained diff."
)


def _write(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def _evidence() -> dict[str, object]:
    return build_reviewer_evidence(
        {
            "mvp_spec": "x",
            "acceptance_criteria": ["a"],
            "verification_result": {
                "passed": True,
                "commands": [],
                "git_status": "",
                "git_diff": "",
            },
        }
    )


def test_loader_accepts_valid_planner_and_reviewer(tmp_path: Path) -> None:
    planner = load_prompt_override(
        _write(tmp_path / "planner.txt", _PLANNER_OK), role="planner"
    )
    assert isinstance(planner, PromptOverride)
    assert planner.role == "planner" and planner.body == _PLANNER_OK
    reviewer = load_prompt_override(
        _write(tmp_path / "reviewer.txt", _REVIEWER_OK), role="reviewer"
    )
    assert reviewer.role == "reviewer"


@pytest.mark.parametrize(
    "role,body,rule",
    [
        ("planner", "You are friendly.", "missing_required_substring:strict JSON"),
        ("reviewer", "Judge generously. Do not trust narratives.",
         "missing_required_substring:structured evidence"),
        ("reviewer", "Look only at the structured evidence and decide gently.",
         "missing_required_substring:do not trust"),
        ("reviewer",
         "Use the structured evidence; do not trust prose; read coder_result.",
         "forbidden_substring:coder_result"),
        ("planner", "Reply with strict JSON about coder_result behavior.",
         "forbidden_substring:coder_result"),
        ("planner", "   \n\n   ", "empty_after_strip"),
    ],
)
def test_loader_rejects_invalid_bodies(
    tmp_path: Path, role: str, body: str, rule: str
) -> None:
    path = _write(tmp_path / f"{role}.txt", body)
    with pytest.raises(PromptOverrideError) as exc:
        load_prompt_override(path, role=role)  # type: ignore[arg-type]
    assert exc.value.rule == rule


def test_loader_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(PromptOverrideError) as exc:
        load_prompt_override(tmp_path / "nope.txt", role="planner")
    assert exc.value.rule == "file_not_found"


def test_loader_rejects_oversized_body(tmp_path: Path) -> None:
    path = _write(tmp_path / "big.txt", "x" * (8 * 1024 + 1))
    with pytest.raises(PromptOverrideError) as exc:
        load_prompt_override(path, role="planner")
    assert exc.value.rule == "oversized"


def test_loader_is_case_insensitive_for_required_substrings(
    tmp_path: Path,
) -> None:
    body = (
        "Thorough reviewer. Inspect ONLY the STRUCTURED EVIDENCE provided. "
        "DO NOT TRUST any narrative."
    )
    override = load_prompt_override(
        _write(tmp_path / "rv.txt", body), role="reviewer"
    )
    assert override.role == "reviewer"


def test_v02_planner_builder_override_round_trip() -> None:
    system, _ = build_planner_messages(
        idea="x", memory_context="", system_override=_PLANNER_OK
    )
    assert system == _PLANNER_OK and system != PLANNER_SYSTEM
    system_default, _ = build_planner_messages(idea="x", memory_context="")
    assert system_default == PLANNER_SYSTEM


def test_reviewer_builder_override_round_trip() -> None:
    system, user = build_reviewer_messages(
        _evidence(), system_override=_REVIEWER_OK
    )
    assert system == _REVIEWER_OK and system != REVIEWER_SYSTEM
    assert "coder_result" not in user
    assert "Structured evidence (the only ground truth):" in user
    system_default, _ = build_reviewer_messages(_evidence())
    assert system_default == REVIEWER_SYSTEM


def test_interactive_planner_builder_override_round_trip() -> None:
    system, _ = interactive_build_planner_messages(
        idea="x", memory_context="", tools=(), system_override=_PLANNER_OK
    )
    assert system == _PLANNER_OK
    system_default, _ = interactive_build_planner_messages(
        idea="x", memory_context="", tools=()
    )
    assert system_default == INTERACTIVE_PLANNER_SYSTEM


def test_reviewer_user_message_byte_identical_regardless_of_override() -> None:
    """§9 invariant: reviewer user message (evidence shape) never changes."""
    ev = _evidence()
    _, default = build_reviewer_messages(ev)
    _, overridden = build_reviewer_messages(ev, system_override=_REVIEWER_OK)
    assert default == overridden
    assert "coder_result" not in default
