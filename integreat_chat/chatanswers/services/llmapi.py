"""
Very simple LiteLLM Client (should be compatible to OpenAI API)
"""
import json

import asyncio
import aiohttp

from django.conf import settings

class LlmMessage:
    """
    Class that represents a prompt to an LLM

    param content: message
    param role: user, system or assistant
    """
    def __init__(self, content: str, role: str = "user") -> None:
        self.role = role
        self.content = content

    def as_dict(self) -> dict:
        """
        Return OpenAI API compatible message dict
        """
        return {
            "role": self.role,
            "content": self.content,
        }

class LlmPrompt:
    """
    Class that represents a prompt to an LLM
    """
    def __init__(self, model: str, messages: list[LlmMessage], json_schema: None | dict = None):
        self.messages = messages
        self.json_schema = json_schema
        self.model = model

    def as_dict(self) -> dict:
        """
        Return OpenAI API compatible prompt dict
        """
        body = {
            "model": self.model,
            "messages": [message.as_dict() for message in self.messages]
        }
        if self.json_schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": self.json_schema,
            }
        return body

class LlmResponse:
    """
    Class for parsing LLM responses
    """
    def __init__(self, response: dict) -> None:
        self.response = response

    def __str__(self) -> str:
        """
        Return message response as string
        """
        return self.response["choices"][0]["message"]["content"]

    def as_dict(self) -> dict:
        """
        Parse JSON in response
        """
        return json.loads(str(self))

class LlmApiClient:
    """
    API Client for prompting
    """
    def __init__(self):
        """
        Initialize the API client with a LLM model

        param system_prompt: A system prompt that provides general orientation to the LLM
        param model: LLM Model
        """
        self.api_url = f"{settings.LLM_SERVER}/chat/completions"

    def simple_prompt(self, message: str) -> str:
        """
        Simple message and answer function.

        param message: Message prompted to LLM
        return: message returned by LLM
        """
        return str(
            LlmResponse(asyncio.run(self.chat_prompt_session_wrapper(
                LlmPrompt(settings.RAG_MODEL, [LlmMessage(message)])
            )))
        )

    async def chat_prompt_session_wrapper(self, prompt: LlmPrompt) -> dict:
        """
        Async wrapper for simple prompt
        """
        async with aiohttp.ClientSession() as session:
            return await self.chat_prompt(session, prompt)

    async def chat_prompt(self, session: aiohttp.ClientSession, prompt: LlmPrompt) -> dict:
        """
        Get RAG answer
        """
        async with session.post(self.api_url,
                                json={**prompt.as_dict(), "temperature": 0},
                                timeout=120,
                                headers={
                                    'Authorization': f'Bearer {settings.LLM_API_KEY}',
                                    'Content-Type': 'application/json',
                                }) as response:
            return await response.json()
