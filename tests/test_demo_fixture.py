"""Guard test for the §15.1 demo fixture in examples/broken_calc/.

The fixture exists so the spec §15.1 scenario ("failing test → green
via real worker") can be reproduced on demand. These guards assert
the fixture's shape — files present, ``add`` defined, expected
``test_add_works`` assertion present — without pinning whether
``add`` is currently in its broken or its fixed state.

Historical note (Bug A, surfaced 2026-05-17 v0.4 exit-gate attempt 3):
this module used to contain ``test_calc_add_is_still_broken`` which
asserted ``"return a - b" in calc.py``. That guard was a v0.3 §15.1
demo-era safeguard, written before v0.4's exit-gate workflow existed.
The v0.4 gate's whole purpose is to drive ``ai-cockpit plans run`` to
fix ``calc.py`` end-to-end — but the anti-fix guard then forced the
real worker to also rewrite this module to make the suite green,
which violated the planner's ``scope_out`` constraint and triggered
the reviewer's §9 rejection. Removing the anti-fix guard resolves
that v0.3/v0.4 contradiction; demo-ability is now protected by:

* ``examples/broken_calc/README.md`` "How to reset for another demo
  run" (``git checkout -- calc.py``).
* The single-line nature of the bug (one ``-`` ↔ ``+`` toggle).
* ``examples/broken_calc/test_calc.py::test_mul_unchanged`` which
  guards against over-eager rewrites that touch unrelated code.

This test does NOT run pytest on the fixture (that would defeat the
``testpaths`` scoping that keeps the fixture out of the main suite).
Instead it inspects the source.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "examples" / "broken_calc"


def test_fixture_exists() -> None:
    assert FIXTURE.is_dir(), "examples/broken_calc must ship in the repo"
    for fname in ("calc.py", "test_calc.py", "README.md"):
        assert (FIXTURE / fname).is_file(), f"missing {fname}"


def test_calc_module_shape() -> None:
    """``calc.py`` must define ``add`` and ``mul`` regardless of state.

    Replaces the v0.3-era ``test_calc_add_is_still_broken`` anti-fix
    guard (Bug A). We no longer pin the body of ``add`` — the v0.4
    exit-gate is allowed to fix it — but we do pin that the
    callables exist so ``test_calc.py`` keeps its imports valid.
    """

    src = (FIXTURE / "calc.py").read_text(encoding="utf-8")
    assert "def add(" in src, "examples/broken_calc/calc.py must define add()"
    assert "def mul(" in src, "examples/broken_calc/calc.py must define mul()"


def test_test_calc_still_asserts_addition() -> None:
    src = (FIXTURE / "test_calc.py").read_text(encoding="utf-8")
    assert "add(2, 3) == 5" in src
    assert "test_mul_unchanged" in src
