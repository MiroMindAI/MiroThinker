# Copyright 2025 Miromind.ai
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
