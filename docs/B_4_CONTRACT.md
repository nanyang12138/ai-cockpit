# B.4 — `--system-prompt FILE` override (contract v0.1, DRAFT)

Status: **draft contract only.** The 2026-05-17 03:57 UTC queue
authorizes cron to *write this contract*; it explicitly does
**not** authorize any change to `src/ai_cockpit/llm/prompts.py`,
`src/ai_cockpit/planner_interactive/prompts.py`, the placeholder
allow-list, or any other implementation surface. The user must
post-review this draft before an implementation PR may be opened.

> Queue position: item #9 of the v0.3 Cursor hardening + v0.4
> startup window. Branch `cursor/v0_4-b4-contract`. Pure-
> documentation deliverable: 2 files / ≤300 net LOC. No code
> under `src/`, no tests touched.

## 1. Why

ai-cockpit ships fixed `PLANNER_SYSTEM` / `REVIEWER_SYSTEM`
strings in `src/ai_cockpit/llm/prompts.py`. Two real-world
needs push back on that: (a) project-specific tone / domain
language (e.g. "always emit pure functions") for the planner
system message; (b) per-project reviewer caveats ("treat any
modified file under `vendor/` as a hard fail") that the spec
deliberately refuses to hard-code. Today the only path is fork
or monkey-patch — too high a barrier for the v0.4 exit-gate
audience (one operator, one repo, one shell).

B.4 is the single smallest hatch: read a text file from disk at
CLI boot, validate it against an allow-list, and substitute it
for the built-in default. The §9 risk is obvious: a hostile or
buggy override file could erase the "judge ONLY structured
evidence" clause. B.4's allow-list is the mitigation.

## 2. Hard invariants (cannot be overridden at implementation time)

These override §3, override "small extra improvement" temptation
at implementation time, and override any judgement call inside
the future implementation PR. If the implementation must violate
one, the gate stays CLOSED and a new contract amendment is
required.

| Invariant | Source | How B.4 honors it |
| --- | --- | --- |
| §9 evidence-only reviewer | spec §9 | The reviewer **user** message is built by `build_reviewer_messages(evidence)` exactly as today; only the **system** message is overridable, and only if the override file passes the allow-list (see §3 Q3). The 5-test `tests/test_anti_deception.py` suite stays byte-identical and is treated as a hard regression gate. |
| §3.2 memory write approval | hard rule §3.2 | Override files live in a project-local path the operator chooses (e.g. `prompts/reviewer.txt`). B.4 never writes to `.ai-cockpit/memory/*`, `.ai-cockpit/suggestions/*`, or back to the override file itself. |
| §12 permanent boundaries | spec §12 | No download from a URL, no plugin marketplace, no auto-discovery from the cloud. The override path must be a local filesystem path resolvable from the CLI invocation cwd. |
| §3.5 no real LLM in CI | AUTOMATION_PROMPT | Override loading is a deterministic file-read + string check. CI uses fixture override files; no LLM call required to test the surface. |
| ≤8 files / ≤400 net LOC per PR | EXECUTION_RULES | Contract (this PR): 2 files / ≤300. Implementation (future PR, separate authorization): ≤5 / ≤300. |
| Override fails closed | new in B.4 | If the override file is missing, unreadable, fails allow-list validation, or exceeds the size cap, the CLI **errors out before any LLM call**. There is no "warn and proceed with default" path — silent fallback would defeat the operator's expectation that their override applies. |
| Built-in default unchanged | EXECUTION_RULES | The shipped `PLANNER_SYSTEM` / `REVIEWER_SYSTEM` constants stay byte-identical. B.4 only adds an opt-in branch around them. Reverting the implementation PR restores the previous behavior cleanly. |
| One gate per cron tick | AUTOMATION_PROMPT §3.3 | This contract PR is queue item #9. Implementation is **not** pre-authorized — it requires a fresh user signal after post-review. |

## 3. Resolved design decisions (Q1–Q5, draft)

These are the **proposed** answers. Unlike the B.3 / B.5 contracts,
they are not user-locked yet; the user must signal acceptance
during post-review. Any item flagged "DEFERRED" stays out of the
future implementation PR until a follow-up contract amendment.

| # | Question | Draft decision | Rationale |
| --- | --- | --- | --- |
| Q1 | What surface does the override expose? | A single CLI flag pair, `--planner-system-prompt FILE` and `--reviewer-system-prompt FILE`, threaded through `ai-cockpit plan`, `ai-cockpit plans run`, and the planner-interactive entrypoint. Each defaults to `None` (use the built-in). The override replaces only the **system** string for the named role; user-message construction is untouched. | Two narrowly-named flags beat one generic `--system-prompt FILE` because the planner and reviewer have different allow-list rules (Q3) and the operator usually wants to override exactly one role at a time. The flag name carries the role so a typo (`--reviewer-system-prompt planner.txt`) does not silently load the wrong file. |
| Q2 | What file format? | Plain UTF-8 text. No YAML front-matter, no JSON wrapper, no template engine. The entire file body, after stripping a single trailing newline, is the new system message. Hard size cap: 8 KiB. | Text is the smallest possible surface. YAML / JSON would add a parser dependency and a second failure mode (parse error). The 8 KiB cap is roughly 8× the built-in `REVIEWER_SYSTEM` and well under the per-call token ceiling B.3's dashboard tracks. |
| Q3 | What does the allow-list enforce? | Per-role placeholder + substring requirements, evaluated **after** loading and **before** any LLM call. (a) **Reviewer override** must contain the literal substring `"structured evidence"` AND must contain `"do not trust"` (case-insensitive on both). Both appear in the built-in `REVIEWER_SYSTEM`; they are the §9 spine. (b) **Planner override** must contain `"strict JSON"` (case-insensitive) so the schema-only reply contract survives. (c) Both must be ≤8 KiB and non-empty after `.strip()`. (d) Neither may contain the literal substring `"coder_result"` (defense against an override that tries to coerce the reviewer back into reading the worker's self-report). Validation failure raises a typed `PromptOverrideError` with the failed rule name; the CLI prints the rule and exits non-zero. | The substring rules are deliberately conservative: they encode the §9 invariants the built-in carries, not stylistic preferences. They are case-insensitive so an operator's rephrasing ("STRUCTURED EVIDENCE") still passes. The `coder_result` blacklist is a belt-and-braces guard — the user message already excludes it, but a reviewer system message that *names* `coder_result` as a thing-to-trust is a §9 red flag. |
| Q4 | How does the override flow into the prompt builders? | Both prompt builders gain an optional kwarg: `build_planner_messages(*, idea, memory_context, system_override: str \| None = None)` and `build_reviewer_messages(evidence, *, system_override: str \| None = None)`. When `None`, they use the existing module-level constants — call sites that pre-date B.4 stay green. When set, the override replaces the system string verbatim; the user string and JSON schema text are untouched. The CLI is the only loader: `_load_prompt_override(path: Path, role: Literal["planner", "reviewer"]) -> str` reads, validates, and returns the body, or raises `PromptOverrideError`. | Optional kwarg with a `None` default is the same pattern B.2 picked for `worker_hints`; the precedent is now consistent. Keeping the loader in the CLI module (or a dedicated `prompts_override.py`) avoids polluting `prompts.py` with file IO. |
| Q5 | How is the change verified without real LLM in CI? | Three test layers: (a) **loader** — fixture files (valid planner, valid reviewer, missing-substring, contains-`coder_result`, oversized, empty) round-trip through `_load_prompt_override` with the expected pass / `PromptOverrideError` outcomes; (b) **prompt-shape** — `build_*_messages(..., system_override="<fixture>")` returns the override verbatim as `system` and leaves the `user` byte-identical to the no-override path; (c) **anti-deception regression** — `tests/test_anti_deception.py` stays byte-identical and runs against both default and override paths (parametrize the override). Real-LLM behavior is observed only when the user runs the B.5 exit gate. | The three layers map 1:1 onto the threat model in §7. The anti-deception parametrization is the load-bearing assertion: the suite must keep passing even when an operator-supplied system message is injected. |

### Why no `Q6` cost / cap question

B.4 carries no cost-cap surface. It only swaps one string in the
prompt; the runtime cost shift per call is bounded by the 8 KiB
override cap (≈ 2k tokens worst case). B.3's dashboard already
shows the per-run total if the operator wants to verify the
impact empirically.

## 4. CLI surface

```text
ai-cockpit plan "<idea>" \
    [--planner-system-prompt FILE] [--reviewer-system-prompt FILE]

ai-cockpit plans run <plan_id> <slice_id> \
    [--planner-system-prompt FILE] [--reviewer-system-prompt FILE]
```

Both flags accept any path Click parses (relative to cwd).
Failure modes the CLI must surface (each exits non-zero, no
traceback): file not found, ≥ 8 KiB, empty after strip, missing
required substring, forbidden `coder_result` substring present.
No env-var equivalent — the flag is the only surface (single
configuration path, single test matrix).

## 5. Data model

```python
@dataclass(frozen=True)
class PromptOverride:
    role: Literal["planner", "reviewer"]
    path: Path
    body: str           # post-validation, post-strip, ≤8 KiB

class PromptOverrideError(RuntimeError):
    """Raised when an override file fails the allow-list."""
    rule: str           # e.g. "missing_required_substring:strict JSON"
    path: Path
```

The `_load_prompt_override` helper returns `PromptOverride` on
success and raises `PromptOverrideError` on any failure. Click
catches `PromptOverrideError` at the CLI boundary and prints the
`rule` field; no traceback is shown to the operator.

## 6. File budget

**Contract (this PR):** 2 files / ≤300 net LOC.

- `docs/B_4_CONTRACT.md` (new) — this document.
- `docs/ROADMAP.md` (mod) — §B.4 stub replaced with a pointer to
  this contract plus a one-line summary, mirroring the §B.2 /
  §B.3 update style.

**Implementation (separate PR, NOT pre-authorized):** ≤5 files /
≤300 net LOC.

- `src/ai_cockpit/llm/prompts_override.py` (new — loader, allow
  -list validator, `PromptOverride` dataclass, `PromptOverride
  Error`; ~90 LOC).
- `src/ai_cockpit/llm/prompts.py` (mod — `system_override`
  kwarg on both builders; ~15 LOC).
- `src/ai_cockpit/planner_interactive/prompts.py` (mod —
  identical kwarg on the interactive builder; ~15 LOC).
- `src/ai_cockpit/cli.py` (mod — wire two flags into both `plan`
  and `plans run`; ~40 LOC).
- `tests/test_prompt_override.py` (new — loader + prompt-shape
  + anti-deception parametrization; ~120 LOC).

`tests/test_anti_deception.py` must remain **byte-identical**.

## 7. Threat model

| Threat | Mitigation |
| --- | --- |
| Operator supplies a reviewer override that drops the "judge ONLY structured evidence" clause (§9 deception) | Allow-list rule Q3 (a): override must contain `"structured evidence"` AND `"do not trust"` (case-insensitive). Without both, `_load_prompt_override` raises before any LLM call. |
| Reviewer override coaxes the model to read the worker's narrative | Allow-list rule Q3 (d): the literal substring `"coder_result"` is forbidden in any override body. Combined with `build_reviewer_messages`'s unchanged user message, the LLM has no path to receive coder narrative. |
| Operator supplies an override that strips the `"strict JSON"` instruction so the planner emits prose | Allow-list rule Q3 (b): planner override must contain `"strict JSON"` (case-insensitive). Same fail-closed semantics. |
| Override file points to `/etc/passwd` or a giant binary blob | Size cap Q2: ≥ 8 KiB → reject. Empty after strip → reject. UTF-8 decode failure → reject. The loader does not follow symlinks recursively; Path.read_text handles it. |
| Override path is interpreted as a URL or remote location | The implementation accepts only `pathlib.Path` resolvable from cwd. No `http://` / `https://` / `s3://` prefix support. §12 boundary. |
| Implementation accidentally bakes the override into the checkpoint DB / memory | The override is never written to `TaskState`, `WorkerResult.metrics`, the checkpoint DB, `.ai-cockpit/memory/*`, or `.ai-cockpit/suggestions/*`. It is a per-process kwarg that lives in memory for the duration of one CLI invocation. The B.3 cost dashboard remains unaware of it. |
| Multiple concurrent runs use different overrides and corrupt each other | Each `ai-cockpit` invocation is a fresh process; overrides are per-process kwargs only. Cross-process state lives in the SqliteSaver checkpoint DB, which receives no override-derived bytes. |
| Future planner/reviewer wiring (e.g. cursor backend) forgets to thread the kwarg | The CLI layer is the only loader; the kwarg flows into `build_*_messages` which is the chokepoint shared by both v0.2 and B.9 interactive paths. Cursor backend planner/reviewer share the same prompt builders, so threading happens automatically once the kwarg is added. |
| Anti-deception suite drifts | `tests/test_anti_deception.py` stays byte-identical. The new `tests/test_prompt_override.py` parametrizes the existing reviewer assertions with both default and override fixtures. |

## 8. DoD

**Contract done (this PR) when:**

1. `docs/B_4_CONTRACT.md` is merged to master.
2. `docs/ROADMAP.md` §B.4 stub is replaced with a pointer to
   this contract plus a one-line summary.
3. Pre-push 4 checks pass: `pytest`, `ruff check .`, `mypy .`,
   `ai-cockpit "smoke b4-contract" --max-loops 1 --dry-run
   --llm none --no-checkpoint`.
4. No source under `src/` modified; no test added/removed.

**Implementation done (future, separate PR after user signal) when:**

1. `src/ai_cockpit/llm/prompts_override.py` ships the loader,
   `PromptOverride`, `PromptOverrideError`, and the allow-list
   validators per Q3.
2. Both prompt builders accept `system_override: str | None =
   None` and substitute it for the system string when set.
3. The CLI wires `--planner-system-prompt FILE` and
   `--reviewer-system-prompt FILE` into `plan` and `plans run`,
   loading the file via `_load_prompt_override` and exiting
   non-zero on `PromptOverrideError`.
4. 5-test §9 anti-deception suite remains byte-identical and
   green on both default and override paths.
5. New `tests/test_prompt_override.py` covers loader fixtures
   + prompt-shape + anti-deception parametrization.
6. Pre-push 4 checks pass; ≤5 / ≤300 budget respected.

## 9. Out of scope for B.4

- No reviewer **user-message** override — that surface is the
  §9 evidence shape and stays code-defined.
- No planner / reviewer **schema** override (`PLANNER_SCHEMA`,
  `REVIEWER_SCHEMA`). The schema is part of the JSON-only
  reply contract; loosening it is its own gate.
- No URL-based override loading (no `http://`, no `s3://`),
  no plugin marketplace, no community prompt index — §12.
- No template engine (`{idea}`, `{memory_context}` interpolation
  inside the override body). The override IS the system string;
  user-message variables stay where they are.
- No env-var equivalent (`AI_COCKPIT_PLANNER_SYSTEM_PROMPT`).
  CLI flag only — single configuration path.
- No memory-driven override learning. The planner does not
  write back to the override file based on reviewer rejects.
- No automatic override discovery from project root (`.ai-
  cockpit/prompts/reviewer.txt` auto-load). Operators pass an
  explicit path each time.
- No precedence-merging (e.g. "append override after default").
  Replace-or-default only.
- No rendering of the override into the B.3 cost dashboard or
  the checkpoint DB. Overrides do not leave the process.

## 10. Rollback

If the implementation PR proves harmful:

1. Revert the implementation PR. Contract (this file) stays as
   historical record.
2. Existing planner / reviewer call sites continue to work: the
   `system_override` kwarg defaults to `None` and is opt-in;
   reverting removes it cleanly.
3. The shipped `PLANNER_SYSTEM` / `REVIEWER_SYSTEM` constants
   are byte-identical pre- and post-revert.

## 11. Authorization & operating rhythm

Per the 2026-05-17 03:57 UTC user-locked authorization:

1. **Contract draft only.** This document and the
   `docs/ROADMAP.md` §B.4 pointer are the only B.4 deliverables
   of the current cron tick (queue item #9). Source under
   `src/` MUST NOT be touched in this PR.
2. **Implementation is NOT pre-authorized.** B.4 requires a
   separate user signal after post-review of this draft. Cron
   must STOP and OQ if it sees an implementation PR open
   against this contract without that signal.
3. **One tick, one gate.** Even after the user opens the
   implementation gate, cron ships it on a later tick (queue
   item promotion, not same-tick chaining).

## 15. Open-gate protocol

```text
open-gate B.4 contract (draft)        # granted by the 2026-05-17
                                      # 03:57 UTC prompt body;
                                      # this PR is the deliverable.
open-gate B.4 implementation          # NOT granted — requires a
                                      # fresh user signal after
                                      # post-reviewing this draft.
open-gate B.4 reviewer-user-message   # NEVER GRANTED — §9 boundary;
                                      # the evidence shape stays
                                      # code-defined.
open-gate B.4 url-or-plugin-loaded    # NEVER GRANTED — §12 boundary.
open-gate B.4 schema-override         # NEVER GRANTED in v0.4 —
                                      # would need its own contract.
```

A future `open-gate B.4 implementation` signal must reference the
specific Q-row in §3 that the implementation addresses (and any
that it explicitly defers). Without that reference, cron treats
the signal as ambiguous and stops with an OQ entry.
