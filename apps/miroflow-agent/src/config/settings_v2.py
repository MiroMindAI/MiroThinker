import os

from omegaconf import DictConfig

from .http import hydrate_mcp_client_with_streamable_http
from .sse import hydrate_mcp_client_with_sse_transport
from .stdio import hydrate_mcp_client_with_stdio_transport


def create_mcp_server_parameters(cfg: DictConfig, agent_cfg: DictConfig):
    os.environ["OPENAI_BASE_URL"] = (
        cfg.llm.get("openai_base_url") or "https://api.openai.com/v1"
    )
    os.environ["ANTHROPIC_BASE_URL"] = (
        cfg.llm.get("anthropic_base_url") or "https://api.anthropic.com"
    )

    OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL")
    ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL")

    tool_list = agent_cfg.get("tools", [])
    stdio_configs = hydrate_mcp_client_with_stdio_transport(
        tool_list,
        anthropic_base_url=ANTHROPIC_BASE_URL,
        openai_base_url=OPENAI_BASE_URL,
    )
    sse_configs = hydrate_mcp_client_with_sse_transport(tool_list)
    http_configs = hydrate_mcp_client_with_streamable_http(tool_list)

    configs = [*stdio_configs, *sse_configs, *http_configs]

    blacklist = set()
    for item in agent_cfg.get("tool_blacklist", []):
        blacklist.add((item[0], item[1]))
    return configs, blacklist
