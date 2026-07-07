# Copyright (c) 2025 MiroMind
# This source code is licensed under the Apache 2.0 License.

"""
You.com Search and Research MCP server.

Provides two tools backed by the You.com API:
- ``youcom_search``: web search returning organic results (title, url, snippet).
- ``youcom_research``: multi-step research with synthesized, cited answers.

Authentication uses the ``YDC_API_KEY`` environment variable (X-API-Key header).
"""

import json
import os
from typing import Any, Dict

import requests
from mcp.server.fastmcp import FastMCP
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .utils import decode_http_urls_in_dict

YOUCOM_API_KEY = os.getenv("YDC_API_KEY", "")
YOUCOM_SEARCH_URL = os.getenv(
    "YOUCOM_SEARCH_URL", "https://api.you.com/v1/agents/search"
)
YOUCOM_RESEARCH_URL = os.getenv(
    "YOUCOM_RESEARCH_URL", "https://api.you.com/v1/research"
)

# Initialize FastMCP server
mcp = FastMCP("youcom-mcp-server")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type(
        (requests.ConnectionError, requests.Timeout, requests.HTTPError)
    ),
)
def _post_json(url: str, payload: Dict[str, Any], headers: Dict[str, str]) -> dict:
    """POST JSON to *url* and return the parsed response body."""
    response = requests.post(url, json=payload, headers=headers, timeout=60)
    response.raise_for_status()
    return response.json()


def _error(msg: str) -> str:
    return json.dumps({"success": False, "error": msg, "results": []},
                      ensure_ascii=False)


@mcp.tool()
def youcom_search(
    query: str,
    max_results: int = 10,
) -> str:
    """
    Perform web searches via the You.com Search API and retrieve organic results.

    Args:
        query: Search query string.
        max_results: Maximum number of results to return (default: 10).

    Returns:
        JSON string with a ``results`` array (each item has ``title``,
        ``url``, ``snippet``) and an ``images`` array.
    """
    if not YOUCOM_API_KEY:
        return _error("YDC_API_KEY environment variable not set")

    if not query or not query.strip():
        return _error("Search query is required and cannot be empty")

    try:
        data = _post_json(
            YOUCOM_SEARCH_URL,
            {"query": query.strip(), "max_results": max_results},
            {"X-API-Key": YOUCOM_API_KEY, "Content-Type": "application/json"},
        )
        data = decode_http_urls_in_dict(data)
        return json.dumps(data, ensure_ascii=False)
    except Exception as e:
        return _error(f"Unexpected error: {e}")


@mcp.tool()
def youcom_research(
    input: str,
    research_effort: str = "standard",
) -> str:
    """
    Obtain a comprehensive, well-cited research answer via the You.com Research API.

    The Research API runs multiple searches, reads sources, and synthesises a
    thorough response with inline citations — useful when a single web search is
    insufficient for a complex question.

    Args:
        input: The research question or complex query (max 40 000 characters).
        research_effort: Controls depth vs. speed. One of ``lite``,
            ``standard`` (default), ``deep``, or ``exhaustive``.

    Returns:
        JSON string with an ``output`` object containing ``content`` (the
        synthesised answer with inline citations), ``content_type``, and a
        ``sources`` array (each with ``url``, ``title``, ``snippets``).
    """
    if not YOUCOM_API_KEY:
        return _error("YDC_API_KEY environment variable not set")

    if not input or not input.strip():
        return _error("Research input is required and cannot be empty")

    valid_efforts = ("lite", "standard", "deep", "exhaustive")
    if research_effort not in valid_efforts:
        return _error(
            f"Invalid research_effort '{research_effort}'. "
            f"Must be one of: {', '.join(valid_efforts)}"
        )

    try:
        data = _post_json(
            YOUCOM_RESEARCH_URL,
            {"input": input.strip(), "research_effort": research_effort},
            {"X-API-Key": YOUCOM_API_KEY, "Content-Type": "application/json"},
        )
        return json.dumps(data, ensure_ascii=False)
    except Exception as e:
        return _error(f"Unexpected error: {e}")


if __name__ == "__main__":
    mcp.run()
