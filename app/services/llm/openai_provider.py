import json
from app.services.llm.base import BaseLLMProvider
from app.config import settings


class OpenAIProvider(BaseLLMProvider):
    def __init__(self):
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.LLM_MODEL or "gpt-4o-mini"

    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict | None = None,
        temperature: float = 0.7,
        max_output_tokens: int | None = None,
    ) -> dict:
        messages = [
            {"role": "system", "content": system_prompt + "\nRespond ONLY with valid JSON."},
            {"role": "user", "content": user_prompt},
        ]
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            response_format={"type": "json_object"},
            max_tokens=max_output_tokens,
        )
        content = response.choices[0].message.content
        return self._extract_json(content)

    async def generate_chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
        temperature: float = 0.7,
    ) -> str:
        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=all_messages,
            temperature=temperature,
        )
        return response.choices[0].message.content
