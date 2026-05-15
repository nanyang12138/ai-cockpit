"""pytest fixture for the §15.1 ai-cockpit demo.

Not collected by the main test suite (pyproject's
``testpaths = ['tests']`` scopes pytest discovery to ``tests/`` only).
Run from this directory with ``python -m pytest -q`` to confirm the
demo state: ``test_add_works`` should fail until ai-cockpit fixes
``calc.add``.
"""

from __future__ import annotations

from calc import add, mul


def test_add_works() -> None:
    assert add(2, 3) == 5
    assert add(-1, 1) == 0
    assert add(0, 0) == 0


def test_mul_unchanged() -> None:
    # Sanity check — multiplication must NOT regress while ai-cockpit
    # fixes add(). This catches over-eager edits.
    assert mul(2, 3) == 6
    assert mul(-2, 3) == -6
