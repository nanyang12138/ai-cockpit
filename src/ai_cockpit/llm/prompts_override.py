"""B.4: ``--planner-system-prompt`` / ``--reviewer-system-prompt`` loader.

Validates the override against a role-scoped allow-list **before any
LLM call** (CLI boundary, not reviewer turn). Rules per
``docs/B_4_CONTRACT.md`` §3: reviewer must contain ``"structured
evidence"`` AND ``"do not trust"``; planner must contain
``"strict JSON"``; neither may contain ``"coder_result"``; both ≤8 KiB
and non-empty after strip; strict UTF-8.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

_MAX_OVERRIDE_BYTES: int = 8 * 1024
_FORBIDDEN_SUBSTRING: str = "coder_result"
_REQUIRED_SUBSTRINGS_BY_ROLE: dict[str, tuple[str, ...]] = {
    "planner": ("strict JSON",),
    "reviewer": ("structured evidence", "do not trust"),
}

Role = Literal["planner", "reviewer"]


class PromptOverrideError(RuntimeError):
    """Raised when an override file fails the allow-list."""

    def __init__(self, *, rule: str, path: Path, detail: str = "") -> None:
        suffix = f": {detail}" if detail else ""
        super().__init__(f"prompt override rejected ({rule}) for {path}{suffix}")
        self.rule = rule
        self.path = path


@dataclass(frozen=True)
class PromptOverride:
    """Validated override body bound to its role + source path."""

    role: Role
    path: Path
    body: str


def _read_text(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except FileNotFoundError as exc:
        raise PromptOverrideError(
            rule="file_not_found", path=path, detail=str(exc)
        ) from exc
    except OSError as exc:
        raise PromptOverrideError(
            rule="file_unreadable", path=path, detail=str(exc)
        ) from exc
    if len(raw) > _MAX_OVERRIDE_BYTES:
        raise PromptOverrideError(
            rule="oversized",
            path=path,
            detail=f"{len(raw)} bytes > {_MAX_OVERRIDE_BYTES} cap",
        )
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PromptOverrideError(
            rule="utf8_decode_failed", path=path, detail=str(exc)
        ) from exc


def _validate(body: str, *, role: Role, path: Path) -> str:
    required = _REQUIRED_SUBSTRINGS_BY_ROLE.get(role)
    if required is None:
        raise PromptOverrideError(
            rule=f"unknown_role:{role}", path=path,
            detail="role must be 'planner' or 'reviewer'",
        )
    stripped = body.rstrip("\n")
    if not stripped.strip():
        raise PromptOverrideError(
            rule="empty_after_strip", path=path,
            detail="override body is whitespace-only",
        )
    lowered = stripped.lower()
    if _FORBIDDEN_SUBSTRING in lowered:
        raise PromptOverrideError(
            rule=f"forbidden_substring:{_FORBIDDEN_SUBSTRING}", path=path,
            detail=f"override mentions {_FORBIDDEN_SUBSTRING!r} (§9 defence)",
        )
    for token in required:
        if token.lower() not in lowered:
            raise PromptOverrideError(
                rule=f"missing_required_substring:{token}", path=path,
                detail=f"{role} override must contain {token!r}",
            )
    return stripped


def load_prompt_override(path: Path, *, role: Role) -> PromptOverride:
    """Read, validate, and return a :class:`PromptOverride`.

    Raises :class:`PromptOverrideError` on any failure. The error's
    ``rule`` field is suitable for one-line CLI output without a
    traceback.
    """
    body = _read_text(path)
    return PromptOverride(role=role, path=path, body=_validate(body, role=role, path=path))


__all__ = ["PromptOverride", "PromptOverrideError", "load_prompt_override"]
