"""``ai-cockpit`` command-line entry point.

v0.2 step 5b restructures the CLI into a ``click.Group`` so we can expose
a ``memory`` subgroup for reviewing and applying suggestion blobs written
by step 5a. Backward compatibility for the historical positional form
``ai-cockpit "some idea" --flags`` is preserved by a ``_DefaultGroup``:
if the first non-option token is not a registered subcommand, the group
silently prepends ``run`` before dispatching.
"""

from __future__ import annotations

import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import click

from ai_cockpit.checkpoint import new_thread_id, resolve_checkpoint_db
from ai_cockpit.graph import run_graph
from ai_cockpit.llm import build_llm
from ai_cockpit.memory.suggestions import (
    Suggestion,
    SuggestionError,
    accept_suggestion,
    generate_and_write,
    list_suggestions,
    load_suggestion,
)
from ai_cockpit.planner_interactive import run_interactive_planner
from ai_cockpit.tools.git import is_git_repo
from ai_cockpit.tools.shell import run_command
from ai_cockpit.workflow import (
    Workflow,
    WorkflowError,
    default_workflow_path,
    load_workflow,
)


def _get_version() -> str:
    """Return the installed package version, or 'dev' when not installed."""
    try:
        from importlib.metadata import version as _pkg_version

        return _pkg_version("ai-cockpit")
    except Exception:
        return "dev"


class _DefaultGroup(click.Group):
    """Group that dispatches to ``run`` when no subcommand is given.

    Without this shim, the v0.1 / early-v0.2 invocation
    ``ai-cockpit "some idea" --flags`` would break the moment we add real
    subcommands. We inspect the *first* non-option token: if it matches a
    registered subcommand (``run`` / ``memory``) we let click route as usual;
    otherwise we prepend ``run`` so the historical form keeps working.
    Pure-option invocations (e.g. ``ai-cockpit --help``) are passed through
    so the group's help still surfaces.
    """

    default_cmd_name = "run"

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        if args:
            first_non_opt = next((a for a in args if not a.startswith("-")), None)
            if first_non_opt is not None and first_non_opt not in self.commands:
                args = [self.default_cmd_name, *args]
        return super().parse_args(ctx, args)


@click.group(
    cls=_DefaultGroup,
    name="ai-cockpit",
    help=(
        "Run the AI Cockpit idea-to-MVP execution loop, or manage memory "
        "suggestions written by previous runs."
    ),
    context_settings={"help_option_names": ["-h", "--help"]},
)
def main() -> None:  # noqa: D401 - click group docstring is in the decorator
    """Group entry point — actual work happens in subcommands."""


# A.7: paths matching any of these prefixes are aider/ai-cockpit runtime
# side-effects, not user work, so a dirty entry pointing at one of them
# never blocks `--worker aider --apply`. Keep in sync with `docs/ROADMAP.md`
# §A.7 and the A.8 .gitignore additions.
_AIDER_RUNTIME_ALLOWLIST_PREFIXES: tuple[str, ...] = (
    ".aider.",
    ".aider/",
    ".ai-cockpit/suggestions/",
    ".ai-cockpit/history/",
)


def _dirty_paths_outside_aider_allowlist(project_root: str) -> list[str]:
    """Return uncommitted-modification paths that are NOT aider runtime artifacts.

    ``--untracked-files=all`` matters: without it git collapses untracked
    dirs into a single entry (e.g. ``.ai-cockpit/``) that defeats per-file
    prefix matching for a legitimate ``.ai-cockpit/suggestions/foo.json``.
    Returns ``[]`` on non-git roots or git failure — best-effort, not a
    hard gate.
    """
    if not is_git_repo(project_root):
        return []
    result = run_command(
        "git status --porcelain --untracked-files=all", cwd=project_root
    )
    if result["exit_code"] != 0:
        return []
    paths: list[str] = []
    for raw_line in result["stdout"].splitlines():
        if len(raw_line) < 4:
            continue
        rest = raw_line[3:]
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        path = rest.strip()
        if path and not any(
            path.startswith(p) for p in _AIDER_RUNTIME_ALLOWLIST_PREFIXES
        ):
            paths.append(path)
    return paths


def _enforce_dirty_tree_precheck(project_root: str) -> None:
    """A.7: refuse ``--worker aider --apply`` on a dirty working tree."""
    dirty = _dirty_paths_outside_aider_allowlist(project_root)
    if not dirty:
        return
    click.echo(
        "error: refusing --worker aider --apply on a dirty working tree. "
        "The following uncommitted paths are not aider runtime artifacts:",
        err=True,
    )
    for path in dirty:
        click.echo(f"  {path}    (revert with: git checkout -- {path})", err=True)
    click.echo(
        "Commit, stash, or revert these paths before re-running, or pass "
        "--allow-dirty-tree to bypass this guard at your own risk.",
        err=True,
    )
    raise click.UsageError(
        f"dirty working tree blocks --worker aider --apply "
        f"({len(dirty)} path(s) outside aider runtime allow-list)"
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


@main.command(
    name="run",
    help="Run the idea-to-MVP execution loop on an idea (default subcommand).",
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
@click.option(
    "--suggest/--no-suggest",
    "suggest",
    default=True,
    show_default=True,
    help=(
        "After the run, write a memory-update suggestion JSON under "
        ".ai-cockpit/suggestions/. Inspect with `ai-cockpit memory list` "
        "and apply with `ai-cockpit memory accept <id>`."
    ),
)
@click.option(
    "--worker",
    "worker_name",
    default="stub",
    show_default=True,
    type=click.Choice(["stub", "aider"], case_sensitive=False),
    help=(
        "Which worker executes the implementation slice. 'stub' (default) "
        "never modifies the working tree. 'aider' spawns the aider CLI; "
        "to actually let aider write files you must also pass --apply, "
        "otherwise the worker only previews the message it would send."
    ),
)
@click.option(
    "--apply",
    "apply",
    is_flag=True,
    default=False,
    help=(
        "For --worker aider: opt in to actually invoking aider so it can "
        "modify files. Without --apply, aider is never spawned (preview-only). "
        "Ignored when --worker stub. Mutually exclusive with --dry-run."
    ),
)
@click.option(
    "--allow-dirty-tree",
    "allow_dirty_tree",
    is_flag=True,
    default=False,
    help=(
        "Skip the A.7 pre-run dirty-tree pre-check. By default, "
        "--worker aider --apply refuses to start if uncommitted changes "
        "exist outside the aider runtime allow-list (.aider.*, "
        ".ai-cockpit/suggestions/, .ai-cockpit/history/) so aider does "
        "not squash your work-in-progress. Pass this flag only if you "
        "deliberately want aider to edit on top of a dirty tree."
    ),
)
@click.pass_context
def run_cmd(
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
    suggest: bool,
    worker_name: str,
    apply: bool,
    allow_dirty_tree: bool,
) -> None:
    if no_checkpoint and (thread_id or resume or checkpoint_db):
        raise click.UsageError(
            "--no-checkpoint cannot be combined with --thread-id, --resume, "
            "or --checkpoint-db"
        )

    if resume and not thread_id:
        raise click.UsageError("--resume requires --thread-id")

    worker_name = (worker_name or "stub").lower()
    if apply and worker_name != "aider":
        raise click.UsageError("--apply is only meaningful with --worker aider")
    if apply and dry_run:
        raise click.UsageError("--apply and --dry-run are mutually exclusive")
    if allow_dirty_tree and not (worker_name == "aider" and apply):
        click.echo(
            "warning: --allow-dirty-tree only affects --worker aider --apply; "
            "ignored for the current invocation.",
            err=True,
        )
    # Safety default: aider worker is preview-only unless --apply is set.
    effective_dry_run = dry_run or (worker_name == "aider" and not apply)

    user_input = " ".join(idea).strip() if idea else ""
    if not resume and not user_input:
        raise click.UsageError("idea must be a non-empty string")

    project_root = str(Path(root).resolve())

    if worker_name == "aider" and apply and not allow_dirty_tree:
        _enforce_dirty_tree_precheck(project_root)

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

    if worker_name == "aider":
        if apply:
            click.echo(
                "info: worker=aider --apply: aider WILL be invoked and may modify "
                "your working tree.",
                err=True,
            )
        else:
            click.echo(
                "info: worker=aider preview-only (no --apply): aider will NOT be "
                "spawned; pass --apply to let it edit files.",
                err=True,
            )

    final_state = run_graph(
        user_input=user_input,
        project_root=project_root,
        mode=mode,
        max_loops=max_loops,
        test_commands=list(test_commands),
        dry_run=effective_dry_run,
        llm=llm,
        checkpoint_db=checkpoint_db,
        thread_id=effective_thread_id,
        resume=resume,
        worker_name=worker_name,
    )

    if suggest and final_state is not None:
        try:
            suggestion = generate_and_write(project_root, final_state)
        except SuggestionError as exc:
            click.echo(f"warning: could not write memory suggestion: {exc}", err=True)
        else:
            if suggestion is not None:
                click.echo(
                    f"info: memory suggestion written: {suggestion.id} "
                    f"(target={suggestion.target}); "
                    "see `ai-cockpit memory list` to review or "
                    "`ai-cockpit memory accept <id>` to apply.",
                    err=True,
                )


# ---------------------------------------------------------------------------
# interactive planner command (B.9a)
# ---------------------------------------------------------------------------


@main.command(
    name="plan",
    help="Interactively discuss and save a human-approved plan artifact.",
)
@click.argument("idea", nargs=-1, required=True)
@click.option(
    "--root",
    "root",
    default=".",
    show_default=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    help="Project root to inspect and where docs/plans/ is written.",
)
@click.option(
    "--output",
    "output",
    default=None,
    type=click.Path(dir_okay=False, resolve_path=True),
    help="Optional plan YAML path. Defaults to docs/plans/<plan_id>.plan.yaml.",
)
@click.option(
    "--llm",
    "llm_mode",
    default="auto",
    show_default=True,
    type=click.Choice(["none", "auto", "anthropic", "openai"], case_sensitive=False),
    help="'none' uses the deterministic B.9a fixture; real LLM support is B.9c.",
)
@click.option(
    "--backend",
    "backend",
    default="builtin",
    show_default=True,
    type=click.Choice(["builtin", "cursor"], case_sensitive=False),
    help="Planner backend. B.9a implements only the builtin fixture backend.",
)
@click.option(
    "--max-slices",
    "max_slices",
    default=None,
    type=click.IntRange(min=1),
    help="Optional save-time cap on draft slice count.",
)
@click.option(
    "--max-turns",
    "max_turns",
    default=12,
    show_default=True,
    type=click.IntRange(min=1, max=100),
    help="Maximum feedback turns before warning the user.",
)
@click.option(
    "--max-tool-bytes",
    "max_tool_bytes",
    default=12000,
    show_default=True,
    type=click.IntRange(min=1000, max=100000),
    help="Reserved for B.9b read-only tool output clipping.",
)
def plan_cmd(
    idea: tuple[str, ...],
    root: str,
    output: str | None,
    llm_mode: str,
    backend: str,
    max_slices: int | None,
    max_turns: int,
    max_tool_bytes: int,
) -> None:
    """Start the B.9 interactive planning REPL."""

    user_input = " ".join(idea).strip()
    if not user_input:
        raise click.UsageError("idea must be a non-empty string")
    if llm_mode != "none" and not click.get_text_stream("stdin").isatty():
        raise click.UsageError(
            "Interactive planner requires a TTY. Use --llm none only for tests."
        )
    run_interactive_planner(
        idea=user_input,
        project_root=Path(root).resolve(),
        output_path=Path(output).resolve() if output else None,
        llm_mode=llm_mode.lower(),
        backend=backend.lower(),
        max_slices=max_slices,
        max_turns=max_turns,
        max_tool_bytes=max_tool_bytes,
    )


# ---------------------------------------------------------------------------
# status subcommand
# ---------------------------------------------------------------------------


def _count_workflow_files(project_root: str) -> int:
    """Count .yaml and .yml files under <project_root>/.ai-cockpit/workflows/."""
    workflows_dir = Path(project_root) / ".ai-cockpit" / "workflows"
    if not workflows_dir.is_dir():
        return 0
    count = 0
    for ext in ("*.yaml", "*.yml"):
        count += len(list(workflows_dir.glob(ext)))
    return count


def _probe_llm_auto() -> str:
    """Check whether ``build_llm("auto")`` can construct a provider.

    Returns ``"available (<name>)"`` or ``"unavailable"`` — never calls the
    LLM.
    """
    try:
        llm = build_llm("auto")
    except Exception:
        return "unavailable"
    if llm is None:
        return "unavailable"
    return f"available ({llm.name})"


@main.command(
    name="status",
    help=(
        "Show project status: version, root, LLM availability, workflows, "
        "suggestions, checkpoint DB."
    ),
)
@click.option(
    "--root",
    "root",
    default=".",
    show_default=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    help="Project root to inspect.",
)
def status_cmd(root: str) -> None:
    """Print a concise status report for the current project."""
    project_root = str(Path(root).resolve())

    version = _get_version()
    llm_mode_auto = _probe_llm_auto()
    workflows_found = _count_workflow_files(project_root)
    suggestions_pending = len(list_suggestions(project_root))
    checkpoint_db = str(resolve_checkpoint_db(project_root))

    click.echo(f"version: {version}")
    click.echo(f"project_root: {project_root}")
    click.echo(f"llm_mode_auto: {llm_mode_auto}")
    click.echo(f"workflows_found: {workflows_found}")
    click.echo(f"suggestions_pending: {suggestions_pending}")
    click.echo(f"checkpoint_db: {checkpoint_db}")


# ---------------------------------------------------------------------------
# memory subgroup
# ---------------------------------------------------------------------------


@main.group(
    name="memory",
    help="Inspect and apply memory-update suggestions written by previous runs.",
)
def memory_group() -> None:
    """Memory-suggestion lifecycle subcommands."""


_ROOT_OPTION = click.option(
    "--root",
    "root",
    default=".",
    show_default=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    help="Project root containing .ai-cockpit/suggestions/.",
)


# A.2 (2026-05-16): ``memory list`` gained an ``age:`` column and a one-line
# aggregate summary. The decision label that drove the original run lives in
# the suggestion id (canonical) and in the rationale text (fallback); we
# extract from whichever is available so user-crafted suggestions still
# render cleanly without contributing to either subtotal.
_DECISION_FROM_ID_RE = re.compile(r"^\d{8}T\d{6}-(done|ask_human)-")
_DECISION_FROM_RATIONALE_RE = re.compile(r"decision=([A-Za-z_]+)")


def _parse_created_at(s: Suggestion) -> datetime:
    """Parse a suggestion's ``created_at`` to an aware UTC datetime.

    Falls back to a sentinel far in the past so malformed timestamps sort to
    the bottom of a ``reverse=True`` listing rather than crashing the CLI.
    """
    try:
        dt = datetime.fromisoformat(s.created_at)
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _format_age(s: Suggestion, *, now: datetime) -> str:
    """Render ``created_at`` as ``Nd Nh ago`` relative to ``now``.

    Returns ``"?d ?h ago"`` if the timestamp can't be parsed and ``"0d 0h ago"``
    if the timestamp is in the future (clock skew); never raises.
    """
    try:
        dt = datetime.fromisoformat(s.created_at)
    except (TypeError, ValueError):
        return "?d ?h ago"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    seconds = int((now - dt).total_seconds())
    if seconds < 0:
        return "0d 0h ago"
    days, remainder = divmod(seconds, 86400)
    hours = remainder // 3600
    return f"{days}d {hours}h ago"


def _decision_of(s: Suggestion) -> str | None:
    """Best-effort extraction of the run decision that produced a suggestion.

    Suggestions written by ``build_suggestion_from_state`` encode the decision
    twice: in the id (``<ts>-<decision>-<slug>``) and in the rationale
    (``decision=<value>``). Either match is enough; manually-crafted
    suggestions with neither return ``None``.
    """
    m = _DECISION_FROM_ID_RE.match(s.id)
    if m:
        return m.group(1)
    m2 = _DECISION_FROM_RATIONALE_RE.search(s.rationale or "")
    if m2:
        return m2.group(1)
    return None


@memory_group.command(name="list", help="List pending memory suggestions.")
@_ROOT_OPTION
def memory_list_cmd(root: str) -> None:
    suggestions = list_suggestions(root)
    if not suggestions:
        click.echo("no pending memory suggestions")
        return
    suggestions.sort(key=_parse_created_at, reverse=True)
    now = datetime.now(UTC)
    done_count = 0
    ask_human_count = 0
    for s in suggestions:
        first_line = s.content.splitlines()[0] if s.content else ""
        age = _format_age(s, now=now)
        click.echo(
            f"age: {age}\t{s.id}\t{s.target}\t{s.operation}\t{first_line}"
        )
        decision = _decision_of(s)
        if decision == "done":
            done_count += 1
        elif decision == "ask_human":
            ask_human_count += 1
    click.echo(
        f"total: {len(suggestions)} "
        f"(done: {done_count}, ask_human: {ask_human_count})"
    )


@memory_group.command(name="show", help="Show one pending memory suggestion in full.")
@click.argument("suggestion_id")
@_ROOT_OPTION
def memory_show_cmd(suggestion_id: str, root: str) -> None:
    try:
        s = load_suggestion(root, suggestion_id)
    except SuggestionError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"id:         {s.id}")
    click.echo(f"created_at: {s.created_at}")
    click.echo(f"target:     {s.target}")
    click.echo(f"operation:  {s.operation}")
    click.echo(f"rationale:  {s.rationale}")
    click.echo("---")
    click.echo(s.content)


@memory_group.command(
    name="accept",
    help="Apply a pending suggestion to its target memory file and archive it.",
)
@click.argument("suggestion_id")
@_ROOT_OPTION
def memory_accept_cmd(suggestion_id: str, root: str) -> None:
    try:
        target = accept_suggestion(root, suggestion_id)
    except SuggestionError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"applied {suggestion_id} -> {target}")


# ---------------------------------------------------------------------------
# workflows subgroup (A.4)
# ---------------------------------------------------------------------------


@main.group(
    name="workflows",
    help="Inspect and validate workflow YAMLs under .ai-cockpit/workflows/.",
)
def workflows_group() -> None:
    """Workflow YAML discovery + pre-flight validation subcommands."""


_WORKFLOWS_ROOT_OPTION = click.option(
    "--root",
    "root",
    default=".",
    show_default=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    help="Project root containing .ai-cockpit/workflows/.",
)


def _iter_workflow_yaml_paths(project_root: str) -> list[Path]:
    """Return YAML files under <root>/.ai-cockpit/workflows/ in sorted order."""
    workflows_dir = Path(project_root) / ".ai-cockpit" / "workflows"
    if not workflows_dir.is_dir():
        return []
    paths: list[Path] = []
    for ext in ("*.yaml", "*.yml"):
        paths.extend(workflows_dir.glob(ext))
    return sorted(paths)


@workflows_group.command(
    name="list",
    help="List workflow YAMLs with their mode, max_loops, and test-command count.",
)
@_WORKFLOWS_ROOT_OPTION
def workflows_list_cmd(root: str) -> None:
    project_root = str(Path(root).resolve())
    paths = _iter_workflow_yaml_paths(project_root)
    if not paths:
        click.echo("no workflows found")
        return
    click.echo("name\tmode\tmax_loops\ttest_commands_count")
    for path in paths:
        try:
            wf = load_workflow(path)
            test_commands_count: int | str = len(wf.verifier_test_commands())
            mode = wf.mode
            max_loops: int | str = wf.max_loops
            name = wf.name
        except WorkflowError as exc:
            name = path.stem
            mode = "?"
            max_loops = "?"
            test_commands_count = f"INVALID: {exc}"
        click.echo(f"{name}\t{mode}\t{max_loops}\t{test_commands_count}")


@workflows_group.command(
    name="validate",
    help="Load a workflow YAML and report 'OK' or a specific WorkflowError.",
)
@click.argument(
    "path",
    type=click.Path(exists=True, dir_okay=False, resolve_path=True),
)
def workflows_validate_cmd(path: str) -> None:
    try:
        load_workflow(path)
    except WorkflowError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo("OK")


if __name__ == "__main__":
    main(prog_name="ai-cockpit", standalone_mode=True, args=sys.argv[1:])
