"""``ai-cockpit`` command-line entry point."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from ai_cockpit.checkpoint import new_thread_id
from ai_cockpit.graph import run_graph
from ai_cockpit.llm import build_llm
from ai_cockpit.workflow import (
    Workflow,
    WorkflowError,
    default_workflow_path,
    load_workflow,
)


def _resolve_workflow(project_root: str, override_path: str | None) -> Workflow | None:
    """Resolve which workflow YAML to use; missing default is OK, malformed isn't."""

    if override_path is not None:
        try:
            return load_workflow(override_path)
        except WorkflowError as exc:
            raise click.UsageError(f"--workflow: {exc}") from exc
    default_path = default_workflow_path(project_root)
    if not default_path.is_file():
        return None
    try:
        return load_workflow(default_path)
    except WorkflowError as exc:
        raise click.UsageError(f"workflow YAML at {default_path}: {exc}") from exc


def _apply_workflow_defaults(
    ctx: click.Context,
    workflow: Workflow | None,
    *,
    mode: str,
    max_loops: int,
    test_commands: tuple[str, ...],
) -> tuple[str, int, tuple[str, ...]]:
    """Layer YAML-provided defaults under explicit CLI flags."""

    if workflow is None:
        return mode, max_loops, test_commands
    default = click.core.ParameterSource.DEFAULT
    if ctx.get_parameter_source("mode") == default:
        mode = workflow.mode
    if ctx.get_parameter_source("max_loops") == default:
        max_loops = workflow.max_loops
    yaml_cmds = workflow.verifier_test_commands()
    if yaml_cmds:
        test_commands = yaml_cmds + tuple(test_commands)
    return mode, max_loops, test_commands


@click.command(
    name="ai-cockpit",
    help="Run the AI Cockpit v0.1 idea-to-MVP execution loop on an idea.",
)
@click.argument("idea", nargs=-1, required=False)
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
    type=str,
    help=(
        "Explicit thread id under which this run is persisted. When omitted "
        "and checkpointing is enabled (the default), a fresh id is minted "
        "and printed to stderr."
    ),
)
@click.option(
    "--resume",
    "resume",
    is_flag=True,
    default=False,
    help=(
        "Resume the run identified by --thread-id from its last saved "
        "checkpoint. Requires --thread-id; idea argument is ignored."
    ),
)
@click.option(
    "--no-checkpoint",
    "no_checkpoint",
    is_flag=True,
    default=False,
    help=(
        "Disable SQLite checkpointing for this run (no DB writes). "
        "Mutually exclusive with --thread-id / --resume / --checkpoint-db."
    ),
)
@click.option(
    "--checkpoint-db",
    "checkpoint_db",
    default=None,
    type=click.Path(dir_okay=False),
    help=(
        "Override the checkpoint database path. Defaults to "
        "<root>/.ai-cockpit/history/checkpoints.sqlite when checkpointing "
        "is enabled."
    ),
)
@click.option(
    "--workflow",
    "workflow_path",
    default=None,
    type=click.Path(dir_okay=False),
    help=(
        "Override the workflow YAML path. Defaults to "
        "<root>/.ai-cockpit/workflows/idea-to-mvp.yaml when present. "
        "The YAML supplies defaults for --mode, --max-loops, and "
        "--test-command; explicit CLI flags always win."
    ),
)
@click.pass_context
def main(
    ctx: click.Context,
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
    workflow_path: str | None,
) -> None:
    if no_checkpoint and (thread_id or resume or checkpoint_db):
        raise click.UsageError(
            "--no-checkpoint cannot be combined with --thread-id, --resume, "
            "or --checkpoint-db"
        )

    if resume and not thread_id:
        raise click.UsageError("--resume requires --thread-id")

    user_input = " ".join(idea).strip() if idea else ""
    if not resume and not user_input:
        raise click.UsageError("idea must be a non-empty string")

    project_root = str(Path(root).resolve())

    workflow = _resolve_workflow(project_root, workflow_path)
    mode, max_loops, test_commands = _apply_workflow_defaults(
        ctx, workflow, mode=mode, max_loops=max_loops, test_commands=test_commands
    )

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

    effective_thread_id: str | None = thread_id
    if not no_checkpoint and not resume and effective_thread_id is None:
        effective_thread_id = new_thread_id()
        click.echo(
            f"info: checkpointing enabled, thread id: {effective_thread_id} "
            "(use --no-checkpoint to disable)",
            err=True,
        )
    elif resume:
        click.echo(f"info: resuming thread {effective_thread_id}", err=True)
    elif effective_thread_id is not None:
        click.echo(f"info: persisting run as thread {effective_thread_id}", err=True)

    run_graph(
        user_input=user_input,
        project_root=project_root,
        mode=mode,
        max_loops=max_loops,
        test_commands=list(test_commands),
        dry_run=dry_run,
        llm=llm,
        checkpoint_db=checkpoint_db,
        thread_id=effective_thread_id,
        resume=resume,
    )


if __name__ == "__main__":
    main(prog_name="ai-cockpit", standalone_mode=True, args=sys.argv[1:])
