"""Terminal REPL for B.9 interactive planning."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import click

from ai_cockpit.llm import build_llm
from ai_cockpit.memory.loader import load_memory
from ai_cockpit.planner_interactive.backends import BuiltinPlannerBackend
from ai_cockpit.planner_interactive.types import (
    PlanDraft,
    PlannerBackend,
    PlannerRequest,
    PlanValidationError,
    default_plan_path,
    save_plan_atomic,
)

if TYPE_CHECKING:
    from ai_cockpit.cursor_adapter import CursorSessionFactory

_cursor_session_factory_override: CursorSessionFactory | None = None

HELP_TEXT = """Commands:
  /help              Show this help.
  /draft             Ask for the current draft summary.
  /show              Print the current draft YAML.
  /revise <feedback> Record feedback for the planner.
  /tools             List planner tools (B.9b).
  /save [path]       Validate and save the current draft.
  /abort             Exit without writing.
"""


def build_planner_backend(request: PlannerRequest) -> PlannerBackend:
    """Return the backend for the interactive planner.

    B.9b shipped the builtin backend shell with the read-only tool
    registry in deterministic ``--llm none`` mode. B.9c wires the
    existing :class:`LLMProvider` factory so non-``none`` modes ask a
    real LLM for a structured ``PlanDraft`` payload. The optional
    Cursor backend ships through B.10's role-backend track, not as a
    one-off B.9 adapter.
    """

    if request.backend == "cursor":
        from ai_cockpit.cursor_adapter import CursorPlannerBackend

        cursor_backend = CursorPlannerBackend(
            session_factory=_cursor_session_factory_override,
        )
        click.echo("info: planner backend enabled (cursor)", err=True)
        return cursor_backend
    if request.backend != "builtin":
        raise click.ClickException(
            f"planner backend {request.backend!r} is not implemented yet; "
            "use --backend builtin or --backend cursor"
        )
    backend = BuiltinPlannerBackend(llm_mode=request.llm_mode)
    if request.llm_mode != "none":
        llm = build_llm(request.llm_mode)
        if llm is None:
            click.echo(
                "warning: --llm requested but no usable LLM is available "
                "(missing credentials or optional package); falling back "
                "to the deterministic fixture draft.",
                err=True,
            )
        else:
            click.echo(f"info: planner LLM enabled ({llm.name})", err=True)
        backend.bind_llm(llm)
    return backend


def set_cursor_session_factory_for_tests(
    factory: CursorSessionFactory | None,
) -> None:
    """Install a fake :class:`CursorPlannerSession` factory for tests."""

    global _cursor_session_factory_override
    _cursor_session_factory_override = factory


def run_interactive_planner(
    *,
    idea: str,
    project_root: Path,
    output_path: Path | None,
    llm_mode: str,
    backend: str,
    max_slices: int | None,
    max_turns: int,
    max_tool_bytes: int,
) -> None:
    """Run the interactive planner REPL."""

    request = PlannerRequest(
        idea=idea,
        project_root=project_root,
        memory_context=load_memory(project_root),
        output_path=output_path,
        llm_mode=llm_mode,
        backend=backend,
        max_slices=max_slices,
        max_turns=max_turns,
        max_tool_bytes=max_tool_bytes,
    )
    planner = build_planner_backend(request)
    try:
        response = planner.start(request)
    except Exception as exc:
        from ai_cockpit.cursor_adapter import CursorUnavailableError

        if isinstance(exc, CursorUnavailableError):
            raise click.ClickException(str(exc)) from exc
        raise
    click.echo(response.message)
    click.echo("Type /help for commands.")

    turns = 0
    while True:
        try:
            raw = click.prompt("plan", default="", show_default=False)
        except (EOFError, KeyboardInterrupt):
            click.echo("\naborted; no plan written")
            return
        command = raw.strip()
        if not command:
            continue
        if command == "/help":
            click.echo(HELP_TEXT.rstrip())
        elif command == "/draft":
            _show_draft_summary(planner.draft())
        elif command == "/show":
            _show_draft_yaml(planner.draft())
        elif command.startswith("/revise"):
            feedback = command.removeprefix("/revise").strip()
            _handle_feedback(planner, feedback or "(no feedback supplied)")
            turns += 1
        elif command == "/tools":
            _show_tools(planner)
        elif command.startswith("/save"):
            target = _resolve_save_path(
                project_root,
                planner.draft(),
                request.output_path,
                command.removeprefix("/save").strip(),
            )
            if target is None:
                continue
            try:
                save_plan_atomic(target, _draft_or_raise(planner), max_slices=max_slices)
            except PlanValidationError as exc:
                click.echo(f"error: plan validation failed: {exc}", err=True)
                continue
            click.echo(f"saved plan: {target}")
            return
        elif command == "/abort":
            click.echo("aborted; no plan written")
            return
        elif command.startswith("/"):
            click.echo(f"unknown command: {command}")
        else:
            _handle_feedback(planner, command)
            turns += 1

        if turns >= max_turns:
            click.echo(
                "max planner turns reached; use /save, /abort, or restart with "
                "a larger --max-turns value.",
                err=True,
            )


def _handle_feedback(planner: PlannerBackend, feedback: str) -> None:
    response = planner.respond(feedback)
    click.echo(response.message)


def _show_tools(planner: PlannerBackend) -> None:
    tools_fn = getattr(planner, "tools", None)
    registry = tools_fn() if callable(tools_fn) else None
    if not registry:
        click.echo("No read-only tools are available in this backend.")
        return
    click.echo("Read-only planner tools:")
    for tool in registry.values():
        click.echo(f"- {tool.name}: {tool.description}")


def _show_draft_summary(draft: PlanDraft | None) -> None:
    if draft is None:
        click.echo("no draft yet")
        return
    click.echo(f"plan_id: {draft.plan_id}")
    click.echo(f"slices: {len(draft.slices)}")
    for plan_slice in draft.slices:
        click.echo(f"- {plan_slice.id}: {plan_slice.title}")


def _show_draft_yaml(draft: PlanDraft | None) -> None:
    if draft is None:
        click.echo("no draft yet")
        return
    click.echo(draft.to_yaml().rstrip())


def _resolve_save_path(
    project_root: Path,
    draft: PlanDraft | None,
    output_path: Path | None,
    arg: str,
) -> Path | None:
    if draft is None:
        click.echo("error: no draft to save", err=True)
        return None
    if arg:
        return Path(arg).expanduser().resolve()
    if output_path is not None:
        return output_path
    return default_plan_path(project_root, draft)


def _draft_or_raise(planner: PlannerBackend) -> PlanDraft:
    draft = planner.draft()
    if draft is None:
        raise PlanValidationError("no draft to save")
    return draft
