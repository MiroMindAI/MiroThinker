# Copyright (c) 2025 Miromind.ai
# This source code is licensed under the MIT License.

from typing import Optional

from omegaconf import DictConfig, OmegaConf

from ..logging.task_logger import TaskLog
from .providers.anthropic_client import AnthropicClient
from .providers.openai_client import OpenAIClient


def ClientFactory(
    task_id: str, cfg: DictConfig, task_log: Optional[TaskLog] = None, **kwargs
):
    """
    Automatically select provider and create LLM client based on configuration
    """
    provider = cfg.llm.provider
    config = OmegaConf.merge(cfg, kwargs)

    client_creators = {
        "anthropic": lambda: AnthropicClient(
            task_id=task_id, task_log=task_log, cfg=config
        ),
        "qwen": lambda: OpenAIClient(task_id=task_id, task_log=task_log, cfg=config),
        "openai": lambda: OpenAIClient(task_id=task_id, task_log=task_log, cfg=config),
    }

    factory = client_creators.get(provider)
    if not factory:
        raise ValueError(f"Unsupported provider: {provider}")

    return factory()
