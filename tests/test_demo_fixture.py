"""Guard test for the §15.1 demo fixture in examples/broken_calc/.

The fixture is intentionally broken; if it ever stops being broken
the demo loses its value. This test asserts the fixture exists, is
shaped the way the README claims, and stays in its failing state.

This test does NOT run pytest on the fixture (that would defeat the
testpaths scoping that keeps the fixture out of the main suite).
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


def test_calc_add_is_still_broken() -> None:
    """The whole point of the fixture is that add() is wrong.

    If somebody commits a fix, the demo is no longer demonstrable.
    The README explicitly tells users to fix add() via ai-cockpit
    and to reset with ``git checkout -- calc.py``.
    """

    src = (FIXTURE / "calc.py").read_text(encoding="utf-8")
    assert "def add(" in src
    # The bug line is canonical. Don't be too strict about whitespace,
    # but require the subtraction shape so a stray '+' commit fails CI.
    assert "return a - b" in src, (
        "examples/broken_calc/calc.py must keep its intentionally broken "
        "subtraction body; reset with `git checkout -- calc.py`."
    )


def test_test_calc_still_asserts_addition() -> None:
    src = (FIXTURE / "test_calc.py").read_text(encoding="utf-8")
    assert "add(2, 3) == 5" in src
    assert "test_mul_unchanged" in src
