from app.config import settings
from app.services.llm.base import BaseLLMProvider


class GroqProvider(BaseLLMProvider):
    """Groq LLM provider using OpenAI-compatible API at api.groq.com."""

    DEFAULT_MODEL = "llama-3.3-70b-versatile"
    GROQ_MODELS = {
        "llama-3.3-70b-versatile",
        "llama-3.1-70b-versatile",
        "llama3-70b-8192",
        "mixtral-8x7b-32768",
    }
    HARD_MAX_OUTPUT_TOKENS = 2400

    def __init__(self):
        from openai import AsyncOpenAI

        self.client = AsyncOpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        )

        configured = settings.LLM_MODEL or ""
        self.model = configured if configured in self.GROQ_MODELS else self.DEFAULT_MODEL

        # Free-tier-safe bounds to reduce max-token failures.
        configured_tokens = int(getattr(settings, "LLM_MAX_OUTPUT_TOKENS", 700) or 700)
        self.max_output_tokens = max(128, min(configured_tokens, self.HARD_MAX_OUTPUT_TOKENS))
        configured_chars = int(getattr(settings, "LLM_MAX_INPUT_CHARS", 12000) or 12000)
        self.max_input_chars = max(2000, configured_chars)

    def _trim(self, text: str) -> str:
        if len(text) <= self.max_input_chars:
            return text
        return text[: self.max_input_chars]

    def _trim_messages(self, messages: list[dict]) -> list[dict]:
        trimmed: list[dict] = []
        budget = self.max_input_chars
        for message in reversed(messages):
            content = str(message.get("content", ""))
            if budget <= 0:
                break
            keep = content[-budget:]
            budget -= len(keep)
            trimmed.append({"role": message.get("role", "user"), "content": keep})
        return list(reversed(trimmed))

    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict | None = None,
        temperature: float = 0.7,
        max_output_tokens: int | None = None,
    ) -> dict:
        messages = [
            {
                "role": "system",
                "content": (
                    self._trim(system_prompt)
                    + "\n\nIMPORTANT: Respond ONLY with valid JSON. "
                    "No markdown, no explanation, just raw JSON."
                ),
            },
            {"role": "user", "content": self._trim(user_prompt)},
        ]
        requested = max_output_tokens if max_output_tokens is not None else self.max_output_tokens
        token_limit = max(128, min(requested, self.HARD_MAX_OUTPUT_TOKENS))
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=token_limit,
        )
        content = response.choices[0].message.content or ""
        return self._extract_json(content)

    async def generate_chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
        temperature: float = 0.7,
    ) -> str:
        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": self._trim(system_prompt)})
        all_messages.extend(self._trim_messages(messages))
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=all_messages,
            temperature=temperature,
            max_tokens=self.max_output_tokens,
        )
        return response.choices[0].message.content or ""
