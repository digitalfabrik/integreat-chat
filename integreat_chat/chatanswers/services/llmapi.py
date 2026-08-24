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


class LlmClientError(Exception):
    """The LLM server answered with an HTTP error status.

    ``status`` is the HTTP status code (or ``None`` if it could not be
    determined). The message is capped, and the response body is
    included only in truncated form, so it is safe to log and to
    surface to end users in a degraded-but-safe reason string.
    """

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


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
    def __init__(
        self,
        model: str,
        messages: list[LlmMessage],
        json_schema: None | dict = None,
        extra_body: None | dict = None,
    ):
        self.messages = messages
        self.json_schema = json_schema
        self.model = model
        # Optional provider-specific top-level request params (e.g.
        # ``{"think": False}``) that are appended verbatim to the request
        # body. None (the default) means nothing extra is sent, so existing
        # callers are unaffected; only callers that opt in (e.g. translation)
        # see the extra keys.
        self.extra_body = extra_body

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
        if self.extra_body:
            # Merge provider-specific params at the TOP LEVEL of the
            # request body. This works for LiteLLM (our LLM_SERVER) and
            # Ollama/vLLM, which accept unknown top-level params. If
            # LLM_SERVER ever points at a strict OpenAI-compatible
            # gateway that rejects unknown params, this must be nested
            # under the provider-specific key instead (e.g.
            # "reasoning_effort" inside "options").
            body.update({k: v for k, v in self.extra_body.items() if v is not None})
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
        # ``total`` caps the *whole* request (connect + headers + body).
        # Translation and other larger generations on a CPU-only backend
        # routinely need more than the old hard-coded 120s, especially
        # when several calls queue behind a single model worker. Make the
        # cap overridable (default raised to 300s) so an operator can give
        # long generations room to finish instead of hard-failing.
        timeout = getattr(settings, "LLM_TIMEOUT", 300)
        async with session.post(self.api_url,
                                json={**prompt.as_dict(), "temperature": 0},
                                timeout=aiohttp.ClientTimeout(total=timeout),
                                headers={
                                    'Authorization': f'Bearer {settings.LLM_API_KEY}',
                                    'Content-Type': 'application/json',
                                }) as response:
            if response.status >= 400:
                try:
                    body = await response.text()
                except (aiohttp.ClientError, OSError, UnicodeDecodeError):
                    body = ""
                snippet = " ".join(body.split())[:200]
                LOGGER.warning(
                    "LLM server %s returned HTTP %s: %s",
                    self.api_url, response.status, snippet or "(no body)",
                )
                raise LlmClientError(
                    f"LLM server returned HTTP {response.status}"
                    + (f": {snippet}" if snippet else ""),
                    status=response.status,
                ) from None
            return await response.json()
