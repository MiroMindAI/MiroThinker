import sys
from typing import Literal, TypedDict

from mcp import StdioServerParameters

from .settings import (
    ANTHROPIC_API_KEY,
    E2B_API_KEY,
    JINA_API_KEY,
    JINA_BASE_URL,
    OPENAI_API_KEY,
    REASONING_API_KEY,
    REASONING_BASE_URL,
    REASONING_MODEL_NAME,
    SERPER_API_KEY,
    SERPER_BASE_URL,
    TENCENTCLOUD_SECRET_ID,
    TENCENTCLOUD_SECRET_KEY,
    VISION_API_KEY,
    VISION_BASE_URL,
    VISION_MODEL_NAME,
    WHISPER_API_KEY,
    WHISPER_BASE_URL,
    WHISPER_MODEL_NAME,
)


class Config(TypedDict):
    name: str
    kind: Literal["stdio"]
    params: StdioServerParameters


def hydrate_mcp_client_with_stdio_transport(
    tool_list: list[str], anthropic_base_url: str, openai_base_url: str
) -> list[Config]:
    configs: list[Config] = []
    for tool_name in tool_list:
        if tool_name == "tool-google-search":
            configs.append(
                {
                    "name": "tool-google-search",
                    "kind": "stdio",
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
        elif tool_name == "tool-sougou-search":
            configs.append(
                {
                    "name": "tool-sougou-search",
                    "kind": "stdio",
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

        elif tool_name == "tool-python":
            configs.append(
                {
                    "name": "tool-python",
                    "kind": "stdio",
                    "params": StdioServerParameters(
                        command=sys.executable,
                        args=["-m", "miroflow_tools.mcp_servers.python_mcp_server"],
                        env={"E2B_API_KEY": E2B_API_KEY},
                    ),
                }
            )
        elif tool_name == "tool-code":
            configs.append(
                {
                    "name": "tool-code",
                    "kind": "stdio",
                    "params": StdioServerParameters(
                        command=sys.executable,
                        args=["-m", "miroflow_tools.mcp_servers.python_mcp_server"],
                        env={"E2B_API_KEY": E2B_API_KEY},
                    ),
                }
            )
        elif tool_name == "tool-vqa":
            configs.append(
                {
                    "name": "tool-vqa",
                    "kind": "stdio",
                    "params": StdioServerParameters(
                        command=sys.executable,
                        args=["-m", "miroflow_tools.mcp_servers.vision_mcp_server"],
                        env={
                            "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
                            "ANTHROPIC_BASE_URL": anthropic_base_url,
                        },
                    ),
                }
            )
        elif tool_name == "tool-vqa-os":
            configs.append(
                {
                    "name": "tool-vqa-os",
                    "kind": "stdio",
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

        elif tool_name == "tool_transcribe":
            configs.append(
                {
                    "name": "tool-transcribe",
                    "kind": "stdio",
                    "params": StdioServerParameters(
                        command=sys.executable,
                        args=["-m", "miroflow_tools.mcp_servers.audio_mcp_server"],
                        env={
                            "OPENAI_API_KEY": OPENAI_API_KEY,
                            "OPENAI_BASE_URL": openai_base_url,
                        },
                    ),
                }
            )

        elif tool_name == "tool-transcribe-os":
            configs.append(
                {
                    "name": "tool-transcribe-os",
                    "kind": "stdio",
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

        elif tool_name == "tool-reasoning":
            configs.append(
                {
                    "name": "tool-reasoning",
                    "kind": "stdio",
                    "params": StdioServerParameters(
                        command=sys.executable,
                        args=[
                            "-m",
                            "miroflow_tools.mcp_servers.reasoning_mcp_server",
                        ],
                        env={
                            "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
                            "ANTHROPIC_BASE_URL": anthropic_base_url,
                        },
                    ),
                }
            )

        elif tool_name == "tool-reasoning-os":
            configs.append(
                {
                    "name": "tool-reasoning-os",
                    "kind": "stdio",
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
        elif tool_name == "tool-reader":
            configs.append(
                {
                    "name": "tool-reader",
                    "kind": "stdio",
                    "params": StdioServerParameters(
                        command=sys.executable,
                        args=["-m", "markitdown_mcp"],
                    ),
                }
            )

        elif tool_name == "tool-reading":
            configs.append(
                {
                    "name": "tool-reading",
                    "kind": "stdio",
                    "params": StdioServerParameters(
                        command=sys.executable,
                        args=["-m", "miroflow_tools.mcp_servers.reading_mcp_server"],
                    ),
                }
            )
        else:
            print("not supported")

    return configs
