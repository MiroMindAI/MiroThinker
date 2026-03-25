# Copyright (c) 2025 MiroMind
# This source code is licensed under the Apache 2.0 License.

"""
Tavily search MCP server - parallel alternative to serper_mcp_server.py.
Provides web search via the Tavily API.
"""

import json
import os
from typing import Any, Dict

from mcp.server.fastmcp import FastMCP
from tavily import TavilyClient

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# Initialize FastMCP server
mcp = FastMCP("tavily-mcp-server")


def make_tavily_request(
    client: TavilyClient, query: str, max_results: int, search_depth: str, topic: str
) -> Dict[str, Any]:
    """Make Tavily search request."""
    return client.search(
        query=query,
        max_results=max_results,
        search_depth=search_depth,
        topic=topic,
    )


def _is_huggingface_dataset_or_space_url(url):
    """
    Check if the URL is a HuggingFace dataset or space URL.
    :param url: The URL to check
    :return: True if it's a HuggingFace dataset or space URL, False otherwise
    """
    if not url:
        return False
    return "huggingface.co/datasets" in url or "huggingface.co/spaces" in url


@mcp.tool()
def tavily_search(
    q: str,
    num: int = 10,
    search_depth: str = "basic",
    topic: str = "general",
):
    """
    Tool to perform web searches via Tavily API and retrieve rich results.

    It is able to retrieve organic search results with titles, URLs, and content snippets.

    Args:
        q: Search query string
        num: Number of results to return (default: 10)
        search_depth: Search depth - 'basic' for fast results or 'advanced' for higher relevance (default: 'basic')
        topic: Search topic - 'general', 'news', or 'finance' (default: 'general')

    Returns:
        Dictionary containing search results and metadata.
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
    if not q or not q.strip():
        return json.dumps(
            {
                "success": False,
                "error": "Search query 'q' is required and cannot be empty",
                "results": [],
            },
            ensure_ascii=False,
        )

    try:
        client = TavilyClient(api_key=TAVILY_API_KEY)
        data = make_tavily_request(
            client=client,
            query=q.strip(),
            max_results=num,
            search_depth=search_depth,
            topic=topic,
        )

        # Filter out HuggingFace dataset or space URLs and normalize to
        # match the serper_mcp_server organic result structure
        organic_results = []
        for item in data.get("results", []):
            url = item.get("url", "")
            if _is_huggingface_dataset_or_space_url(url):
                continue
            organic_results.append(
                {
                    "title": item.get("title", ""),
                    "link": item.get("url", ""),
                    "snippet": item.get("content", ""),
                    "score": item.get("score", 0),
                }
            )

        response_data = {
            "organic": organic_results,
            "searchParameters": {
                "q": q.strip(),
                "type": "search",
                "engine": "tavily",
            },
        }

        return json.dumps(response_data, ensure_ascii=False)

    except Exception as e:
        return json.dumps(
            {"success": False, "error": f"Unexpected error: {str(e)}", "results": []},
            ensure_ascii=False,
        )


if __name__ == "__main__":
    mcp.run()
