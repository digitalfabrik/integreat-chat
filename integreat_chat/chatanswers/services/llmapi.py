"""
Very simple LiteLLM Client (should be compatible to OpenAI API)
"""
import json
import logging
import re

import aiohttp

from django.conf import settings


LOGGER = logging.getLogger(__name__)

# Runs of byte-fallback tokens (e.g. "<0xE2><0x80><0xAF>") that some
# llama.cpp/Ollama models emit verbatim instead of the decoded character.
_BYTE_TOKEN_RUN = re.compile(r"(?:<0x[0-9A-Fa-f]{2}>)+")


def decode_byte_tokens(text: str) -> str:
    """
    Turn leaked byte-fallback token runs back into their UTF-8 characters.
    """
    def replace(match: re.Match) -> str:
        raw = bytes(
            int(token, 16)
            for token in re.findall(r"<0x([0-9A-Fa-f]{2})>", match.group(0))
        )
        return raw.decode("utf-8", errors="replace")

    return _BYTE_TOKEN_RUN.sub(replace, text)


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
        return decode_byte_tokens(self.response["choices"][0]["message"]["content"])

    def as_dict(self) -> dict:
        """
        Parse JSON in response
        """
        try:
            return json.loads(str(self))
        except json.decoder.JSONDecodeError:
            LOGGER.exception("Failed to parse JSON LLM response from response: %s", str(self))
            return {}

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

    async def simple_prompt(self, session: aiohttp.ClientSession, message: str) -> str:
        """
        Send a single user message to the default RAG model and return its content.

        param session: shared aiohttp session
        param message: prompt content
        return: LLM response text
        """
        return str(LlmResponse(await self.chat_prompt(
            session,
            LlmPrompt(settings.RAG_MODEL, [LlmMessage(message)])
        )))

    async def chat_prompt_session_wrapper(self, prompt: LlmPrompt) -> dict:
        """
        Run a single prompt with its own short-lived aiohttp session.
        """
        async with aiohttp.ClientSession() as session:
            return await self.chat_prompt(session, prompt)

    async def chat_prompt(self, session: aiohttp.ClientSession, prompt: LlmPrompt) -> dict:
        """
        Get RAG answer
        """
        async with session.post(self.api_url,
                                json={**prompt.as_dict(), "temperature": 0},
                                timeout=aiohttp.ClientTimeout(total=120),
                                headers={
                                    'Authorization': f'Bearer {settings.LLM_API_KEY}',
                                    'Content-Type': 'application/json',
                                }) as response:
            return await response.json()
