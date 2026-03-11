import json
from app.services.llm.base import BaseLLMProvider
from app.config import settings


class ClaudeProvider(BaseLLMProvider):
    def __init__(self):
        import anthropic
        self.client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = settings.LLM_MODEL or "claude-3-5-haiku-20241022"

    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict | None = None,
        temperature: float = 0.7,
        max_output_tokens: int | None = None,
    ) -> dict:
        full_system = system_prompt + "\n\nIMPORTANT: Respond ONLY with valid JSON. No other text."
        token_limit = max_output_tokens or 4096
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=token_limit,
            system=full_system,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=temperature,
        )
        content = response.content[0].text
        return self._extract_json(content)

    async def generate_chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
        temperature: float = 0.7,
    ) -> str:
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=system_prompt or "You are a helpful AI career mentor.",
            messages=messages,
            temperature=temperature,
        )
        return response.content[0].text
