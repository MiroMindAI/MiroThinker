# Copyright (c) 2025 MiroMind
# This source code is licensed under the Apache 2.0 License.

"""
Tavily search MCP server — parallel alternative to serper_mcp_server.py.
Exposes a single ``tavily_search`` tool via FastMCP.
"""

import json
import os
from typing import Any, Dict, List

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
def make_tavily_request(
    client: TavilyClient,
    query: str,
    max_results: int = 10,
    search_depth: str = "advanced",
    topic: str = "general",
    include_domains: List[str] | None = None,
    exclude_domains: List[str] | None = None,
    time_range: str | None = None,
) -> Dict[str, Any]:
    """Make a search request to Tavily API with retry logic."""
    kwargs: Dict[str, Any] = {
        "query": query,
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
    return client.search(**kwargs)


def _is_huggingface_dataset_or_space_url(url: str) -> bool:
    """Check if the URL is a HuggingFace dataset or space URL."""
    if not url:
        return False
    return "huggingface.co/datasets" in url or "huggingface.co/spaces" in url


@mcp.tool()
def tavily_search(
    q: str,
    num: int = 10,
    search_depth: str = "advanced",
    topic: str = "general",
    time_range: str | None = None,
):
    """
    Tool to perform web searches via Tavily API and retrieve rich results.

    It is able to retrieve organic search results with titles, URLs,
    content snippets, and relevance scores.

    Args:
        q: Search query string
        num: Number of results to return (default: 10)
        search_depth: Search depth — 'basic' or 'advanced' (default: 'advanced')
        topic: Search topic — 'general', 'news', or 'finance' (default: 'general')
        time_range: Time range filter — 'day', 'week', 'month', 'year', or None

    Returns:
        JSON string containing search results and metadata.
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
            time_range=time_range,
        )

        # Filter out HuggingFace dataset/space URLs
        filtered_results = []
        for item in data.get("results", []):
            if _is_huggingface_dataset_or_space_url(item.get("url", "")):
                continue
            filtered_results.append(item)

        # Build response in a structure parallel to the serper output
        response_data: Dict[str, Any] = {
            "query": data.get("query", q),
            "organic": [
                {
                    "title": r.get("title", ""),
                    "link": r.get("url", ""),
                    "snippet": r.get("content", ""),
                    "score": r.get("score", 0),
                }
                for r in filtered_results
            ],
        }
        if data.get("answer"):
            response_data["answerBox"] = {"answer": data["answer"]}

        return json.dumps(response_data, ensure_ascii=False)

    except Exception as e:
        return json.dumps(
            {"success": False, "error": f"Unexpected error: {str(e)}", "results": []},
            ensure_ascii=False,
        )


if __name__ == "__main__":
    mcp.run()
