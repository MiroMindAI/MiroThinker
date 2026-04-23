# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

"""
LiteLLM-compatible LLM client implementation.

This module provides the LiteLLMClient class for interacting with 100+
LLM providers (OpenAI, Anthropic, Azure, Bedrock, Vertex, Groq, Cohere,
Ollama, etc.) through a single unified interface via LiteLLM.

It extends OpenAIClient and overrides _create_client() to route API calls
through litellm.completion/acompletion instead of the OpenAI SDK directly.
Since LiteLLM returns OpenAI-compatible responses, all retry logic, token
tracking, and response processing from OpenAIClient work unchanged.
"""

import dataclasses
import logging
from typing import Union

from .openai_client import OpenAIClient

logger = logging.getLogger("miroflow_agent")


class _SyncCompletions:
    """Sync proxy that delegates to litellm.completion."""

    @staticmethod
    def create(**kwargs):
        import litellm

        kwargs["drop_params"] = True
        return litellm.completion(**kwargs)


class _AsyncCompletions:
    """Async proxy that delegates to litellm.acompletion."""

    @staticmethod
    async def create(**kwargs):
        import litellm

        kwargs["drop_params"] = True
        return await litellm.acompletion(**kwargs)


class _Chat:
    def __init__(self, completions):
        self.completions = completions


class _LiteLLMProxy:
    """Lightweight proxy mimicking the OpenAI client interface.

    Routes calls to litellm.completion (sync) or litellm.acompletion (async)
    so that OpenAIClient's retry logic and response processing work unchanged.
    """

    def __init__(self, async_mode: bool = False):
        completions = _AsyncCompletions() if async_mode else _SyncCompletions()
        self.chat = _Chat(completions)


@dataclasses.dataclass
class LiteLLMClient(OpenAIClient):
    """LLM client that routes to 100+ providers via LiteLLM.

    Extends OpenAIClient and replaces the OpenAI SDK client with a
    lightweight proxy that delegates to litellm.completion/acompletion.
    All retry logic, token tracking, and response processing are inherited.

    Configure via Hydra config:
        llm:
          provider: litellm
          model_name: anthropic/claude-3-haiku  # any LiteLLM model string
          api_key: ...  # optional, litellm reads provider env vars automatically
    """

    def _create_client(self) -> _LiteLLMProxy:
        """Create a LiteLLM proxy client instead of a direct OpenAI client."""
        return _LiteLLMProxy(async_mode=self.async_client)
