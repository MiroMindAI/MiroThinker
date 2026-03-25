# Copyright (c) 2025 MiroMind
# This source code is licensed under the Apache 2.0 License.

import asyncio
import json
import os
import sys

from fastmcp import FastMCP
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
JINA_API_KEY = os.environ.get("JINA_API_KEY", "")
JINA_BASE_URL = os.environ.get("JINA_BASE_URL", "https://r.jina.ai")

# Initialize FastMCP server
mcp = FastMCP("searching-tavily-mcp-server")


@mcp.tool()
async def tavily_search(
    q: str,
    num: int = 10,
    search_depth: str = "basic",
    topic: str = "general",
) -> str:
    """Perform web searches via Tavily API and retrieve rich results.
    It is able to retrieve organic search results with titles, URLs, and content snippets.

    Args:
        q: Search query string.
        num: The number of results to return (default: 10).
        search_depth: Search depth - 'basic' for fast results or 'advanced' for higher relevance (default: 'basic').
        topic: Search topic - 'general', 'news', or 'finance' (default: 'general').

    Returns:
        The search results.
    """
    if TAVILY_API_KEY == "":
        return (
            "[ERROR]: TAVILY_API_KEY is not set, tavily_search tool is not available."
        )

    tool_name = "tavily_search"
    arguments = {
        "q": q,
        "num": num,
        "search_depth": search_depth,
        "topic": topic,
    }
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "miroflow_tools.mcp_servers.tavily_mcp_server"],
        env={"TAVILY_API_KEY": TAVILY_API_KEY},
    )
    result_content = ""

    retry_count = 0
    max_retries = 3

    while retry_count < max_retries:
        try:
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(
                    read, write, sampling_callback=None
                ) as session:
                    await session.initialize()
                    tool_result = await session.call_tool(
                        tool_name, arguments=arguments
                    )
                    result_content = (
                        tool_result.content[-1].text if tool_result.content else ""
                    )
                    assert (
                        result_content is not None and result_content.strip() != ""
                    ), "Empty result from tavily_search tool, please try again."
                    return result_content  # Success, exit retry loop
        except Exception as error:
            retry_count += 1
            if retry_count >= max_retries:
                return f"[ERROR]: tavily_search tool execution failed after {max_retries} attempts: {str(error)}"
            # Wait before retrying
            await asyncio.sleep(min(2**retry_count, 60))

    return "[ERROR]: Unknown error occurred in tavily_search tool, please try again."


if __name__ == "__main__":
    mcp.run(transport="stdio")
