import json
from app.services.llm.base import BaseLLMProvider
from app.config import settings


class GeminiProvider(BaseLLMProvider):
    def __init__(self):
        import google.generativeai as genai
        genai.configure(api_key=settings.GOOGLE_API_KEY)
        model_name = settings.LLM_MODEL or "gemini-1.5-flash"
        self.model = genai.GenerativeModel(model_name)

    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict | None = None,
        temperature: float = 0.7,
        max_output_tokens: int | None = None,
    ) -> dict:
        import asyncio
        import functools
        prompt = f"{system_prompt}\n\nRespond ONLY with valid JSON.\n\nUser: {user_prompt}"
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            functools.partial(self.model.generate_content, prompt)
        )
        return self._extract_json(response.text)

    async def generate_chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
        temperature: float = 0.7,
    ) -> str:
        import asyncio
        import functools
        # Convert messages to Gemini format
        history = []
        for msg in messages[:-1]:
            role = "user" if msg["role"] == "user" else "model"
            history.append({"role": role, "parts": [msg["content"]]})
        last_message = messages[-1]["content"] if messages else ""
        chat = self.model.start_chat(history=history)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            functools.partial(chat.send_message, last_message)
        )
        return response.text
