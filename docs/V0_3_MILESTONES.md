# v0.3 Milestones

Permanent record of v0.3 events that proved capabilities the project
was not previously known to have. Pairs with `docs/V0_2_COMPLETION.md`
(which froze v0.2's exit-gate evidence).

## 2026-05-16 — ai-cockpit's first non-demo feature contribution

**Headline:** ai-cockpit, running its own `--worker aider --apply --llm
auto` flow against the AMD Anthropic-via-APIM endpoint, autonomously
produced the source code for the `status` subcommand (ROADMAP A.1) and
its 9-test CliRunner suite. The human contribution was the prompt
(copied verbatim from `docs/ROADMAP.md` A.1) and the cleanup of
unrelated leftover state in the working tree. No edits to the
generated code were necessary; the code merged as-is via PR #31
(squash-merge commit `7a903ab`, master at the time of writing).

This is structurally different from the §15.1 demo on 2026-05-15:

| Aspect | §15.1 demo (broken_calc) | A.1 milestone (status subcommand) |
|---|---|---|
| Source | `examples/broken_calc/calc.py` | `src/ai_cockpit/cli.py` |
| Goal | "fix the failing test" | "implement a planned feature" |
| Scope | 1 file, 1-line change | 2 files, ~165 net LOC |
| Risk surface | demo fixture, not shipped code | real shipped CLI surface |
| Pattern complexity | revert one operator | add a new click subcommand following the existing `_DefaultGroup` + `@main.command` registration pattern |
| Tests added | 0 (test already existed) | 9 new CliRunner tests |

§15.1 proved the loop works on a toy. A.1 proves the loop can extend
the project's own production surface area. v0.3 was originally
scoped without this evidence; this milestone is what makes the
"v0.3 → v0.4 transition" defensible from data rather than wishful
thinking.

### Run parameters

- **Model:** `anthropic/claude-opus-4-6` via the AMD APIM endpoint
  `https://llm-api.amd.com/Anthropic`.
- **Worker:** AiderWorker (`aider-chat 0.86.2`) under
  `--worker aider --apply`.
- **Workflow:** `.ai-cockpit/workflows/bug-fix.yaml` (mode=task,
  max_loops=3, auto-test-commands `python -m pytest -q` + `ruff
  check .`).
- **Prompt to ai-cockpit (verbatim):**

  > "implement a new 'status' subcommand on src/ai_cockpit/cli.py
  > following the same _DefaultGroup pattern as the existing 'memory'
  > subgroup. Output lines: version, project_root, llm_mode_auto
  > availability via build_llm() WITHOUT calling the LLM, workflows
  > found under .ai-cockpit/workflows/, suggestions_pending count,
  > checkpoint_db path. Add tests via CliRunner. Acceptance criteria
  > are in docs/ROADMAP.md section A.1."

### Cost / token signal

Two aider invocations across the 3 graph loops:

- Loop 1: `Tokens: 11k sent, 566 received. Cost: $0.07`.
- Loop 2: `Tokens: 14k sent, 286 received. Cost: $0.08, session: $0.15`.
- Loop 3: identical to loop 2 (aider confirmed "no further changes
  needed"; the planner re-asked because the reviewer kept rejecting
  due to the leftover-state confound below).

Total real-LLM cost for this milestone: **~$0.15**. ai-cockpit's
planner + reviewer LLM calls were not separately metered but are
included in the same APIM session.

### The leftover-state confound (worth remembering)

The graph decision on this run was `ask_human` after `3/3` loops,
NOT `done`. The reason was not any defect in aider's output:

`examples/broken_calc/calc.py` had been modified during the
previous day's §15.1 demo (line `return a - b` flipped to `return
a + b`) and never reset. When the bug-fix workflow's verifier ran
`python -m pytest -q`, `tests/test_demo_fixture.py::
test_calc_add_is_still_broken` failed with:

> "examples/broken_calc/calc.py must keep its intentionally broken
> subtraction body; reset with `git checkout -- calc.py`."

The Claude reviewer correctly diagnosed this:

> "The status subcommand implementation itself looks correct and
> well-tested. The only failure is an unrelated collateral change
> to the demo fixture file that breaks an existing guard test."

Spec §9 anti-deception in action: the reviewer did NOT blame
aider's actual contribution; it pointed at the unrelated dirty
state. After `git checkout -- examples/broken_calc/calc.py` (and
removing aider's own `.aider.*` side-artifacts and a stale
`examples/broken_calc/.ai-cockpit/` directory from yesterday), the
full check chain went green: pytest 108/108, ruff clean, mypy clean
(43 source files).

This surfaces a real v0.4 backlog item: **ai-cockpit should
pre-check `git status` before a real run and warn / refuse when
unrelated files are dirty**, so a stale tree never inflates the
ask_human rate. Filed in `docs/ROADMAP.md` Section B.

### What ai-cockpit's output looked like, end-to-end

The committed `git diff` (post-cleanup) was structurally identical
to what a careful human would write:

- New helpers under appropriate boundaries: `_get_version()`,
  `_count_workflow_files(project_root)`, `_probe_llm_auto()`. Each
  one was named, type-annotated, and docstring'd consistently with
  the rest of the module.
- `_probe_llm_auto()` constructed via `build_llm("auto")` and
  inspected `.name` only — it **never called `.complete()`**.
  Spec §9 invariant preserved by aider's own choice.
- `status_cmd` registered via `@main.command(name="status", ...)`
  with a `--root` option using the same `click.Path(exists=True,
  file_okay=False, dir_okay=True, resolve_path=True)` shape as
  other commands in the same file.
- The new test file (`tests/test_cli_status.py`) initialised a
  temporary git repo with `subprocess.run(["git", "init", ...])`
  before each test, then exercised the command via `CliRunner`,
  asserting exit code 0 and the presence of all six output keys.
  9 tests total, covering every acceptance criterion in ROADMAP
  A.1.

End-user-visible result, run by the human after cleanup:

```text
$ ai-cockpit status --root .
version: 0.1.0
project_root: /proj/.../ai-cockpit
llm_mode_auto: available (anthropic:claude-opus-4-6)
workflows_found: 2
suggestions_pending: 5
checkpoint_db: /proj/.../.ai-cockpit/history/checkpoints.sqlite
```

Every line matches the ROADMAP A.1 contract exactly.

### Honest framing of "how close to a human"

The output was ~90% of what a careful human author would have
written. The 10% differences:

- `except Exception:` in two helpers, where a narrower
  `PackageNotFoundError` (for `_get_version`) and just the
  documented `None` return (for `_probe_llm_auto`) would have
  been tighter. Not wrong; just less surgical.
- `glob` ordering is filesystem-dependent in `_count_workflow_files`;
  a human might have wrapped it in `sorted(...)` for determinism.
  Tests passed regardless, but a wider repo could expose this.
- The test file uses `subprocess.run([...])` for git init instead of
  the project's helper pattern. Not wrong; just a parallel style.

None of these required a follow-up commit. They are observations
worth noting in case v0.4 takes on planner-prompt-side hardening
(ROADMAP B.2 territory).

### What this milestone does NOT establish

- That ai-cockpit can produce **architectural** changes
  (multi-file refactors, new public APIs spanning modules). A.1
  was a single-pattern extension within an existing CLI file.
- That ai-cockpit can recover from **failed verification** by
  iterating beyond the leftover-state case. The 3 loops here
  did not test "real" iteration — aider considered itself done
  after loop 1 and the reviewer was complaining about an unrelated
  file. A future B-section experiment should construct a scenario
  where the reviewer rejects aider's actual edit and aider has to
  revise.
- That ai-cockpit is fit to autonomously process Section B items.
  Section B work continues to require human direction (per
  `V0_3_STATUS.md` operating contract).

### Cross-links

- Code: `src/ai_cockpit/cli.py::_get_version`, `::_count_workflow_files`,
  `::_probe_llm_auto`, `::status_cmd`.
- Tests: `tests/test_cli_status.py` (9 tests).
- PR: nanyang12138/ai-cockpit#31 (squash-merged 2026-05-16 08:44:56Z
  as commit `7a903ab`).
- ROADMAP entry: `docs/ROADMAP.md` Section A.1 (now ✅ DONE).
- Operating contract: `V0_3_STATUS.md` (cron memory) was authorized
  by the user on 2026-05-15 to walk Section A; A.1 was item one of
  that queue.

## 2026-05-16 — B.6 multi-step planner contract authored (no code yet)

**Headline:** the design contract for the largest unshipped v0.3
backlog item — multi-step planning (`docs/ROADMAP.md` B.6) — was
authored in an interactive design conversation with the user and
checked in to `docs/B_6_CONTRACT.md`. No source code under `src/` was
modified; cron is **not** authorized to begin implementation until the
user explicitly signals "open-gate B.6a".

This milestone is logged here rather than under v0.4 because it
captures the **process** by which v0.3-the-project graduates from
single-slice runs to plan-driven execution. The contract itself does
not change runtime behavior; the open-gate signal is what flips B.6
from "deferred" into "in flight".

### Why this is a milestone

Three reasons it's worth a permanent record:

1. **It's the first time the cron / agent contract was negotiated
   end-to-end with the user before any code landed.** Earlier work
   (PRs #3–#34) followed pre-existing contracts in `V0_2_PLAN.md` or
   `docs/ROADMAP.md` Section A. B.6 required the operating layer to
   produce a fresh, accurate, safe spec instead of guessing — and
   then prove (in conversation) that each design choice survived
   user scrutiny.
2. **It locks down the architectural shape of "complex task" support
   for v0.4 and beyond.** B.6 is the load-bearing decision for whether
   ai-cockpit ever takes a complex goal as a single CLI invocation.
   Getting it wrong now would constrain v0.4. Getting it right (as
   reviewed in the conversation) keeps spec §9 and §12 invariants
   intact even when execution grows multi-slice.
3. **It deliberately did NOT borrow swarm / multi-agent / debate
   patterns** despite those being the obvious "more agents = more
   power" temptation. The contract is grounded in the 2025–2026
   multi-agent retrospective literature (Cognition "Don't Build
   Multi-Agents", Anthropic research-system writeup, NeurIPS 2025
   MAST taxonomy, Magentic-One Task Ledger). The single-threaded
   writer + evidence-gated reviewer + persisted task ledger
   structure is the convergent best practice.

### Six design questions and how each one was decided

Each Q was raised by the contract draft, debated with the user, and
resolved with rationale captured both here and in
`docs/B_6_CONTRACT.md` §3.

| # | Resolution | Note |
|---|---|---|
| Q1 — file format | `.plan.yaml` with markdown `\|` multi-line content blocks | YAML for schema safety; markdown blocks preserve human readability. |
| Q2 — CLI shape | New `ai-cockpit plans run <plan_id> <slice_id>` subcommand under the `plans` group; `run` left unmodified | The user explicitly preferred reducing flag-overload on `run`; the cleanest path turned out to be a dedicated subcommand mirroring the existing `memory list/show/accept` group. |
| Q3 — slice count cap | None at schema level | User pushed back on my initial recommendation of 20. Their argument: operational/cognitive risks aren't safety risks. Schema invariants (per-slice budget, scope_out non-empty) are sufficient. |
| Q4 — `--max-slices` default | Flag kept, **default unbounded** | User noticed the inconsistency between "no schema cap" and "default cap of 10" and corrected me. Flag still exists for deliberate use. |
| Q5 — cron authorization for B.6 execution | Two keys: plan merged + `V0_3_STATUS.md` lists `active_plan_id` | Plan-merge proves PR review; status pointer proves operator intent. Status file is not LLM-written, defeating self-authorization via jailbroken plan. |
| Q6 — per-call cost cap on `plan` | Dropped | User pointed out that v0.2/v0.3 don't cap planner/reviewer costs anywhere else; adding it only for `plan` would be inconsistent with the project's posture. Cost stays a user-account concern. |

### Honest framing — what this milestone does NOT establish

- **No source code change** lives in this commit chain. `src/` is
  unmodified. The next cron tick still implements `docs/ROADMAP.md`
  Section A items (A.3 → A.8), not B.6.
- **The contract has not been validated by real implementation.**
  Any of the file budgets in `docs/B_6_CONTRACT.md` §6 may turn out
  to be wrong once a slice is actually being written. The contract
  is the best estimate given v0.2/v0.3 step experience; that's not
  the same as evidence.
- **The two-key authorization model has not been load-tested.** Until
  cron has run at least one B.6 plan against this rule, we cannot
  claim it actually prevents misfire. The §15.1-style end-to-end
  demo is part of B.6's DoD specifically to close this gap.
- **B.6 does not, on its own, deliver "complex task → finished
  product".** It delivers "complex task → reviewable plan + per-
  slice execution gates". The human (or eventually the cron, post-
  open-gate) still has to march through the slices. The improvement
  is that the decomposition is now first-class instead of off-book.

### Cross-links

- Full contract: `docs/B_6_CONTRACT.md`.
- ROADMAP entry (now contract-aware): `docs/ROADMAP.md` Section B.6.
- Multi-agent research underlying the design choices: the 2026-05-16
  research summary delivered to the user in this conversation
  (Cognition's "Don't Build Multi-Agents", Anthropic's "How We Built
  Our Multi-Agent Research System", Microsoft Magentic-One Task
  Ledger paper, MAST NeurIPS 2025, "From Spark to Fire" 2026 paper
  on cascading errors in multi-agent collaboration).
