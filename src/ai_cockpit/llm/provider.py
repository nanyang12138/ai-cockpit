"""LLM provider protocol and a generic env-driven factory.

Design notes:
- ``LLMProvider`` is a tiny ``Protocol`` so tests can inject mocks freely.
- Real providers are imported lazily inside the factory so importing
  ``ai_cockpit`` never requires ``langchain-anthropic`` or
  ``langchain-openai`` to be installed.
- Configuration is read from environment variables in priority order:
    1. ``LLM_API_KEY`` + ``LLM_API_BASE`` + ``LLM_MODEL_NAME`` (generic;
       works with AMD-style enterprise proxies).
    2. ``ANTHROPIC_API_KEY`` (default base ``https://api.anthropic.com``).
    3. ``OPENAI_API_KEY`` (default base ``https://api.openai.com/v1``).
- Protocol auto-detection: if ``LLM_API_BASE`` contains "anthropic"
  (case-insensitive) OR the model name starts with "claude", use the
  Anthropic-compatible client; otherwise use the OpenAI-compatible
  client. Explicit override via ``LLM_PROVIDER=anthropic|openai``.
"""

from __future__ import annotations

import logging
import os
from typing import Protocol

log = logging.getLogger(__name__)


class LLMProvider(Protocol):
    """Minimal contract every backing client must satisfy."""

    name: str

    def complete(self, *, system: str, user: str) -> str:
        """Send a single-turn prompt and return the assistant text."""
        ...


def _detect_protocol(base: str | None, model: str | None) -> str:
    explicit = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if explicit in {"anthropic", "openai"}:
        return explicit
    if base and "anthropic" in base.lower():
        return "anthropic"
    if model and model.lower().startswith("claude"):
        return "anthropic"
    return "openai"


def _build_anthropic(*, api_key: str, base_url: str | None, model: str) -> LLMProvider:
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError as exc:  # pragma: no cover - exercised only when installed
        raise RuntimeError(
            "langchain-anthropic is required for --llm anthropic/auto with a "
            "claude-compatible endpoint. Install with: pip install langchain-anthropic"
        ) from exc

    kwargs: dict[str, object] = {"model": model, "api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url

    client = ChatAnthropic(**kwargs)  # type: ignore[arg-type]

    class _AnthropicProvider:
        name = f"anthropic:{model}"

        def complete(self, *, system: str, user: str) -> str:
            messages = [("system", system), ("user", user)]
            response = client.invoke(messages)
            content = getattr(response, "content", "")
            if isinstance(content, list):
                return "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in content
                )
            return str(content)

    return _AnthropicProvider()


def _build_openai(*, api_key: str, base_url: str | None, model: str) -> LLMProvider:
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:  # pragma: no cover - exercised only when installed
        raise RuntimeError(
            "langchain-openai is required for --llm openai/auto with an "
            "OpenAI-compatible endpoint. Install with: pip install langchain-openai"
        ) from exc

    kwargs: dict[str, object] = {"model": model, "api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url

    client = ChatOpenAI(**kwargs)  # type: ignore[arg-type]

    class _OpenAIProvider:
        name = f"openai:{model}"

        def complete(self, *, system: str, user: str) -> str:
            messages = [("system", system), ("user", user)]
            response = client.invoke(messages)
            content = getattr(response, "content", "")
            return str(content)

    return _OpenAIProvider()


def _resolve_env() -> tuple[str, str | None, str] | None:
    """Return ``(api_key, base_url, model)`` from the highest-priority set."""

    generic_key = os.environ.get("LLM_API_KEY")
    if generic_key:
        base = os.environ.get("LLM_API_BASE") or None
        model = os.environ.get("LLM_MODEL_NAME") or "claude-3-5-sonnet-latest"
        return generic_key, base, model

    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_key:
        return anthropic_key, None, os.environ.get("LLM_MODEL_NAME") or "claude-3-5-sonnet-latest"

    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        return openai_key, None, os.environ.get("LLM_MODEL_NAME") or "gpt-4o-mini"

    return None


def build_llm(mode: str) -> LLMProvider | None:
    """Construct an ``LLMProvider`` from env per ``mode``.

    Returns ``None`` when ``mode == 'none'`` or no usable credentials are
    configured. Callers should treat ``None`` as "fall back to stub".
    """

    mode = (mode or "none").strip().lower()
    if mode == "none":
        return None

    env = _resolve_env()
    if env is None:
        return None
    api_key, base_url, model = env

    if mode == "anthropic":
        protocol = "anthropic"
    elif mode == "openai":
        protocol = "openai"
    else:  # auto
        protocol = _detect_protocol(base_url, model)

    try:
        if protocol == "anthropic":
            return _build_anthropic(api_key=api_key, base_url=base_url, model=model)
        return _build_openai(api_key=api_key, base_url=base_url, model=model)
    except RuntimeError as exc:
        log.warning("LLM unavailable (%s); falling back to stub planner/reviewer", exc)
        return None
