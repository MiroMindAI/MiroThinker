# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

"""
LLM Client Factory module.

This module provides a factory function for creating LLM clients based on
configuration. It supports multiple providers including OpenAI, Anthropic,
and Qwen (via OpenAI-compatible API).
"""

from typing import Optional, Union

from omegaconf import DictConfig, OmegaConf

from ..logging.task_logger import TaskLog
from .providers.anthropic_client import AnthropicClient
from .providers.gemini_client import GeminiClient
from .providers.openai_client import OpenAIClient

# Supported LLM providers
SUPPORTED_PROVIDERS = {"anthropic", "openai", "qwen", "gemini"}


def ClientFactory(
    task_id: str, cfg: DictConfig, task_log: Optional[TaskLog] = None, **kwargs
) -> Union[OpenAIClient, AnthropicClient]:
    """
    Create an LLM client based on the provider specified in configuration.

    This factory function automatically selects and instantiates the appropriate
    client class based on the `llm.provider` field in the configuration.

    Args:
        task_id: Unique identifier for the current task (used for tracking)
        cfg: Hydra configuration object containing LLM settings
        task_log: Optional logger for recording task execution details
        **kwargs: Additional keyword arguments to merge into configuration

    Returns:
        An instance of the appropriate LLM client (OpenAIClient or AnthropicClient)

    Example:
        >>> client = ClientFactory(
        ...     task_id="task_001",
        ...     cfg=cfg,
        ...     task_log=task_log
        ... )
    """
    provider = cfg.llm.provider
    config = OmegaConf.merge(cfg, kwargs)

    client_creators = {
        "anthropic": lambda: AnthropicClient(
            task_id=task_id, task_log=task_log, cfg=config
        ),
        "qwen": lambda: OpenAIClient(task_id=task_id, task_log=task_log, cfg=config),
        "openai": lambda: OpenAIClient(task_id=task_id, task_log=task_log, cfg=config),
        "gemini": lambda: GeminiClient(task_id=task_id, task_log=task_log, cfg=config),
    }

    factory = client_creators.get(provider)
    if not factory:
        raise ValueError(
            f"Unsupported provider: '{provider}'. "
            f"Supported providers are: {', '.join(sorted(SUPPORTED_PROVIDERS))}"
        )

    return factory()
