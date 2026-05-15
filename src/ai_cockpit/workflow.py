"""Workflow YAML loader (v0.2 step 4): the YAML now drives the run.

Sources defaults for ``mode`` / ``max_loops`` and per-node config such as
``defaults.verifier.test_commands``; node order must match the compiled
graph or loading fails loudly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CANONICAL_NODE_ORDER: tuple[str, ...] = (
    "intake",
    "planner",
    "coder",
    "verifier",
    "reviewer",
    "decision",
    "summary",
)
ALLOWED_MODES: frozenset[str] = frozenset({"exploration", "task"})


class WorkflowError(ValueError):
    """Raised when a workflow YAML is missing, malformed, or out of sync."""


@dataclass(frozen=True)
class Workflow:
    name: str
    mode: str
    max_loops: int
    node_order: tuple[str, ...]
    defaults: dict[str, dict[str, Any]] = field(default_factory=dict)
    path: Path | None = None

    def verifier_test_commands(self) -> tuple[str, ...]:
        raw = (self.defaults.get("verifier") or {}).get("test_commands") or []
        if not isinstance(raw, list) or any(not isinstance(x, str) for x in raw):
            raise WorkflowError(
                "defaults.verifier.test_commands must be a list of strings"
            )
        return tuple(raw)


def default_workflow_path(project_root: str | Path) -> Path:
    return Path(project_root) / ".ai-cockpit" / "workflows" / "idea-to-mvp.yaml"


def _require_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise WorkflowError(f"workflow field '{key}' must be a non-empty string")
    return value


def _coerce_defaults(data: Any) -> dict[str, dict[str, Any]]:
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise WorkflowError("'defaults' must be a mapping of node-name -> config")
    result: dict[str, dict[str, Any]] = {}
    for name, cfg in data.items():
        if not isinstance(name, str):
            raise WorkflowError("'defaults' keys must be node names (strings)")
        if cfg is None:
            result[name] = {}
        elif isinstance(cfg, dict):
            result[name] = dict(cfg)
        else:
            raise WorkflowError(f"defaults['{name}'] must be a mapping or null")
    return result


def parse_workflow(data: Any, *, path: Path | None = None) -> Workflow:
    """Validate a parsed-YAML mapping and return a ``Workflow``."""

    if not isinstance(data, dict):
        raise WorkflowError("workflow YAML must be a mapping at the top level")

    name = _require_str(data, "name")
    mode = _require_str(data, "mode")
    if mode not in ALLOWED_MODES:
        raise WorkflowError(f"mode must be one of {sorted(ALLOWED_MODES)}, got {mode!r}")

    max_loops = data.get("max_loops")
    if isinstance(max_loops, bool) or not isinstance(max_loops, int) or max_loops < 0:
        raise WorkflowError("workflow field 'max_loops' must be an integer >= 0")

    raw_nodes = data.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise WorkflowError("workflow field 'nodes' must be a non-empty list")
    if any(not isinstance(item, str) for item in raw_nodes):
        raise WorkflowError("each entry in 'nodes' must be a string")
    if tuple(raw_nodes) != CANONICAL_NODE_ORDER:
        raise WorkflowError(
            "workflow nodes are out of sync with the compiled graph. "
            f"Expected {list(CANONICAL_NODE_ORDER)}, got {raw_nodes}. "
            "Update the YAML and the graph together in a single PR."
        )

    defaults = _coerce_defaults(data.get("defaults"))
    unknown = set(defaults) - set(CANONICAL_NODE_ORDER)
    if unknown:
        raise WorkflowError(
            f"defaults references unknown node(s) {sorted(unknown)}. "
            f"Allowed: {list(CANONICAL_NODE_ORDER)}"
        )

    return Workflow(
        name=name,
        mode=mode,
        max_loops=max_loops,
        node_order=tuple(raw_nodes),
        defaults=defaults,
        path=path,
    )


def load_workflow(path: str | Path) -> Workflow:
    """Read ``path`` and return a validated ``Workflow``."""

    yaml_path = Path(path)
    if not yaml_path.is_file():
        raise WorkflowError(f"workflow file not found: {yaml_path}")
    try:
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise WorkflowError(f"invalid YAML in {yaml_path}: {exc}") from exc
    return parse_workflow(data, path=yaml_path)


def load_default_workflow(project_root: str | Path) -> Workflow | None:
    path = default_workflow_path(project_root)
    return load_workflow(path) if path.is_file() else None
