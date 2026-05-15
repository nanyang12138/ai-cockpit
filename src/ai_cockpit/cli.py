"""``ai-cockpit`` command-line entry point."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from ai_cockpit.graph import run_graph
from ai_cockpit.llm import build_llm


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
@click.option(
    "--llm",
    "llm_mode",
    default="none",
    show_default=True,
    type=click.Choice(["none", "auto", "anthropic", "openai"], case_sensitive=False),
    help=(
        "Use a real LLM for planner/reviewer. 'auto' detects from env "
        "(LLM_API_KEY/LLM_API_BASE/LLM_MODEL_NAME, then ANTHROPIC_API_KEY, "
        "then OPENAI_API_KEY). 'none' (default) keeps stub behavior."
    ),
)
def main(
    idea: tuple[str, ...],
    root: str,
    max_loops: int,
    mode: str,
    test_commands: tuple[str, ...],
    dry_run: bool,
    llm_mode: str,
) -> None:
    user_input = " ".join(idea).strip()
    if not user_input:
        raise click.UsageError("idea must be a non-empty string")

    project_root = str(Path(root).resolve())

    llm = build_llm(llm_mode)
    if llm_mode != "none" and llm is None:
        click.echo(
            "warning: --llm requested but no usable LLM is available "
            "(missing credentials or optional package); "
            "falling back to stub planner/reviewer.",
            err=True,
        )
    elif llm is not None:
        click.echo(f"info: LLM enabled ({llm.name})", err=True)

    run_graph(
        user_input=user_input,
        project_root=project_root,
        mode=mode,
        max_loops=max_loops,
        test_commands=list(test_commands),
        dry_run=dry_run,
        llm=llm,
    )


if __name__ == "__main__":
    main(prog_name="ai-cockpit", standalone_mode=True, args=sys.argv[1:])
