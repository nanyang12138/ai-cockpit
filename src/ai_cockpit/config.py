"""Runtime configuration for an AI Cockpit invocation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class CockpitConfig:
    """Immutable per-run configuration assembled from CLI flags."""

    user_input: str
    project_root: Path
    mode: str = "exploration"
    max_loops: int = 1
    test_commands: tuple[str, ...] = field(default_factory=tuple)
    dry_run: bool = False

    def __post_init__(self) -> None:
        if self.mode not in {"exploration", "task"}:
            raise ValueError(f"mode must be 'exploration' or 'task', got {self.mode!r}")
        if self.max_loops < 0:
            raise ValueError("max_loops must be >= 0")
        if not self.user_input.strip():
            raise ValueError("user_input must be non-empty")
