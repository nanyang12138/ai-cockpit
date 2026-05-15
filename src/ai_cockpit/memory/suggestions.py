"""Memory auto-update suggestions (v0.2 step 5; spec §7).

The system *proposes* edits to ``.ai-cockpit/memory/*.md`` after a run by
serializing a JSON blob under ``.ai-cockpit/suggestions/<id>.json``. Memory
files are never auto-edited (hard rule §3.2). A human runs
``ai-cockpit memory accept <id>`` to actually apply the change, after which
the suggestion JSON moves into ``.ai-cockpit/suggestions/applied/``.

Synthesis is deliberately conservative and rule-based for now;
LLM-augmented suggestions are deferred to a later step.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_cockpit.memory.loader import MEMORY_FILES, memory_dir
from ai_cockpit.state import TaskState

ALLOWED_TARGETS: tuple[str, ...] = MEMORY_FILES
ALLOWED_OPERATIONS: tuple[str, ...] = ("append",)
_REQUIRED_KEYS: tuple[str, ...] = (
    "id", "created_at", "target", "operation", "content", "rationale",
)
_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class SuggestionError(Exception):
    """Invalid suggestion blob, missing file, or unsupported operation."""


@dataclass(frozen=True)
class Suggestion:
    id: str
    created_at: str
    target: str
    operation: str
    content: str
    rationale: str

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, blob: dict[str, Any]) -> Suggestion:
        missing = [k for k in _REQUIRED_KEYS if k not in blob]
        if missing:
            raise SuggestionError(f"missing keys in suggestion: {missing}")
        s = cls(**{k: blob[k] for k in _REQUIRED_KEYS})
        s.validate()
        return s

    def validate(self) -> None:
        if not isinstance(self.id, str) or not _ID_RE.match(self.id):
            raise SuggestionError(f"invalid suggestion id: {self.id!r}")
        if self.target not in ALLOWED_TARGETS:
            raise SuggestionError(
                f"target {self.target!r} not in allowed memory files {ALLOWED_TARGETS}"
            )
        if self.operation not in ALLOWED_OPERATIONS:
            raise SuggestionError(
                f"operation {self.operation!r} not supported "
                f"(allowed: {ALLOWED_OPERATIONS})"
            )
        if not isinstance(self.content, str) or not self.content.strip():
            raise SuggestionError("suggestion content is empty")


def suggestions_dir(project_root: Path | str) -> Path:
    return Path(project_root) / ".ai-cockpit" / "suggestions"


def applied_dir(project_root: Path | str) -> Path:
    return suggestions_dir(project_root) / "applied"


def _slugify(text: str, max_len: int = 24) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text.strip().lower())[:max_len]
    return slug.strip("-") or "run"


def build_suggestion_from_state(
    state: TaskState, *, when: datetime | None = None,
) -> Suggestion | None:
    """Synthesize a project-memory suggestion from a finished run, or None.

    v0.3 micro-step: skip writes that carry no information. Concretely:
    when ``decision == 'ask_human'`` AND the verifier captured an empty
    ``git_diff``, the run produced no actionable knowledge — it's a
    coder no-op the reviewer correctly rejected, and recording it in
    project.md would only add noise on future ``ai-cockpit memory list``
    output. Successful runs (``decision == 'done'``) are always kept,
    and ``ask_human`` runs that DID produce a diff (the reviewer
    rejected a real change) are kept because that escalation context
    is worth remembering. Observed during the §15.1 real-LLM
    validation on 2026-05-15: the stub-worker / coder-noop runs were
    pure noise; the aider-made-real-changes-but-lint-unverified run
    is the kind we want to keep.
    """

    decision = state.get("decision")
    idea = (state.get("idea") or state.get("user_input") or "").strip()
    spec = (state.get("mvp_spec") or "").strip()
    if not idea or not spec or decision not in ("done", "ask_human"):
        return None

    if decision == "ask_human":
        verification: object = state.get("verification_result") or {}
        if isinstance(verification, dict):
            diff = str(verification.get("git_diff") or "").strip()
        else:
            diff = ""
        if not diff:
            return None

    when = when or datetime.now(UTC)
    sid = when.strftime("%Y%m%dT%H%M%S") + f"-{decision}-{_slugify(idea)}"
    spec_first = spec.splitlines()[0].strip() or "(no spec line)"
    body = (
        f"## {when.date().isoformat()} — {idea}\n\n"
        f"- decision: {decision}\n"
        f"- mvp_spec: {spec_first}\n"
    )
    return Suggestion(
        id=sid,
        created_at=when.isoformat(timespec="seconds"),
        target="project.md",
        operation="append",
        content=body,
        rationale=f"auto-generated from run; decision={decision}",
    )


def write_suggestion(project_root: Path | str, suggestion: Suggestion) -> Path:
    suggestion.validate()
    base = suggestions_dir(project_root)
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{suggestion.id}.json"
    if path.exists():
        raise SuggestionError(f"suggestion already exists: {path}")
    path.write_text(json.dumps(suggestion.to_json(), indent=2) + "\n", encoding="utf-8")
    return path


def list_suggestions(project_root: Path | str) -> list[Suggestion]:
    base = suggestions_dir(project_root)
    if not base.is_dir():
        return []
    out: list[Suggestion] = []
    for path in sorted(base.glob("*.json")):
        try:
            out.append(Suggestion.from_json(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError, SuggestionError):
            continue
    return out


def load_suggestion(project_root: Path | str, suggestion_id: str) -> Suggestion:
    if not _ID_RE.match(suggestion_id):
        raise SuggestionError(f"invalid suggestion id: {suggestion_id!r}")
    path = suggestions_dir(project_root) / f"{suggestion_id}.json"
    if not path.is_file():
        raise SuggestionError(f"suggestion not found: {suggestion_id}")
    return Suggestion.from_json(json.loads(path.read_text(encoding="utf-8")))


def accept_suggestion(project_root: Path | str, suggestion_id: str) -> Path:
    """Apply a pending suggestion to its target memory file and archive it."""

    s = load_suggestion(project_root, suggestion_id)
    target = memory_dir(project_root) / s.target
    target.parent.mkdir(parents=True, exist_ok=True)
    if s.operation != "append":
        raise SuggestionError(f"unsupported operation: {s.operation}")

    existing = target.read_text(encoding="utf-8") if target.is_file() else ""
    if not existing:
        new_text = s.content
    elif existing.endswith("\n\n"):
        new_text = existing + s.content
    elif existing.endswith("\n"):
        new_text = existing + "\n" + s.content
    else:
        new_text = existing + "\n\n" + s.content
    target.write_text(new_text, encoding="utf-8")

    applied_dir(project_root).mkdir(parents=True, exist_ok=True)
    src = suggestions_dir(project_root) / f"{suggestion_id}.json"
    src.rename(applied_dir(project_root) / f"{suggestion_id}.json")
    return target


def generate_and_write(
    project_root: Path | str, state: TaskState
) -> Suggestion | None:
    """Build + persist a suggestion for ``state``; returns None if skipped."""

    suggestion = build_suggestion_from_state(state)
    if suggestion is None:
        return None
    write_suggestion(project_root, suggestion)
    return suggestion
