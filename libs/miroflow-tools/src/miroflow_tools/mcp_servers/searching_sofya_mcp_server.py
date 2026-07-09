# Copyright (c) 2025 MiroMind
# This source code is licensed under the Apache 2.0 License.

"""
Sofya search, scrape, and research MCP server.

Sofya (https://sofya.co) is a web tools API for AI agents. This server exposes
three tools backed by the Sofya REST API:
- sofya_search: web search that returns extracted page content, not just snippets
- scrape_website: fetch a URL as clean markdown (also handles PDF, DOCX, and more)
- sofya_research: decompose a question, read many sources, and return a cited report

Bring your own Sofya API key via the SOFYA_API_KEY environment variable.
"""

import asyncio
import json
import os

import requests
from fastmcp import FastMCP

SOFYA_API_KEY = os.environ.get("SOFYA_API_KEY", "")
SOFYA_BASE_URL = os.environ.get("SOFYA_BASE_URL", "https://sofya.co")

MAX_RETRIES = 3

# Initialize FastMCP server
mcp = FastMCP("searching-sofya-mcp-server")


async def _post_sofya(path: str, payload: dict) -> dict:
    """POST to the Sofya REST API with simple retry on transient network errors.

    Returns the parsed JSON response. Raises the last exception if all
    attempts fail, or requests.HTTPError immediately on a 4xx response.
    """
    url = f"{SOFYA_BASE_URL}/v1/{path}"
    headers = {
        "Authorization": f"Bearer {SOFYA_API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "miroflow-sofya-mcp",
    }

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=180)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as e:
            # Client errors (bad key, bad request) will not succeed on retry.
            status = e.response.status_code if e.response is not None else None
            if status is not None and 400 <= status < 500:
                raise
            last_error = e
        except (requests.ConnectionError, requests.Timeout) as e:
            last_error = e
        await asyncio.sleep(min(2 ** (attempt + 1), 10))

    raise last_error if last_error else RuntimeError("Sofya request failed")


@mcp.tool()
async def sofya_search(query: str, max_results: int = 10) -> str:
    """Search the web with Sofya and get extracted page content, not just snippets.

    Use this for general web search. Each result includes the page title, URL, and
    cleaned main content, so the agent can read sources without a separate scrape step.

    Args:
        query: The search query string. Be specific to improve relevance.
        max_results: Number of results to return (1-20, default: 10).

    Returns:
        The search results in JSON format, including a top-level "answer" when
        available and a "results" array of {title, url, content, description,
        published_date} objects.
    """
    if not SOFYA_API_KEY:
        return "[ERROR]: SOFYA_API_KEY is not set, sofya_search tool is not available."

    if not query or not query.strip():
        return "[ERROR]: Search query is required and cannot be empty."

    payload = {
        "query": query.strip(),
        "max_results": max(1, min(max_results, 20)),
        "search_depth": "basic",
    }

    try:
        data = await _post_sofya("search", payload)
        return json.dumps(data, ensure_ascii=False)
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else "unknown"
        return f"[ERROR]: sofya_search failed with HTTP {status}: {str(e)}"
    except Exception as e:
        return f"[ERROR]: sofya_search failed: {str(e)}"


@mcp.tool()
async def scrape_website(url: str) -> str:
    """Fetch a single web page as clean markdown using Sofya. Also handles PDF, DOCX, and more.

    Search engines are not supported by this tool. Use sofya_search to find pages,
    then scrape_website to read a specific URL in full.

    Args:
        url: The URL of the page to fetch. Must start with http:// or https://.

    Returns:
        The page content as markdown, or an error string.
    """
    if not SOFYA_API_KEY:
        return (
            "[ERROR]: SOFYA_API_KEY is not set, scrape_website tool is not available."
        )

    if not url or not url.startswith(("http://", "https://")):
        return f"Invalid URL: '{url}'. URL must start with http:// or https://"

    try:
        data = await _post_sofya("fetch", {"urls": [url]})
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else "unknown"
        return f"[ERROR]: scrape_website failed with HTTP {status}: {str(e)}"
    except Exception as e:
        return f"[ERROR]: scrape_website failed: {str(e)}"

    results = data.get("results") or []
    if not results:
        return f"No content retrieved from URL: {url}"

    result = results[0]
    if not result.get("success", True):
        return (
            f"[ERROR]: Failed to fetch '{url}': {result.get('error', 'unknown error')}"
        )

    content = (result.get("content") or "").strip()
    if not content:
        return f"No content retrieved from URL: {url}"

    return content


@mcp.tool()
async def sofya_research(query: str) -> str:
    """Run multi-source deep research with Sofya and get back a cited report.

    Sofya decomposes the question into sub-queries, reads many sources in parallel,
    and synthesizes a single report with citations. Use this for open-ended questions
    that need several sources, not for a single lookup (use sofya_search for that).
    This is slower and costs more than a plain search.

    Args:
        query: The research question.

    Returns:
        The research report in JSON format, including "report" (the cited write-up)
        and "sources" (the references used).
    """
    if not SOFYA_API_KEY:
        return (
            "[ERROR]: SOFYA_API_KEY is not set, sofya_research tool is not available."
        )

    if not query or not query.strip():
        return "[ERROR]: Research query is required and cannot be empty."

    try:
        data = await _post_sofya("research", {"query": query.strip()})
        return json.dumps(data, ensure_ascii=False)
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else "unknown"
        return f"[ERROR]: sofya_research failed with HTTP {status}: {str(e)}"
    except Exception as e:
        return f"[ERROR]: sofya_research failed: {str(e)}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
