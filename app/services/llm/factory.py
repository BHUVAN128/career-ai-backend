import os
from pathlib import Path

import structlog

from app.core.exceptions import LLMError
from app.config import settings
from app.services.llm.base import BaseLLMProvider

logger = structlog.get_logger()

_provider_instance: BaseLLMProvider | None = None


def reset_provider() -> None:
    """Reset singleton (useful for testing or after config changes)."""
    global _provider_instance
    _provider_instance = None


# Reset on every module reload (e.g. uvicorn --reload picks up .env changes)
reset_provider()


def _read_env_values() -> dict[str, str]:
    """Read backend/.env directly to avoid stale settings cache values."""
    env_path = Path(__file__).resolve().parents[3] / ".env"
    env_vars: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env_vars[k.strip()] = v.strip()
    return env_vars


def _key(env_vars: dict[str, str], name: str) -> str:
    setting_fallback = getattr(settings, name, "")
    return env_vars.get(name) or os.environ.get(name, "") or str(setting_fallback or "")


def _is_quota_error(exc: Exception) -> bool:
    """Detect rate-limit / quota / output-limit errors from any provider."""
    msg = str(exc).lower()
    return any(
        k in msg
        for k in (
            "429",
            "quota",
            "rate_limit",
            "ratelimit",
            "resource_exhausted",
            "resourceexhausted",
            "too many requests",
            "exceeded",
            "maximum tokens",
            "max_tokens",
            "output limit",
            "finish_reason: length",
            "finish_reason=length",
            "stop_reason: max_tokens",
        )
    )


def _is_fallbackable_error(exc: Exception) -> bool:
    """
    Errors that should switch to next provider:
    - quota/rate/output limit
    - auth/permission/model/provider availability
    """
    if _is_quota_error(exc):
        return True

    msg = str(exc).lower()
    return any(
        k in msg
        for k in (
            "401",
            "403",
            "unauthorized",
            "forbidden",
            "invalid api key",
            "permission denied",
            "authentication",
            "api key not valid",
            "service unavailable",
            "temporarily unavailable",
            "model not found",
            "not found",
            "unavailable",
        )
    )


def _build_provider(name: str, env_vars: dict[str, str]) -> BaseLLMProvider | None:
    """Instantiate a provider by name if its API key is configured."""
    name = name.lower()

    if name == "groq" and _key(env_vars, "GROQ_API_KEY"):
        from app.services.llm.groq_provider import GroqProvider

        return GroqProvider()
    if name == "openai" and _key(env_vars, "OPENAI_API_KEY"):
        from app.services.llm.openai_provider import OpenAIProvider

        return OpenAIProvider()
    if name == "claude" and _key(env_vars, "ANTHROPIC_API_KEY"):
        from app.services.llm.claude_provider import ClaudeProvider

        return ClaudeProvider()
    if name == "gemini" and _key(env_vars, "GOOGLE_API_KEY"):
        from app.services.llm.gemini_provider import GeminiProvider

        return GeminiProvider()
    return None


class FallbackLLMProvider(BaseLLMProvider):
    """
    Wrap multiple providers with automatic fallback.
    On fallbackable errors the next available provider is tried.
    """

    def __init__(self, providers: list[BaseLLMProvider], names: list[str]):
        self._providers = providers
        self._names = names

    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict | None = None,
        temperature: float = 0.7,
        max_output_tokens: int | None = None,
    ) -> dict:
        last_exc: Exception | None = None
        for provider, name in zip(self._providers, self._names):
            try:
                result = await provider.generate_structured(
                    system_prompt,
                    user_prompt,
                    response_schema,
                    temperature,
                    max_output_tokens,
                )
                if name != self._names[0]:
                    logger.info("llm_fallback_used", provider=name)
                return result
            except Exception as exc:
                last_exc = exc
                if _is_fallbackable_error(exc):
                    logger.warning(
                        "llm_provider_failed_fallback",
                        provider=name,
                        error=str(exc)[:160],
                    )
                    continue
                raise
        raise LLMError(f"All LLM providers exhausted. Last error: {last_exc}")

    async def generate_chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
        temperature: float = 0.7,
    ) -> str:
        last_exc: Exception | None = None
        for provider, name in zip(self._providers, self._names):
            try:
                result = await provider.generate_chat(messages, system_prompt, temperature)
                if name != self._names[0]:
                    logger.info("llm_fallback_used", provider=name)
                return result
            except Exception as exc:
                last_exc = exc
                if _is_fallbackable_error(exc):
                    logger.warning(
                        "llm_provider_failed_fallback",
                        provider=name,
                        error=str(exc)[:160],
                    )
                    continue
                raise
        raise LLMError(f"All LLM providers exhausted. Last error: {last_exc}")


def get_llm_provider() -> BaseLLMProvider:
    """Return a singleton fallback provider chain with configured providers."""
    global _provider_instance
    if _provider_instance is not None:
        return _provider_instance

    env_vars = _read_env_values()

    # Groq-first default for better free-tier resilience.
    requested_primary = (_key(env_vars, "LLM_PROVIDER") or "groq").lower()
    if requested_primary == "gemini" and _key(env_vars, "GROQ_API_KEY"):
        primary = "groq"
    else:
        primary = requested_primary
    fallback_order = ["groq", "gemini", "openai", "claude"]

    # Put primary first, then the rest without duplicates.
    ordered = [primary] + [provider for provider in fallback_order if provider != primary]

    providers: list[BaseLLMProvider] = []
    names: list[str] = []
    for name in ordered:
        provider = _build_provider(name, env_vars)
        if provider is not None:
            providers.append(provider)
            names.append(name)

    if not providers:
        raise LLMError(
            "No LLM provider configured. Set GROQ_API_KEY, OPENAI_API_KEY, "
            "ANTHROPIC_API_KEY, or GOOGLE_API_KEY in .env."
        )

    logger.info("llm_providers_loaded", primary=names[0], chain=names)
    _provider_instance = FallbackLLMProvider(providers, names)
    return _provider_instance
