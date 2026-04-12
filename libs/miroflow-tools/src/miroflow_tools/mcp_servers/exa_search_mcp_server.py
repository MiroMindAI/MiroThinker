# Copyright (c) 2025 MiroMind
# This source code is licensed under the Apache 2.0 License.

"""
Exa AI-powered search MCP server.

Provides web search with built-in content retrieval (highlights, text, summary)
through the Exa API. Supports multiple search types, domain/text filtering,
category filtering, and date range queries.
"""

import json
import os
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

EXA_API_KEY = os.getenv("EXA_API_KEY", "")

# Initialize FastMCP server
mcp = FastMCP("exa-search-mcp-server")


def _get_exa_client():
    """Create and return an Exa client with integration tracking header."""
    from exa_py import Exa

    client = Exa(api_key=EXA_API_KEY)
    client.headers["x-exa-integration"] = "mirothinker"
    return client


@mcp.tool()
def exa_search(
    q: str,
    search_type: str = "auto",
    num_results: int = 10,
    content_mode: str = "highlights",
    category: str | None = None,
    include_domains: str | None = None,
    exclude_domains: str | None = None,
    include_text: str | None = None,
    exclude_text: str | None = None,
    start_published_date: str | None = None,
    end_published_date: str | None = None,
) -> str:
    """
    Perform AI-powered web search via Exa API with built-in content retrieval.

    Unlike traditional keyword search, Exa uses neural search to understand
    query meaning and return semantically relevant results with content.

    Args:
        q: Search query string. For best results, phrase as a natural language
            statement describing the ideal page (e.g., "research paper about
            transformer architectures for code generation" rather than
            "transformer code generation paper").
        search_type: Search type. Options: 'auto' (default, intelligently
            combines methods), 'neural' (embedding-based), 'fast' (optimized
            for speed).
        num_results: Number of results to return (default: 10, max: 100).
        content_mode: Content retrieval mode. Options: 'highlights' (default,
            key passages), 'text' (full page text), 'summary' (LLM-generated
            summary), 'none' (URLs and titles only).
        category: Filter by content category. Options: 'research paper', 'news',
            'company', 'personal site', 'financial report', 'people'.
        include_domains: Comma-separated list of domains to restrict results to
            (e.g., "arxiv.org,github.com").
        exclude_domains: Comma-separated list of domains to exclude from results
            (e.g., "pinterest.com,quora.com").
        include_text: Text that must appear in the results (single phrase, up to
            5 words).
        exclude_text: Text that must not appear in the results.
        start_published_date: Filter results published after this date
            (ISO 8601 format, e.g., "2024-01-01T00:00:00.000Z").
        end_published_date: Filter results published before this date
            (ISO 8601 format, e.g., "2024-12-31T23:59:59.000Z").

    Returns:
        JSON string containing search results with content.
    """
    if not EXA_API_KEY:
        return json.dumps(
            {
                "success": False,
                "error": "EXA_API_KEY environment variable not set",
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
        client = _get_exa_client()

        # Build search kwargs
        kwargs: Dict[str, Any] = {
            "query": q.strip(),
            "type": search_type,
            "num_results": min(num_results, 100),
        }

        # Content retrieval options
        if content_mode == "highlights":
            kwargs["highlights"] = {"max_characters": 4000}
        elif content_mode == "text":
            kwargs["text"] = {"max_characters": 10000}
        elif content_mode == "summary":
            kwargs["summary"] = True

        # Category filtering
        if category:
            kwargs["category"] = category

        # Domain filtering
        if include_domains:
            kwargs["include_domains"] = [
                d.strip() for d in include_domains.split(",") if d.strip()
            ]
        if exclude_domains:
            kwargs["exclude_domains"] = [
                d.strip() for d in exclude_domains.split(",") if d.strip()
            ]

        # Text filtering
        if include_text:
            kwargs["include_text"] = [include_text.strip()]
        if exclude_text:
            kwargs["exclude_text"] = [exclude_text.strip()]

        # Date range filtering
        if start_published_date:
            kwargs["start_published_date"] = start_published_date
        if end_published_date:
            kwargs["end_published_date"] = end_published_date

        # Execute search with content retrieval
        use_contents = content_mode and content_mode != "none"
        if use_contents:
            response = client.search_and_contents(**kwargs)
        else:
            # Remove content-related keys for plain search
            kwargs.pop("highlights", None)
            kwargs.pop("text", None)
            kwargs.pop("summary", None)
            response = client.search(**kwargs)

        # Process results
        results: List[Dict[str, Any]] = []
        for result in response.results:
            entry: Dict[str, Any] = {
                "title": getattr(result, "title", "") or "",
                "url": getattr(result, "url", "") or "",
            }

            # Add content based on mode
            if content_mode == "highlights":
                highlights = getattr(result, "highlights", None)
                if highlights:
                    entry["highlights"] = highlights
            elif content_mode == "text":
                text = getattr(result, "text", None)
                if text:
                    entry["text"] = text
            elif content_mode == "summary":
                summary = getattr(result, "summary", None)
                if summary:
                    entry["summary"] = summary

            # Add optional metadata
            published_date = getattr(result, "published_date", None)
            if published_date:
                entry["publishedDate"] = published_date

            author = getattr(result, "author", None)
            if author:
                entry["author"] = author

            results.append(entry)

        return json.dumps(
            {"success": True, "results": results},
            ensure_ascii=False,
        )

    except Exception as e:
        return json.dumps(
            {"success": False, "error": f"Exa search error: {str(e)}", "results": []},
            ensure_ascii=False,
        )


if __name__ == "__main__":
    mcp.run()
