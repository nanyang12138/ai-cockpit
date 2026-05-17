"""B.2: planner-side worker-quirk catalog + prompt-shape regression."""

from __future__ import annotations

from ai_cockpit.llm.prompts import (
    PLANNER_SYSTEM as V02_PLANNER_SYSTEM,
)
from ai_cockpit.llm.prompts import (
    build_planner_messages as v02_build_planner_messages,
)
from ai_cockpit.llm.prompts import (
    build_reviewer_evidence,
    build_reviewer_messages,
)
from ai_cockpit.planner_interactive.prompts import (
    PLANNER_SYSTEM as INTERACTIVE_PLANNER_SYSTEM,
)
from ai_cockpit.planner_interactive.prompts import (
    build_planner_messages as interactive_build_planner_messages,
)
from ai_cockpit.workers.quirks import (
    WORKER_QUIRKS,
    WorkerQuirk,
    quirks_for,
)


def test_catalog_has_seed_entries_for_aider_and_cursor() -> None:
    assert "aider" in WORKER_QUIRKS
    assert "cursor" in WORKER_QUIRKS
    assert WORKER_QUIRKS["stub"] == ()
    aider_entry = WORKER_QUIRKS["aider"][0]
    assert isinstance(aider_entry, WorkerQuirk)
    assert aider_entry.id == "aider.gitignore"
    assert "gitignore" in aider_entry.human_summary.lower()


def test_quirks_for_returns_lists_per_worker() -> None:
    assert quirks_for("aider")
    assert quirks_for("AIDER") == quirks_for("aider")
    assert quirks_for("cursor")
    assert quirks_for("stub") == []
    assert quirks_for("openhands") == []
    assert quirks_for("") == []
    assert quirks_for(None) == []


def test_quirks_for_clips_long_human_summaries_to_80_chars() -> None:
    for name in ("aider", "cursor"):
        for hint in quirks_for(name):
            assert len(hint) <= 80, (name, hint)


def test_v02_planner_omits_hint_block_by_default() -> None:
    system, user = v02_build_planner_messages(
        idea="add login", memory_context=""
    )
    assert system == V02_PLANNER_SYSTEM
    assert "Worker quirks" not in user


def test_v02_planner_includes_hint_block_when_hints_supplied() -> None:
    hints = quirks_for("aider")
    system, user = v02_build_planner_messages(
        idea="add login",
        memory_context="",
        worker_hints=hints,
        worker_name="aider",
    )
    assert system == V02_PLANNER_SYSTEM
    assert "Worker quirks to design around" in user
    assert "current backend: aider" in user
    for hint in hints:
        assert hint in user


def test_v02_planner_clips_bullets_to_six_and_eighty_chars() -> None:
    long_hints = ["x" * 200] + [f"hint {i}" for i in range(2, 9)]
    _, user = v02_build_planner_messages(
        idea="x",
        memory_context="",
        worker_hints=long_hints,
        worker_name="aider",
    )
    bullet_lines = [ln for ln in user.splitlines() if ln.startswith("- ")]
    assert len(bullet_lines) == 6
    assert "hint 8" not in user
    for line in bullet_lines:
        assert len(line[2:]) <= 80, line


def test_v02_planner_unspecified_worker_name_renders_label() -> None:
    _, user = v02_build_planner_messages(
        idea="x", memory_context="", worker_hints=["only"], worker_name=None
    )
    assert "current backend: unspecified" in user


def test_interactive_planner_omits_hint_block_by_default() -> None:
    system, user = interactive_build_planner_messages(
        idea="add login", memory_context="", tools=()
    )
    assert system == INTERACTIVE_PLANNER_SYSTEM
    assert "Worker quirks" not in user


def test_interactive_planner_includes_hint_block_when_supplied() -> None:
    hints = quirks_for("cursor")
    _, user = interactive_build_planner_messages(
        idea="add login",
        memory_context="",
        tools=(),
        worker_hints=hints,
        worker_name="cursor",
    )
    assert "Worker quirks to design around" in user
    assert "current backend: cursor" in user
    for hint in hints:
        assert hint in user


def test_reviewer_prompt_never_carries_worker_quirk_substrings() -> None:
    """B.2 §9 boundary: quirks must not leak into the reviewer prompt."""

    evidence = build_reviewer_evidence(
        {
            "mvp_spec": "ship a small feature",
            "acceptance_criteria": ["users can see the feature"],
            "verification_result": {
                "passed": True,
                "commands": [
                    {"command": "pytest", "exit_code": 0, "stdout": "ok", "stderr": ""}
                ],
                "git_status": "",
                "git_diff": "",
            },
        }
    )
    system, user = build_reviewer_messages(evidence)
    full = system + "\n" + user
    for fragment in ("Worker quirks", "current backend:", "workspace scan", "design around"):
        assert fragment not in full, fragment
    assert "worker_hints" not in evidence
