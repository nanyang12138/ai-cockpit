"""``ai-cockpit`` command-line entry point."""

from __future__ import annotations

from pathlib import Path

import click

from ai_cockpit.graph import run_graph


@click.command(
    name="ai-cockpit",
    help="Run the AI Cockpit v0.1 idea-to-MVP execution loop on an idea.",
)
@click.argument("idea", nargs=-1, required=True)
@click.option(
    "--root",
    "root",
    default=".",
    show_default=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    help="Project root in which git/test commands run.",
)
@click.option(
    "--max-loops",
    "max_loops",
    default=1,
    show_default=True,
    type=click.IntRange(min=0, max=10),
    help="Maximum number of retry loops (hard cap to prevent runaways).",
)
@click.option(
    "--mode",
    "mode",
    default="exploration",
    show_default=True,
    type=click.Choice(["exploration", "task"], case_sensitive=False),
    help="Workflow mode.",
)
@click.option(
    "--test-command",
    "test_commands",
    multiple=True,
    help="Shell command to run as a verification check. Repeatable.",
)
@click.option(
    "--dry-run",
    "dry_run",
    is_flag=True,
    default=False,
    help="Skip executing test commands; still collect git status/diff.",
)
def main(
    idea: tuple[str, ...],
    root: str,
    max_loops: int,
    mode: str,
    test_commands: tuple[str, ...],
    dry_run: bool,
) -> None:
    user_input = " ".join(idea).strip()
    if not user_input:
        raise click.UsageError("idea must be a non-empty string")

    project_root = str(Path(root).resolve())

    run_graph(
        user_input=user_input,
        project_root=project_root,
        mode=mode,
        max_loops=max_loops,
        test_commands=list(test_commands),
        dry_run=dry_run,
    )


if __name__ == "__main__":
    main()
