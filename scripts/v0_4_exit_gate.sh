#!/usr/bin/env bash
#
# v0.4 exit-gate operator runbook (B.5 contract §4).
#
# Walks a human operator through the v0.4 exit-gate run on
# examples/broken_calc. **Operator-driven only** (per B.5 contract §11
# and AUTOMATION_PROMPT.md §3.5): cron must NOT execute this script.
#
# Usage:
#   bash scripts/v0_4_exit_gate.sh [--worker aider|cursor]
#
# Prerequisites (script checks each before continuing):
#   - cwd is an ai-cockpit checkout on master at a clean tip
#   - .venv exists and is the active Python env (sources it for you)
#   - ANTHROPIC_API_KEY or OPENAI_API_KEY is exported
#   - aider-chat installed when --worker aider (default)
#   - cursor agent installed AND --worker cursor passed (optional path)
#   - examples/broken_calc working tree is clean (no .aider* leftovers)
#
# Hard caps (B.5 contract §3 Q4, AND-relation):
#   (1) total cost ≤ $1 USD per run (operator reads from `ai-cockpit cost`)
#   (2) wall-time ≤ 15 min (script prints elapsed time)
#   (3) human interventions = 0 (script never prompts mid-loop)
#   (4) pytest 100% green at end (script runs pytest twice)
#
# This script DOES NOT auto-fill docs/V0_4_EXIT_EVIDENCE.md. The
# operator pastes the printed evidence-shaped output into the template
# at the end. Cron / CI never run this script.

set -euo pipefail

WORKER="aider"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --worker) WORKER="${2:-aider}"; shift 2;;
    --help|-h)
      sed -n '2,30p' "$0"; exit 0;;
    *) echo "unknown flag: $1" >&2; exit 2;;
  esac
done

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

step() { echo; echo "==> $*"; }
require() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1" >&2; exit 1; }; }
fail() { echo "FAIL: $*" >&2; exit 1; }

step "preflight: git state"
[[ "$(git symbolic-ref --short HEAD)" == "master" ]] || fail "must be on master"
git diff --quiet || fail "master working tree is dirty"

step "preflight: python env"
[[ -f .venv/bin/activate ]] || fail "no .venv at $REPO_ROOT/.venv"
# shellcheck disable=SC1091
source .venv/bin/activate

step "preflight: LLM creds"
if [[ -z "${ANTHROPIC_API_KEY:-}" && -z "${OPENAI_API_KEY:-}" ]]; then
  fail "set ANTHROPIC_API_KEY or OPENAI_API_KEY before running"
fi

step "preflight: worker tooling ($WORKER)"
case "$WORKER" in
  aider) require aider;;
  cursor) require cursor;;
  *) fail "--worker must be aider or cursor; got '$WORKER'";;
esac

step "preflight: examples/broken_calc clean"
[[ -d examples/broken_calc ]] || fail "examples/broken_calc not found"
( cd examples/broken_calc && git status --porcelain examples/broken_calc 2>/dev/null | grep -q . ) && \
  fail "examples/broken_calc has uncommitted leftovers (rm .aider*?)"

step "baseline: pytest (top-level) before run"
BASELINE_TESTS="$(python -m pytest --collect-only -q 2>/dev/null | tail -1 | awk '{print $1}')"
echo "baseline test count: $BASELINE_TESTS"

step "v0.4 step 1/3: interactive plan"
echo "Action required (interactive):"
echo "  ai-cockpit plan 'fix examples/broken_calc so pytest passes end-to-end' \\"
echo "    --root examples/broken_calc --llm auto"
echo "  then /save when satisfied."
echo
read -r -p "Press ENTER when /save has produced docs/plans/<plan_id>.plan.yaml (or Ctrl-C to abort): "

step "list saved plans"
ai-cockpit plans list --root examples/broken_calc

read -r -p "plan_id : " PLAN_ID
read -r -p "slice_id: " SLICE_ID
[[ -n "$PLAN_ID" && -n "$SLICE_ID" ]] || fail "plan_id/slice_id required"

step "v0.4 step 2/3: plans run --worker $WORKER --apply --llm auto"
START_TS="$(date +%s)"
time ai-cockpit plans run "$PLAN_ID" "$SLICE_ID" \
  --root examples/broken_calc \
  --worker "$WORKER" --apply --llm auto

END_TS="$(date +%s)"
ELAPSED=$(( END_TS - START_TS ))
echo "elapsed: ${ELAPSED}s (Q4 cap = 900s)"
(( ELAPSED <= 900 )) || echo "WARNING: exceeded Q4 (2) 15-min wall-time cap"

step "v0.4 step 3/3: memory accept"
ai-cockpit memory list --root examples/broken_calc
read -r -p "suggestion_id to accept: " SUGGESTION_ID
[[ -n "$SUGGESTION_ID" ]] || fail "suggestion_id required (Q1 requires ≥1 done suggestion)"
ai-cockpit memory accept "$SUGGESTION_ID" --root examples/broken_calc

step "post-run: pytest at broken_calc must pass"
( cd examples/broken_calc && python -m pytest -q ) || fail "Q4 (4) broken_calc pytest failed"

step "post-run: top-level pytest must stay green"
python -m pytest -q | tail -3

step "Q4 evidence: cost + git log"
ai-cockpit cost --root examples/broken_calc --format text || \
  echo "WARNING: ai-cockpit cost subcmd returned non-zero"
echo
git -C examples/broken_calc log --oneline -5

cat <<EOF

==> Gate metrics summary (paste into docs/V0_4_EXIT_EVIDENCE.md):

  worker          : $WORKER
  elapsed_seconds : $ELAPSED        (Q4 (2) cap = 900)
  baseline_tests  : $BASELINE_TESTS
  plan_id         : $PLAN_ID
  slice_id        : $SLICE_ID
  suggestion_id   : $SUGGESTION_ID
  cost_usd        : <copy from \`ai-cockpit cost\` output above; Q4 (1) cap = 1.00>
  human_actions   : <count ENTERs you pressed; Q4 (3) target = 0 mid-loop>

EOF
