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

import os
import sys

from dotenv import load_dotenv
from mcp import StdioServerParameters
from omegaconf import DictConfig

# Load environment variables from .env file
load_dotenv()

# API for Google Search
SERPER_API_KEY = os.environ.get("SERPER_API_KEY")
SERPER_BASE_URL = os.environ.get("SERPER_BASE_URL", "https://google.serper.dev")

# API for Web Scraping
JINA_API_KEY = os.environ.get("JINA_API_KEY")
JINA_BASE_URL = os.environ.get("JINA_BASE_URL", "https://r.jina.ai")

# API for Linux Sandbox
E2B_API_KEY = os.environ.get("E2B_API_KEY")

# API for Open-Source Audio Transcription Tool
WHISPER_BASE_URL = os.environ.get("WHISPER_BASE_URL")
WHISPER_API_KEY = os.environ.get("WHISPER_API_KEY")
WHISPER_MODEL_NAME = os.environ.get("WHISPER_MODEL_NAME")

# API for Open-Source VQA Tool
VISION_API_KEY = os.environ.get("VISION_API_KEY")
VISION_BASE_URL = os.environ.get("VISION_BASE_URL")
VISION_MODEL_NAME = os.environ.get("VISION_MODEL_NAME")

# API for Open-Source Reasoning Tool
REASONING_API_KEY = os.environ.get("REASONING_API_KEY")
REASONING_BASE_URL = os.environ.get("REASONING_BASE_URL")
REASONING_MODEL_NAME = os.environ.get("REASONING_MODEL_NAME")

# API for Claude Sonnet 3.7 as Commercial Tools
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# API Keys for Commercial Tools
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# API for Sougou Search
TENCENTCLOUD_SECRET_ID = os.environ.get("TENCENTCLOUD_SECRET_ID")
TENCENTCLOUD_SECRET_KEY = os.environ.get("TENCENTCLOUD_SECRET_KEY")


# MCP server configuration generation function
def create_mcp_server_parameters(cfg: DictConfig, agent_cfg: DictConfig):
    """Define and return MCP server configuration list"""
    configs = []
    os.environ["OPENAI_BASE_URL"] = (
        cfg.llm.get("openai_base_url") or "https://api.openai.com/v1"
    )
    os.environ["ANTHROPIC_BASE_URL"] = (
        cfg.llm.get("anthropic_base_url") or "https://api.anthropic.com"
    )

    OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL")
    ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL")

    if (
        agent_cfg.get("tools", None) is not None
        and "tool-google-search" in agent_cfg["tools"]
    ):
        if not SERPER_API_KEY:
            raise ValueError(
                "SERPER_API_KEY not set, tool-google-search will be unavailable."
            )

        configs.append(
            {
                "name": "tool-google-search",
                "params": StdioServerParameters(
                    command=sys.executable,
                    args=[
                        "-m",
                        "miroflow_tools.mcp_servers.searching_google_mcp_server",
                    ],
                    env={
                        "SERPER_API_KEY": SERPER_API_KEY,
                        "SERPER_BASE_URL": SERPER_BASE_URL,
                        "JINA_API_KEY": JINA_API_KEY,
                        "JINA_BASE_URL": JINA_BASE_URL,
                    },
                ),
            }
        )

    if (
        agent_cfg.get("tools", None) is not None
        and "tool-sougou-search" in agent_cfg["tools"]
    ):
        configs.append(
            {
                "name": "tool-sougou-search",
                "params": StdioServerParameters(
                    command=sys.executable,
                    args=[
                        "-m",
                        "miroflow_tools.mcp_servers.searching_sougou_mcp_server",
                    ],
                    env={
                        "TENCENTCLOUD_SECRET_ID": TENCENTCLOUD_SECRET_ID,
                        "TENCENTCLOUD_SECRET_KEY": TENCENTCLOUD_SECRET_KEY,
                        "JINA_API_KEY": JINA_API_KEY,
                        "JINA_BASE_URL": JINA_BASE_URL,
                    },
                ),
            }
        )

    if agent_cfg.get("tools", None) is not None and "tool-python" in agent_cfg["tools"]:
        configs.append(
            {
                "name": "tool-python",
                "params": StdioServerParameters(
                    command=sys.executable,
                    args=["-m", "miroflow_tools.mcp_servers.python_mcp_server"],
                    env={"E2B_API_KEY": E2B_API_KEY},
                ),
            }
        )

    if agent_cfg.get("tools", None) is not None and "tool-code" in agent_cfg["tools"]:
        configs.append(
            {
                "name": "tool-code",
                "params": StdioServerParameters(
                    command=sys.executable,
                    args=["-m", "miroflow_tools.mcp_servers.python_mcp_server"],
                    env={"E2B_API_KEY": E2B_API_KEY},
                ),
            }
        )

    if agent_cfg.get("tools", None) is not None and "tool-vqa" in agent_cfg["tools"]:
        configs.append(
            {
                "name": "tool-vqa",
                "params": StdioServerParameters(
                    command=sys.executable,
                    args=["-m", "miroflow_tools.mcp_servers.vision_mcp_server"],
                    env={
                        "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
                        "ANTHROPIC_BASE_URL": ANTHROPIC_BASE_URL,
                    },
                ),
            }
        )

    if agent_cfg.get("tools", None) is not None and "tool-vqa-os" in agent_cfg["tools"]:
        configs.append(
            {
                "name": "tool-vqa-os",
                "params": StdioServerParameters(
                    command=sys.executable,
                    args=["-m", "miroflow_tools.mcp_servers.vision_mcp_server_os"],
                    env={
                        "VISION_API_KEY": VISION_API_KEY,
                        "VISION_BASE_URL": VISION_BASE_URL,
                        "VISION_MODEL_NAME": VISION_MODEL_NAME,
                    },
                ),
            }
        )

    if (
        agent_cfg.get("tools", None) is not None
        and "tool-transcribe" in agent_cfg["tools"]
    ):
        configs.append(
            {
                "name": "tool-transcribe",
                "params": StdioServerParameters(
                    command=sys.executable,
                    args=["-m", "miroflow_tools.mcp_servers.audio_mcp_server"],
                    env={
                        "OPENAI_API_KEY": OPENAI_API_KEY,
                        "OPENAI_BASE_URL": OPENAI_BASE_URL,
                    },
                ),
            }
        )

    if (
        agent_cfg.get("tools", None) is not None
        and "tool-transcribe-os" in agent_cfg["tools"]
    ):
        configs.append(
            {
                "name": "tool-transcribe-os",
                "params": StdioServerParameters(
                    command=sys.executable,
                    args=["-m", "miroflow_tools.mcp_servers.audio_mcp_server_os"],
                    env={
                        "WHISPER_BASE_URL": WHISPER_BASE_URL,
                        "WHISPER_API_KEY": WHISPER_API_KEY,
                        "WHISPER_MODEL_NAME": WHISPER_MODEL_NAME,
                    },
                ),
            }
        )

    if (
        agent_cfg.get("tools", None) is not None
        and "tool-reasoning" in agent_cfg["tools"]
    ):
        configs.append(
            {
                "name": "tool-reasoning",
                "params": StdioServerParameters(
                    command=sys.executable,
                    args=[
                        "-m",
                        "miroflow_tools.mcp_servers.reasoning_mcp_server",
                    ],
                    env={
                        "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
                        "ANTHROPIC_BASE_URL": ANTHROPIC_BASE_URL,
                    },
                ),
            }
        )

    if (
        agent_cfg.get("tools", None) is not None
        and "tool-reasoning-os" in agent_cfg["tools"]
    ):
        configs.append(
            {
                "name": "tool-reasoning-os",
                "params": StdioServerParameters(
                    command=sys.executable,
                    args=[
                        "-m",
                        "miroflow_tools.mcp_servers.reasoning_mcp_server_os",
                    ],
                    env={
                        "REASONING_API_KEY": REASONING_API_KEY,
                        "REASONING_BASE_URL": REASONING_BASE_URL,
                        "REASONING_MODEL_NAME": REASONING_MODEL_NAME,
                    },
                ),
            }
        )

    # reader
    if agent_cfg.get("tools", None) is not None and "tool-reader" in agent_cfg["tools"]:
        configs.append(
            {
                "name": "tool-reader",
                "params": StdioServerParameters(
                    command=sys.executable,
                    args=["-m", "markitdown_mcp"],
                ),
            }
        )

    if (
        agent_cfg.get("tools", None) is not None
        and "tool-reading" in agent_cfg["tools"]
    ):
        configs.append(
            {
                "name": "tool-reading",
                "params": StdioServerParameters(
                    command=sys.executable,
                    args=["-m", "miroflow_tools.mcp_servers.reading_mcp_server"],
                ),
            }
        )

    blacklist = set()
    for black_list_item in agent_cfg.get("tool_blacklist", []):
        blacklist.add((black_list_item[0], black_list_item[1]))
    return configs, blacklist


def expose_sub_agents_as_tools(sub_agents_cfg: DictConfig):
    """Expose sub-agents as tools"""
    sub_agents_server_params = []
    for sub_agent in sub_agents_cfg.keys():
        if "agent-browsing" in sub_agent:
            sub_agents_server_params.append(
                dict(
                    name="agent-browsing",
                    tools=[
                        dict(
                            name="search_and_browse",
                            description="This tool is an agent that performs the subtask of searching and browsing the web for specific missing information and generating the desired answer. The subtask should be clearly defined, include relevant background, and focus on factual gaps. It does not perform vague or speculative subtasks. \nArgs: \n\tsubtask: the subtask to be performed. \nReturns: \n\tthe result of the subtask. ",
                            schema={
                                "type": "object",
                                "properties": {
                                    "subtask": {"title": "Subtask", "type": "string"}
                                },
                                "required": ["subtask"],
                                "title": "search_and_browseArguments",
                            },
                        )
                    ],
                )
            )
    return sub_agents_server_params


def get_env_info(cfg: DictConfig) -> dict:
    """Collect current configuration environment variable information for logging"""
    return {
        # LLM Configuration
        "llm_provider": cfg.llm.provider,
        "llm_model_name": cfg.llm.model_name,
        "llm_temperature": cfg.llm.temperature,
        "llm_top_p": cfg.llm.top_p,
        "llm_min_p": cfg.llm.min_p,
        "llm_top_k": cfg.llm.top_k,
        "llm_max_tokens": cfg.llm.max_tokens,
        "llm_async_client": cfg.llm.async_client,
        "keep_tool_result": cfg.llm.keep_tool_result,
        # Agent Configuration
        "main_agent_max_turns": cfg.agent.main_agent.max_turns,
        **{
            f"sub_{sub_agent}_max_turns": cfg.agent.sub_agents[sub_agent].max_turns
            for sub_agent in cfg.agent.sub_agents
        },
        # API Keys (masked for security)
        "has_serper_api_key": bool(SERPER_API_KEY),
        "has_jina_api_key": bool(JINA_API_KEY),
        "has_anthropic_api_key": bool(ANTHROPIC_API_KEY),
        "has_openai_api_key": bool(OPENAI_API_KEY),
        "has_e2b_api_key": bool(E2B_API_KEY),
        # Base URLs
        "openai_base_url": os.environ.get("OPENAI_BASE_URL"),
        "anthropic_base_url": os.environ.get("ANTHROPIC_BASE_URL"),
    }
