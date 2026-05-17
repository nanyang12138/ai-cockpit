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


def test_catalog_carries_testcmd_path_quirk_on_apply_capable_workers() -> None:
    """Bug B (2026-05-17 v0.4 gate attempt 3): planner emitted
    ``pytest examples/broken_calc -v`` while the verifier cwd was
    already ``examples/broken_calc``, yielding exit 4 "not found".

    The quirk is worker-agnostic in nature (planner-emission convention)
    but it shows up *through* the verifier commands, so apply-capable
    backends (aider, cursor) carry it. ``stub`` does not — it never
    runs verifier test_commands meaningfully.
    """

    quirk_ids = {
        worker: {q.id for q in WORKER_QUIRKS[worker]}
        for worker in ("aider", "cursor", "stub")
    }
    target = "verifier.test_command_path_relative_to_root"
    assert target in quirk_ids["aider"], quirk_ids["aider"]
    assert target in quirk_ids["cursor"], quirk_ids["cursor"]
    assert target not in quirk_ids["stub"], quirk_ids["stub"]


def test_testcmd_path_quirk_text_names_the_failure_mode() -> None:
    """The human_summary must be specific enough that the planner LLM
    actually changes its emission. A vague "use relative paths" is not
    enough; the surfacing event proved the model emitted the project
    root prefix because it sounded right in the slice docstring."""

    for worker in ("aider", "cursor"):
        for q in WORKER_QUIRKS[worker]:
            if q.id == "verifier.test_command_path_relative_to_root":
                summary_lower = q.human_summary.lower()
                assert "cwd" in summary_lower or "project_root" in summary_lower
                assert "pytest" in summary_lower
                return
    raise AssertionError("verifier.test_command_path quirk not found")


def test_testcmd_path_quirk_survives_80_char_clip_with_concrete_example() -> None:
    """Calibration regression from v0.4 gate attempt 4 (2026-05-17):

    The original phrasing in PR #80 was 153 chars long. ``quirks_for()``
    clipped it to 80, which fell exactly **before** the concrete
    ``'pytest -v' not 'pytest examples/<dir> -v'`` pair. The planner
    LLM then saw only the abstract head ("don't prefix paths with
    project_root") and re-emitted the same wrong test_command.

    This test pins that the clipped form the planner actually receives:

    * is <= _HINT_CHAR_BUDGET (would otherwise still clip);
    * contains the literal ``pytest -v`` good form; and
    * contains a recognizable bad form (``examples/`` or ``<dir>``)
      so the LLM sees a concrete pair, not an abstract directive.
    """

    hints = quirks_for("aider")
    matching = [h for h in hints if "pytest -v" in h and "examples" in h]
    assert matching, (
        "expected the test_command quirk's clipped human_summary to retain "
        "both the good form 'pytest -v' AND a recognizable bad form "
        "involving 'examples/'; got: " + repr(hints)
    )
    assert len(matching[0]) <= 80, (
        f"clipped hint exceeded _HINT_CHAR_BUDGET: {matching[0]!r}"
    )
    assert "…" not in matching[0], (
        "clip ellipsis should not appear — hint should fit naturally; "
        "got: " + repr(matching[0])
    )


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
