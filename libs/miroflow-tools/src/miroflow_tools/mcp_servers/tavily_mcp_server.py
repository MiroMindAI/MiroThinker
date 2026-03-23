# Copyright (c) 2025 MiroMind
# This source code is licensed under the Apache 2.0 License.

"""
Tavily-backed MCP server providing a tavily_search tool as a parallel
alternative to the Serper-backed google_search tool.
"""

import json
import os

from mcp.server.fastmcp import FastMCP
from tavily import TavilyClient
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# Initialize FastMCP server
mcp = FastMCP("tavily-mcp-server")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((ConnectionError, TimeoutError)),
)
def _tavily_search_request(client: TavilyClient, **kwargs) -> dict:
    """Execute a Tavily search with retry logic."""
    return client.search(**kwargs)


@mcp.tool()
def tavily_search(
    query: str,
    max_results: int = 10,
    search_depth: str = "basic",
    topic: str = "general",
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    time_range: str | None = None,
):
    """
    Tool to perform web searches via Tavily API and retrieve rich results.

    It returns organic search results with titles, URLs, content snippets,
    and relevance scores.

    Args:
        query: Search query string (max 400 characters recommended)
        max_results: Number of results to return (default: 10)
        search_depth: Search depth - 'basic' (fast, 1 credit) or 'advanced' (thorough, 2 credits)
        topic: Search topic category - 'general', 'news', or 'finance'
        include_domains: Optional list of domains to restrict results to
        exclude_domains: Optional list of domains to exclude from results
        time_range: Optional time range filter ('day', 'week', 'month', 'year')

    Returns:
        JSON string containing search results and metadata.
    """
    # Check for API key
    if not TAVILY_API_KEY:
        return json.dumps(
            {
                "success": False,
                "error": "TAVILY_API_KEY environment variable not set",
                "results": [],
            },
            ensure_ascii=False,
        )

    # Validate required parameter
    if not query or not query.strip():
        return json.dumps(
            {
                "success": False,
                "error": "Search query 'query' is required and cannot be empty",
                "results": [],
            },
            ensure_ascii=False,
        )

    try:
        client = TavilyClient(api_key=TAVILY_API_KEY)

        # Build keyword arguments
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

        # Make the API request with retry
        data = _tavily_search_request(client, **kwargs)

        return json.dumps(data, ensure_ascii=False)

    except Exception as e:
        return json.dumps(
            {"success": False, "error": f"Unexpected error: {str(e)}", "results": []},
            ensure_ascii=False,
        )


if __name__ == "__main__":
    mcp.run()
