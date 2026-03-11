from abc import ABC, abstractmethod
from typing import Any
import json


class BaseLLMProvider(ABC):
    """Abstract base class for all LLM providers."""

    @abstractmethod
    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict | None = None,
        temperature: float = 0.7,
        max_output_tokens: int | None = None,
    ) -> dict:
        """Generate a structured JSON response. Must always return a dict."""
        pass

    @abstractmethod
    async def generate_chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
        temperature: float = 0.7,
    ) -> str:
        """Generate a conversational response."""
        pass

    def _extract_json(self, text: str) -> dict:
        """Attempt to extract JSON from text response."""
        text = text.strip()
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Try to find JSON block
        import re
        match = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass
        # Try to find first { ... }
        match = re.search(r"\{[\s\S]+\}", text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        raise ValueError(f"Could not extract JSON from LLM response: {text[:500]}")

    def _is_quota_error(self, exc: Exception) -> bool:
        """Detect rate-limit / quota-exceeded errors from any provider."""
        msg = str(exc).lower()
        return any(k in msg for k in (
            "429", "quota", "rate_limit", "ratelimit",
            "resource_exhausted", "resourceexhausted",
            "too many requests", "exceeded",
        ))

    async def generate_with_retry(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict | None = None,
        max_retries: int = 3,
        max_output_tokens: int | None = None,
    ) -> dict:
        """Retry wrapper for structured generation.
        Quota/rate-limit errors are NOT retried — they bubble up immediately
        so the FallbackLLMProvider can switch to the next provider.
        """
        last_error = None
        for attempt in range(max_retries):
            try:
                result = await self.generate_structured(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_schema=response_schema,
                    max_output_tokens=max_output_tokens,
                )
                return result
            except Exception as e:
                # Quota errors: raise immediately — no point retrying same provider
                if self._is_quota_error(e):
                    raise
                last_error = e
                if attempt < max_retries - 1:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)
        raise RuntimeError(f"LLM failed after {max_retries} attempts: {last_error}")
