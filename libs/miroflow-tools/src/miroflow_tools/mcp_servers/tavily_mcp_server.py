# Copyright (c) 2025 MiroMind
# This source code is licensed under the Apache 2.0 License.

"""
MCP server for Tavily web search.

Provides a tool-tavily-search MCP tool that uses the Tavily API
to perform web searches optimized for LLM consumption.
"""

import json
import os

from mcp.server.fastmcp import FastMCP
from tavily import TavilyClient

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# Initialize FastMCP server
mcp = FastMCP("tavily-mcp-server")


@mcp.tool()
def tavily_search(
    query: str,
    max_results: int = 10,
    search_depth: str = "basic",
    topic: str = "general",
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    time_range: str | None = None,
) -> str:
    """Perform web searches via Tavily API and retrieve results optimized for LLMs.

    Args:
        query: Search query string (keep under 400 characters for best results).
        max_results: Maximum number of results to return (default: 10).
        search_depth: Search depth - 'basic' (fast, 1 credit) or 'advanced' (thorough, 2 credits). Default is 'basic'.
        topic: Search topic category - 'general', 'news', or 'finance'. Default is 'general'.
        include_domains: Optional list of domains to restrict search to (e.g., ['wikipedia.org', 'arxiv.org']).
        exclude_domains: Optional list of domains to exclude from search results.
        time_range: Optional time filter - 'day', 'week', 'month', or 'year'.

    Returns:
        JSON string containing search results with title, url, content, and relevance score.
    """
    if not TAVILY_API_KEY:
        return json.dumps(
            {
                "success": False,
                "error": "TAVILY_API_KEY environment variable not set",
                "results": [],
            },
            ensure_ascii=False,
        )

    if not query or not query.strip():
        return json.dumps(
            {
                "success": False,
                "error": "Search query is required and cannot be empty",
                "results": [],
            },
            ensure_ascii=False,
        )

    try:
        client = TavilyClient(api_key=TAVILY_API_KEY)

        kwargs = {
            "query": query.strip(),
            "max_results": max_results,
            "search_depth": search_depth,
            "topic": topic,
        }
        if include_domains:
            kwargs["include_domains"] = include_domains
        if exclude_domains:
            kwargs["exclude_domains"] = exclude_domains
        if time_range:
            kwargs["time_range"] = time_range

        response = client.search(**kwargs)

        return json.dumps(response, ensure_ascii=False)

    except Exception as e:
        return json.dumps(
            {"success": False, "error": f"Unexpected error: {str(e)}", "results": []},
            ensure_ascii=False,
        )


if __name__ == "__main__":
    mcp.run()
