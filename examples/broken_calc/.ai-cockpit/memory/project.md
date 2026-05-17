## 2026-05-17 — # Fix bugs in broken_calc so all pytest tests pass

## Why
The broken_calc example is intentionally broken to demonstrate AI Cockpit workflows. We need to identify the bugs in the calculator implementation and fix them so the test suite passes end-to-end.

## Scope (must)
- Read the test files to understand what behavior is expected
- Read the source files to identify the bugs
- Fix all bugs in the calculator source code so tests pass
- Ensure pytest -v exits with code 0

## Scope (out)
- Adding new tests beyond what already exists
- Refactoring code style or structure beyond what is needed to fix bugs
- Modifying test files to weaken assertions

## Definition of done
- pytest -v passes with exit code 0
- No tests are deleted or skipped
- Only source (non-test) files are modified

## Background (do not treat as positive evidence)
Fix the examples/broken_calc project so that pytest passes end-to-end

Trailing commit marker (include verbatim in commit): [fix-broken-calc/diagnose-and-fix] from docs/plans/fix-broken-calc.plan.yaml

- decision: done
- mvp_spec: Read the test files under the examples/broken_calc project to determine expected calculator behavior (likely basic arithmetic: add, subtract, multiply, divide). Read the corresponding source files to identify intentional bugs such as wrong operators, off-by-one errors, or incorrect return values. Fix each bug in the source (non-test) files so that every existing pytest test passes. Validate by running pytest -v and confirming exit code 0. No tests should be added, deleted, skipped, or weakened.
