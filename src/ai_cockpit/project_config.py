"""Project-level CLI flag defaults (v0.5 row #10 sub-gate a-1).

Loads ``.ai-cockpit/config.yaml`` (+ optional ``config.local.yaml``)
and exposes a ``ProjectConfig`` dataclass that the CLI back-fills
DEFAULT-source flags from. Precedence: CLI > workflow YAML > local >
project > built-in. Contract:
``docs/V0_5_ROW_10_CLI_ERGONOMICS_CONTRACT.md`` (LOCKED).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = ".ai-cockpit"
CONFIG_FILENAME = "config.yaml"
LOCAL_CONFIG_FILENAME = "config.local.yaml"

# {key: (expected_type, allowed_choices or None)} — single source of truth.
_SCHEMA: dict[str, tuple[type, tuple[str, ...] | None]] = {
    "llm": (str, ("none", "auto", "anthropic", "openai")),
    "worker": (str, ("stub", "aider", "cursor")),
    "apply": (bool, None),
    "workflow": (str, None),
    "max_loops": (int, None),
    "mode": (str, ("exploration", "task")),
    "reviewer": (str, ("builtin", "cursor")),
    "backend": (str, ("builtin", "cursor")),
    "suggest": (bool, None),
    "allow_dirty_tree": (bool, None),
}

# Q5 hard-rule: any key with these prefixes anywhere in the document
# triggers ProjectConfigError. Credentials belong in env vars only.
_CREDENTIAL_PREFIXES: tuple[str, ...] = ("LLM_", "ANTHROPIC_", "OPENAI_")

# §4.1 rejected ``defaults:`` keys (per-run / debug knobs or workflow YAML).
_REJECTED: frozenset[str] = frozenset(
    {
        "thread_id",
        "thread_id_template",
        "root",
        "test_command",
        "test_commands",
        "checkpoint_db",
        "dry_run",
    }
)


class ProjectConfigError(ValueError):
    """Fatal config error (Q5 credential leak). Other problems degrade."""


@dataclass(frozen=True)
class ProjectConfig:
    """Resolved CLI flag defaults. ``None`` = no opinion; fall through."""

    llm: str | None = None
    worker: str | None = None
    apply: bool | None = None
    workflow: str | None = None
    max_loops: int | None = None
    mode: str | None = None
    reviewer: str | None = None
    backend: str | None = None
    suggest: bool | None = None
    allow_dirty_tree: bool | None = None
    sources: tuple[tuple[str, str], ...] = ()  # (key, "P"|"L") pairs
    project_path: str | None = None
    local_path: str | None = None

    @property
    def is_empty(self) -> bool:
        return not self.sources

    def source_of(self, key: str) -> str | None:
        return next((src for k, src in self.sources if k == key), None)


def _project_path(project_root: str | Path) -> Path:
    return Path(project_root) / CONFIG_DIR / CONFIG_FILENAME


def _local_path(project_root: str | Path) -> Path:
    return Path(project_root) / CONFIG_DIR / LOCAL_CONFIG_FILENAME


def resolve_workflow_value(value: str, project_root: str | Path) -> str:
    """Q8: ``bug-fix`` -> ``<root>/.ai-cockpit/workflows/bug-fix.yaml``."""

    if "/" in value or value.endswith((".yaml", ".yml")):
        return value
    return str(Path(project_root) / CONFIG_DIR / "workflows" / f"{value}.yaml")


def _scan_for_credentials(node: Any, trail: str = "") -> None:
    """Walk the YAML tree; raise on any credential-prefix key (Q5)."""
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(k, str) and k.startswith(_CREDENTIAL_PREFIXES):
                where = f"{trail}.{k}".lstrip(".")
                raise ProjectConfigError(
                    f"credential-like key '{where}' is not allowed in "
                    f"{CONFIG_FILENAME}; LLM credentials must come from "
                    "environment variables (LLM_API_KEY / "
                    "ANTHROPIC_API_KEY / OPENAI_API_KEY)."
                )
            _scan_for_credentials(v, f"{trail}.{k}")
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _scan_for_credentials(item, f"{trail}[{i}]")


def _validate_defaults(raw: Any) -> dict[str, Any]:
    """Validate a ``defaults:`` mapping; return the cleaned subset."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("'defaults:' must be a mapping")
    bad = set(raw) & _REJECTED
    if bad:
        raise ValueError(
            f"'defaults:' keys not allowed in v0.5 row #10: {sorted(bad)}"
        )
    unknown = set(raw) - set(_SCHEMA) - _REJECTED
    if unknown:
        raise ValueError(
            f"unknown 'defaults:' keys: {sorted(unknown)}; "
            f"allowed: {sorted(_SCHEMA)}"
        )
    cleaned: dict[str, Any] = {}
    for key, (expected_type, choices) in _SCHEMA.items():
        if key not in raw:
            continue
        value = raw[key]
        # bool inherits from int in Python; reject the wrong one explicitly.
        if expected_type is bool and not isinstance(value, bool):
            raise ValueError(f"'defaults.{key}' must be a boolean, got {value!r}")
        if expected_type is int and (
            isinstance(value, bool) or not isinstance(value, int)
        ):
            raise ValueError(f"'defaults.{key}' must be an integer, got {value!r}")
        if expected_type is str and not isinstance(value, str):
            raise ValueError(f"'defaults.{key}' must be a string, got {value!r}")
        if choices is not None and value not in choices:
            raise ValueError(
                f"'defaults.{key}' must be one of {list(choices)}, got {value!r}"
            )
        if key == "max_loops" and not (0 <= value <= 10):
            raise ValueError(f"'defaults.max_loops' must be in 0..10, got {value}")
        cleaned[key] = value
    return cleaned


def _parse_one(path: Path) -> dict[str, Any] | None:
    """Read + parse + credential-scan one file. None if absent."""
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"could not parse {path}: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top-level must be a YAML mapping")
    _scan_for_credentials(data)
    sv = data.get("schema_version")
    if sv not in (None, 1):
        raise ValueError(f"{path}: schema_version must be 1 (got {sv!r})")
    return data


def load_project_config(project_root: str | Path) -> ProjectConfig:
    """Load + merge project and local configs. Soft-fails on bad schema."""
    p_path = _project_path(project_root)
    l_path = _local_path(project_root)
    merged: dict[str, Any] = {}
    sources: list[tuple[str, str]] = []

    def _absorb(path: Path, marker: str) -> bool:
        nonlocal sources
        try:
            raw = _parse_one(path)
        except ProjectConfigError:
            raise
        except ValueError as exc:
            print(f"error: {exc}; using built-in defaults", file=sys.stderr)
            return False
        if raw is None:
            return False
        try:
            cleaned = _validate_defaults(raw.get("defaults"))
        except ValueError as exc:
            print(f"error: {path}: {exc}; using built-in defaults", file=sys.stderr)
            return False
        for key, value in cleaned.items():
            merged[key] = value
            sources = [s for s in sources if s[0] != key]
            sources.append((key, marker))
        return True

    p_loaded = _absorb(p_path, "P")
    l_loaded = _absorb(l_path, "L")
    if p_loaded or l_loaded:
        parts = [str(p) for p, ok in [(p_path, p_loaded), (l_path, l_loaded)] if ok]
        print(f"info: loaded defaults from {' + '.join(parts)}", file=sys.stderr)

    kw = {f.name: merged.get(f.name) for f in fields(ProjectConfig) if f.name in _SCHEMA}
    return ProjectConfig(
        sources=tuple(sources),
        project_path=str(p_path) if p_loaded else None,
        local_path=str(l_path) if l_loaded else None,
        **kw,
    )


def emit_apply_warning_if_needed(
    resolved_apply: bool, *, source: str | None
) -> None:
    """Q6: warn when ``apply=true`` came from the committed config, not CLI."""

    if resolved_apply and source in ("P", "L"):
        print(
            "warning: project config sets apply=true; every aider/cursor "
            "run will modify files by default. Pass --no-apply or remove "
            "from config to invert.",
            file=sys.stderr,
        )
