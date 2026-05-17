"""Intentionally broken sample module used by the §15.1 ai-cockpit demo.

Do NOT fix this module by hand — it is deliberately wrong so the
real-LLM end-to-end demo has something concrete to repair. The
companion ``test_calc.py`` will fail until ai-cockpit + aider
correctly rewrite ``add`` to return ``a + b``.
"""

from __future__ import annotations


def add(a: int, b: int) -> int:
    return a + b


def mul(a: int, b: int) -> int:
    return a * b
