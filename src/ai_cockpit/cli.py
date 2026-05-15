"""``ai-cockpit`` command-line entry point."""

from __future__ import annotations

import sys
import uuid
from contextlib import ExitStack
from pathlib import Path

import click

from ai_cockpit.checkpoint import default_checkpoint_path, open_sqlite_saver
from ai_cockpit.graph import run_graph
from ai_cockpit.llm import build_llm


@click.command(
    name="ai-cockpit",
    help="Run the AI Cockpit idea-to-MVP execution loop on an idea.",
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
@click.option(
    "--thread-id",
    "thread_id",
    default=None,
    help=(
        "Checkpoint thread id. Reuse the same id with --resume to continue "
        "an interrupted run. A new uuid is generated if omitted."
    ),
)
@click.option(
    "--resume",
    "resume",
    is_flag=True,
    default=False,
    help="Resume from the last checkpoint for --thread-id (requires --thread-id).",
)
@click.option(
    "--no-checkpoint",
    "no_checkpoint",
    is_flag=True,
    default=False,
    help="Disable SQLite checkpointing (ephemeral run, no .ai-cockpit/history write).",
)
@click.option(
    "--checkpoint-db",
    "checkpoint_db",
    default=None,
    type=click.Path(dir_okay=False),
    help="Override the SQLite checkpoint path. Defaults to "
    ".ai-cockpit/history/checkpoints.sqlite under --root.",
)
def main(
    idea: tuple[str, ...],
    root: str,
    max_loops: int,
    mode: str,
    test_commands: tuple[str, ...],
    dry_run: bool,
    llm_mode: str,
    thread_id: str | None,
    resume: bool,
    no_checkpoint: bool,
    checkpoint_db: str | None,
) -> None:
    user_input = " ".join(idea).strip()
    if not user_input:
        raise click.UsageError("idea must be a non-empty string")

    if resume and not thread_id:
        raise click.UsageError("--resume requires --thread-id")
    if resume and no_checkpoint:
        raise click.UsageError("--resume cannot be combined with --no-checkpoint")

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

    effective_thread_id = thread_id or (None if no_checkpoint else f"run-{uuid.uuid4().hex[:12]}")

    with ExitStack() as stack:
        checkpointer = None
        if not no_checkpoint:
            db_path = checkpoint_db or str(default_checkpoint_path(project_root))
            checkpointer = stack.enter_context(open_sqlite_saver(db_path))
            click.echo(
                f"info: checkpoint db={db_path} thread_id={effective_thread_id} "
                f"resume={resume}",
                err=True,
            )

        run_graph(
            user_input=user_input,
            project_root=project_root,
            mode=mode,
            max_loops=max_loops,
            test_commands=list(test_commands),
            dry_run=dry_run,
            llm=llm,
            checkpointer=checkpointer,
            thread_id=effective_thread_id,
            resume=resume,
        )


if __name__ == "__main__":
    main(prog_name="ai-cockpit", standalone_mode=True, args=sys.argv[1:])
