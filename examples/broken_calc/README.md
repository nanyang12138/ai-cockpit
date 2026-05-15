# `broken_calc` — spec §15.1 end-to-end demo fixture

This directory contains a deliberately broken Python module
(`calc.py`) and a failing pytest (`test_calc.py`). It exists so the
spec §15.1 scenario ("failing test → green via real worker") can be
reproduced on demand with a single ai-cockpit invocation.

The companion `tests/` directory in the repo root is NOT affected;
pytest's `testpaths = ["tests"]` excludes this fixture from the main
suite, so the broken state lives here permanently without breaking CI.

## What's broken

```python
# calc.py
def add(a: int, b: int) -> int:
    return a - b   # BUG — should be a + b
```

`test_calc.py::test_add_works` calls `add(2, 3)` and asserts the
result equals `5`. Right now it fails.

## How to demo

You need: a Python 3.12 venv with `ai-cockpit` and `aider-chat`
installed, plus the AMD APIM env vars (or any other LLM endpoint
configured via `LLM_API_KEY` / `LLM_API_BASE` / `LLM_MODEL_NAME` /
`LLM_API_EXTRA_HEADERS`). See the top-level `README.md` "LLM
configuration" section for the env shape.

Run from this directory:

```bash
cd examples/broken_calc
python -m pytest -q                         # confirm: test fails
ai-cockpit "make tests/test_calc.py pass by fixing calc.py" \
    --workflow ../../.ai-cockpit/workflows/bug-fix.yaml \
    --worker aider --apply \
    --llm auto
python -m pytest -q                         # confirm: test passes
```

If the run produces `decision: done`, you have just observed:

- spec §15.1 (failing test → green via real worker) end-to-end
- spec §15.3 (vague natural-language idea → concrete spec/slice)
- spec §9 (reviewer judges only on structured evidence; aider's
  prose self-report is NOT trusted)

## How to reset for another demo run

```bash
git checkout -- calc.py
python -m pytest -q   # back to the failing state
```

Aider may also touch `.aider*` artifacts; remove them if they
appear (`rm -rf .aider*`). The repo's top-level `.gitignore` already
ignores `.ai-cockpit/suggestions/`; the `--no-gitignore` flag that
`AiderWorker` passes by default keeps aider from auto-editing your
gitignore.

## Why this fixture matters (and why it's tiny)

The real-LLM run of 2026-05-15 (archived in
`docs/V0_2_COMPLETION.md`) showed the full pipeline working against
a one-line README edit. This fixture extends the same evidence to a
SHELL-VERIFIABLE outcome: pytest's exit code, not just visual
inspection, decides whether the demo succeeded. The bug is one line
so aider's smallest possible edit fixes it; the second test
(`test_mul_unchanged`) guards against over-eager rewrites that
touch unrelated code.
