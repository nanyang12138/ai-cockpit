"""LLM provider abstraction for v0.2 step 1.

Keeps the graph nodes provider-agnostic. The factory ``build_llm``
inspects environment variables generically (`LLM_API_KEY`, `LLM_API_BASE`,
`LLM_MODEL_NAME`) so enterprise proxies (e.g. AMD's Anthropic-compatible
gateway) work without hard-coded URLs.

Stub fallback: when ``mode == "none"`` or no key is configured, the
factory returns ``None`` and the planner/reviewer nodes fall back to
the v0.1 deterministic logic.
"""

from ai_cockpit.llm.provider import LLMProvider, build_llm

__all__ = ["LLMProvider", "build_llm"]
