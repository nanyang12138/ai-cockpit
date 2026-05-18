# V0.5 Row #10 — `cli-ergonomics-project-config` contract (v0.1, DRAFT — Q-table pending user lock)

Status: **draft, NOT locked.** The §3 Q-table records cron's
recommendations but is **not** authorised. User must lock the
Q-answers (per row, or "accept all cron recommendations") before
this document becomes the implementation gate.

> Pure-documentation deliverable: 2 files / ≤350 net LOC. No code
> under `src/`, no tests touched.

## 0. Origin

This row is **not** in the original `docs/V0_5_ROADMAP.md` (PR
#86), which catalogued 9 *agent-paradigm* deficiencies in the
graph layer. Row #10 was surfaced on **2026-05-18 ~02:39 UTC**
during the first real-user-style conversation about the tool, by
the project owner acting in user role:

> "我看到 option 需要添加的很多, 要加那些, 不加哪些, 这对我来说,
> 或者对于用户来说是个负担. 他们不知道怎么开始." → "我看到这个
> 了里面有这么多 option 就头大. 那对于刚开始接触这个工具的人呢,
> 他们看到之后还会用这个工具吗?"

This is a different *class* of deficiency from rows #1–#9: not an
agent-paradigm gap but a **CLI ergonomics / onboarding gap**. Per
AUTOMATION_PROMPT §3.1, cron cannot self-add it to ROADMAP. This
contract is the STOP-and-OQ response, drafted under the user's
verbatim 2026-05-18 03:23 UTC authorisation: *"可以 先起草
contract 然后再决定要不要开始"* — which authorises this file +
the ROADMAP pointer only, **not** any implementation gate and
**not** any Q-lock.

## 1. Why

`ai-cockpit run` exposes 14 flags, `ai-cockpit plan` exposes 8.
Each individual default is defensible from a spec-§9 / §3.2 /
§12 standpoint, but the composed UX requires 3–6 flags for every
real-LLM real-worker run, with no CLI-side signal of which 3–6
those are. A daily script today:

```bash
ai-cockpit run "fix the failing test" \
    --workflow .ai-cockpit/workflows/bug-fix.yaml \
    --llm auto --worker aider --apply \
    --thread-id "daily-fix-$(date +%Y%m%d)" \
    --max-loops 2
```

Six flags, three of which (`--llm`/`--worker`/`--apply`) are the
same on every real run, two more (`--workflow`/`--max-loops`)
project-stable. Only `--thread-id` and the idea-string vary.

Consequences: (a) first-touch cliff — no way to discover the
canonical combination from `--help`; (b) recurring-task friction
— every cron / shell-alias wrapper re-encodes the same
combination, drift-prone across machines.

Row #10 introduces a project-level config file
(`.ai-cockpit/config.yaml`) that stores the operator's defaults
once. Daily invocations become `ai-cockpit run "fix the failing
test"`. Flags remain available as **explicit overrides**.

Front-loading row #10 in Phase-2 implementation order unblocks
operator real-usage data collection, which rows #1/#2/#3/#5 all
depend on for prioritisation calibration.

## 2. Hard invariants

| Invariant | Source | How row #10 honours it |
|---|---|---|
| §9 evidence-only reviewer | spec §9 | Config contents never reach `build_reviewer_messages`. The config layer sits **above** the graph — it informs which flags reach the graph, it is not a graph node. The 5-test anti-deception suite stays byte-identical. |
| §3.2 memory write approval | hard rule §3.2 | Config is operator-authored. `ai-cockpit init` (sub-gate b) writes only when the operator runs the wizard interactively and confirms. `.ai-cockpit/memory/*` is not touched. |
| §12 permanent boundaries | spec §12 | No daemon, no UI, no cloud backend. `init` is a one-shot interactive subcommand. |
| Operator override always wins | this contract §3 Q3 | CLI flag explicitly passed always overrides config. Operator can force any behaviour exactly as today. |
| Config absent → unchanged | this contract §3 Q4 | When `.ai-cockpit/config.yaml` is absent OR malformed, behaviour is byte-identical to pre-row-#10 master. No opportunistic auto-detection. Convenience is opt-in. |
| LLM credentials NEVER in config | this contract §3 Q5 | Loader rejects `LLM_API_KEY` / `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `LLM_API_EXTRA_HEADERS` keys with typed error. Caught before any LLM call surface. |
| Backwards compatibility | EXECUTION_RULES | Existing 301-test baseline stays 301-passing without modification. No CLI-flag signature change. |
| ≤8 files / ≤400 net LOC per PR | EXECUTION_RULES | Contract (this PR): 2 files / ≤350. Impl (future): split a (≤4 / ≤200) + b (≤3 / ≤180). |

## 3. Open questions (cron recommendations — awaiting user lock)

| # | Question | Cron recommendation | User answer |
|---|---|---|---|
| Q1 | Config file path | `.ai-cockpit/config.yaml` — project-scoped, alongside existing `workflows/` and `memory/`. Not user-scoped (no XDG). | |
| Q2 | Format | YAML (matches workflow files; no new parser dependency). | |
| Q3 | Precedence order | **CLI flag > workflow YAML > project config > built-in default.** First layer that explicitly sets a key wins. | |
| Q4 | When `config.yaml` is absent | **Byte-identical to current master.** No auto-detection from installed deps. Convenience is opt-in only. | |
| Q5 | LLM credentials in config | **Forbidden.** Loader raises on any `LLM_*` / `ANTHROPIC_*` / `OPENAI_*` key. Env-only, as today. | |
| Q6 | `apply: true` allowed in config? | **Allowed**, but loader emits a stderr warning on every load reminding the operator that aider/cursor will modify files by default. Removing the row defeats the point. | |
| Q7 | Config committed to git? | **Yes** (`config.yaml` is project-shared). Optional `config.local.yaml` for per-operator overrides — same schema, gitignored. Loader appends `**/.ai-cockpit/config.local.yaml` to `.gitignore` idempotently on bootstrap. | |
| Q8 | Workflow simple-name? | **Yes:** `workflow: bug-fix` (no `/`, no `.yaml`/`.yml` suffix) resolves to `<root>/.ai-cockpit/workflows/bug-fix.yaml`. Literal paths still work. | |
| Q9 | Ship `ai-cockpit init` in same PR as loader? | **No.** Sub-gate a = loader + CLI fallback + loader tests. Sub-gate b = `init` wizard + tests. Independently mergeable; b depends on a. | |
| Q10 | Per-subcommand defaults (separate `run.defaults`, `plan.defaults`)? | **Out of scope.** Single `defaults:` block; loader silently ignores irrelevant keys per subcommand. Revisit if real evidence accumulates. | |

## 4. Data model

### 4.1 Config schema (schema_version 1)

```yaml
schema_version: 1
defaults:
  llm: auto                    # none|auto|anthropic|openai
  worker: aider                # stub|aider|cursor
  apply: true                  # bool
  workflow: bug-fix            # simple-name OR path
  max_loops: 2                 # 0..10
  mode: task                   # exploration|task
  reviewer: builtin            # builtin|cursor
  backend: builtin             # builtin|cursor (plan only)
  suggest: true                # bool
  allow_dirty_tree: false      # bool
```

All `defaults:` keys are optional. Absent → fall through to next
precedence layer (§4.3).

**Rejected keys** (typed loader error): any `LLM_*` / `ANTHROPIC_*` /
`OPENAI_*` credential (Q5); `thread_id` / `thread_id_template`
(per-run); `root` (operator-invocation context); `test_command(s)`
(belong in workflow YAML); `checkpoint_db` / `dry_run` (per-run
debug knobs).

### 4.2 Local override file

`.ai-cockpit/config.local.yaml` — identical schema, loads after
`config.yaml`, same-key wins. Auto-gitignored (Q7).

### 4.3 Precedence resolution

For each flag on `run` / `plan`:

```
value = (
    cli_explicit_flag                      # ctx.get_parameter_source() == COMMANDLINE
    or workflow_yaml_value
    or project_config_local_value          # .ai-cockpit/config.local.yaml
    or project_config_value                # .ai-cockpit/config.yaml
    or built_in_default
)
```

"Operator explicitly passed it" uses Click's
`ctx.get_parameter_source()`. Click-default-resolved flags are NOT
treated as "operator passed".

### 4.4 Stderr surface

At most three info/warning lines per run:

1. `info: loaded defaults from .ai-cockpit/config.yaml` (and `+ ...local.yaml` if present)
2. (if resolved `apply == true`) `warning: project config sets apply=true; every aider/cursor run will modify files by default. Pass --no-apply or remove from config to invert.`
3. Malformed config: single `error: ...` line, run continues with built-in defaults (graceful degrade, no hard fail). Same model as `LLM_API_EXTRA_HEADERS` parse error today.

## 5. CLI surface

### 5.1 Existing flags unchanged

The 14 flags on `run` and 8 on `plan` keep their signatures.
Their *effective defaults* now come from the precedence chain
(§4.3).

### 5.2 New subcommand `ai-cockpit init` (sub-gate b)

Interactive wizard, ≤6 prompts, writes `.ai-cockpit/config.yaml`.
Refuses to overwrite existing file unless `--force` (which backs
up to `config.yaml.bak.<timestamp>`). Does NOT prompt for
credentials. Prints env-var reminder banner on exit. Recommends
the next step `ai-cockpit status` to verify load.

### 5.3 `ai-cockpit status` extension

Reports: config file presence + schema_version; local override
presence; effective resolved values per key with source marker
(`C` CLI, `W` workflow YAML, `L` local, `P` project, `D` default).
The `apply: true` warning also surfaces here.

## 6. File budget

**Contract (this PR):** 2 files / ≤350 net LOC.

- `docs/V0_5_ROW_10_CLI_ERGONOMICS_CONTRACT.md` (new — this file).
- `docs/V0_5_ROADMAP.md` (mod — Bucket A table entry, §3 framing
  9 → 10 deficiencies, §4 Row #10 entry, §5 sequencing, §6
  open-gate protocol).

**Sub-gate a — config loader + CLI fallback (future PR, NOT pre-authorised):** ≤4 files / ≤200 LOC.

- `src/ai_cockpit/project_config.py` (new — `ProjectConfig`
  dataclass + loader + precedence + warning policy; ~120 LOC).
- `src/ai_cockpit/cli.py` (mod — `ctx.get_parameter_source()`
  wiring on `run`/`plan` flags; ~40 LOC).
- `src/ai_cockpit/nodes/intake.py` or status surface (mod —
  resolved-defaults reporting; ~20 LOC).
- `tests/test_project_config.py` (new — schema validation,
  precedence, malformed degrade, credential rejection,
  apply-warning emission; ~20 LOC).

**Sub-gate b — `ai-cockpit init` (future PR, NOT pre-authorised):** ≤3 files / ≤180 LOC.

- `src/ai_cockpit/cli.py` (mod — `init` subcommand via
  `click.prompt`; ~80 LOC).
- `src/ai_cockpit/project_config.py` (mod —
  `ProjectConfig.write_yaml()` + `.gitignore` append helper;
  ~30 LOC).
- `tests/test_init_subcommand.py` (new — `CliRunner` with
  simulated stdin; ~70 LOC).

Sub-gate b strictly depends on a being merged.

## 7. Threat model

| Threat | Mitigation |
|---|---|
| Operator commits `apply: true` and a teammate gets a surprise edit on fresh checkout | (a) Loader stderr-warns every run when resolved `apply == true` (Q6); (b) `ai-cockpit status` shows resolved value + source; (c) `init` wizard defaults `apply` to **No**. |
| Operator pastes `LLM_API_KEY` into config and commits | Loader raises `ProjectConfigError` on any `LLM_*`/`ANTHROPIC_*`/`OPENAI_*` key, refusing to run, with typed message. Caught before any LLM-call surface. Asserted in tests. |
| Malformed YAML hard-fails every CLI invocation | Loader catches `yaml.YAMLError` + schema-validation errors, emits `error:` line, proceeds with built-in defaults. Same model as `LLM_API_EXTRA_HEADERS` today. |
| Config silently overrides flag the operator passed | Click `ParameterSource.COMMANDLINE` check; only `COMMANDLINE`-source flags suppress config. Default-source flags defer. Testable. |
| `workflow: bug-fix` collides with a literal cwd file called `bug-fix` | Simple-name resolution (Q8) only fires when value has no `/` AND no `.yaml`/`.yml` suffix. Literal-path users include the extension. |
| `init` overwrites a carefully-tuned existing config | Refuses without `--force`; with `--force` backs up to `config.yaml.bak.<timestamp>` before writing. |
| `apply: true` warning becomes background noise | One-liner per run. If too noisy, operator removes the key from config and passes `--apply` on CLI. Friction is intentional. |

## 8. DoD

**Contract (this PR) done when:**

1. This file is merged to master.
2. `docs/V0_5_ROADMAP.md` Bucket A includes Row #10 with pointer
   to this file. §3 framing reads "10 deficiencies (9
   agent-paradigm + 1 ergonomics, surfaced 2026-05-18)".
3. Pre-push 4 checks pass: `pytest`, `ruff check .`, `mypy .`,
   smoke `ai-cockpit run "smoke row-10-contract" --max-loops 1
   --no-checkpoint`.
4. No source under `src/` modified; no test added/removed.

**Sub-gate a (future PR after `open-gate v0.5-row-10-impl-a`) done when:**

1. `ProjectConfig` + loader at `src/ai_cockpit/project_config.py`.
2. CLI flag resolution uses precedence chain (§4.3) via
   `ctx.get_parameter_source()`.
3. `ai-cockpit status` reports resolved defaults with source
   markers.
4. New tests cover: schema-valid load; malformed-YAML graceful
   degrade; credential keys rejected; `apply: true` warning
   emission; precedence (CLI > workflow > local > project >
   built-in); simple-name workflow resolution; absent-file silent
   fall-through.
5. Pre-push 4 checks green; ≤4 files / ≤200 LOC. 301-baseline
   stays 301-passing.

**Sub-gate b (future PR after `open-gate v0.5-row-10-impl-b` AND sub-gate a merged) done when:**

1. `init` subcommand prompts the 6 questions; output YAML
   round-trips through sub-gate-a loader.
2. `--force` backs up existing config before overwrite.
3. `init` refuses credentials, prints env-var reminder banner.
4. `.gitignore` append for `**/.ai-cockpit/config.local.yaml` is
   idempotent.
5. ≤3 files / ≤180 LOC.

## 9. Out of scope

- User-scoped config (`~/.config/ai-cockpit/`).
- Multi-project inheritance (`extends:`).
- Per-subcommand sections (Q10).
- Auto-detection from installed deps (Q4 invariant).
- JSON / TOML alternative formats.
- Env-var interpolation inside config (`${MAX_LOOPS:-2}`).
- `ai-cockpit doctor` / lint-config subcommand.
- Hot-reload during `--resume`.
- Replacing flags entirely. Config only changes *defaults*.

## 10. Rollback

If sub-gate a is harmful: revert; existing config.yaml files
become inert (pre-row-#10 CLI ignores them); no data corruption.
Sub-gate b auto-blocks. If sub-gate b is harmful: revert;
operators can still hand-author config per §4.1.

## 11. Authorisation & operating rhythm

Per the 2026-05-18 03:23 UTC user authorisation:

1. **Contract draft only.** This PR ships this file + ROADMAP
   pointer. No `src/` touched, no Q-answer locked.
2. **Q-lock signal required before any impl gate.** User
   responds with explicit Q-answers (or "accept all cron
   recommendations"). Cron updates §3 "User answer" column and
   flips status header from `DRAFT` to `LOCKED` in a follow-up
   doc-only PR. Impl gates a and b are blocked until that PR
   merges.
3. **Per-spec rhythm.** `docs/V0_5_ROADMAP.md` §5 already
   gates v0.5 rows on V0_4 evidence merged on master (now
   satisfied via PR #89) AND per-row `open-gate` signals.

## 12. Open-gate protocol

```text
open-gate v0.5-row-10-contract              # granted 2026-05-18 03:23 UTC;
                                            # this PR is the deliverable.
open-gate v0.5-row-10-lock                  # NOT granted — needs §3 Q1–Q10
                                            # answers (or "accept all cron
                                            # recommendations").
open-gate v0.5-row-10-impl-a                # NOT until row-10-lock merged.
open-gate v0.5-row-10-impl-b                # NOT until impl-a merged.

open-gate v0.5-row-10-credentials-in-config # NEVER — §2 Q5 invariant.
open-gate v0.5-row-10-auto-detect-defaults  # NEVER — §2 Q4 invariant.
open-gate v0.5-row-10-user-scoped-config    # NEVER in v0.5; future row.
```

A future `open-gate v0.5-row-10-lock` signal must explicitly
reference §3's Q1–Q10 (with per-row answers or "accept all
cron recommendations verbatim"). Otherwise cron stops with an
OQ entry per `AUTOMATION_PROMPT.md` §4.

## 13. Cross-links

- **Surfacing chat:** 2026-05-18 ~02:39 UTC. Verbatim quote §0.
- **v0.4 ergonomics seeds:** `docs/V0_4_EXIT_EVIDENCE.md` §11
  records 8 prior ergonomics findings (LLM_*↔ANTHROPIC_*
  duplication, runbook UX gaps, B.2 hint budget, plan_id slug
  drift, parallel cloud-agent dup, B.5 §4 commit step,
  pytest-cwd confusion, scripts/v0_4_exit_gate.sh awk bug). Row
  #10 fixes several at the *system* level by making "what flags
  do I need" answerable once per project rather than once per
  invocation.
- **Spec invariants:** `docs/AI_COCKPIT_SPEC_V1.md` §9, §3.2,
  §12.
