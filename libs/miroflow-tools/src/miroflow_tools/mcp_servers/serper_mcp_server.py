# Copyright 2025 Miromind.ai
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
adapted from
https://github.com/MiroMindAI/MiroRL/blob/5073693549ffe05a157a1886e87650ef3be6606e/mirorl/tools/serper_search.py#L1
"""

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

# Initialize FastMCP server
mcp = FastMCP("search_and_scrape_webpage")
SERPER_BASE_URL = os.getenv("SERPER_BASE_URL", "https://google.serper.dev")
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type(
        (requests.ConnectionError, requests.Timeout, requests.HTTPError)
    ),
)
def make_serper_request(
    payload: Dict[str, Any], headers: Dict[str, str]
) -> requests.Response:
    """Make HTTP request to Serper API with retry logic."""
    response = requests.post(f"{SERPER_BASE_URL}/search", json=payload, headers=headers)
    response.raise_for_status()
    return response


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
def google_search(
    q: str,
    gl: str = "us",
    hl: str = "en",
    location: str | None = None,
    num: int | None = None,
    tbs: str | None = None,
    page: int | None = None,
    autocorrect: bool | None = None,
) -> Dict[str, Any]:
    """
    Tool to perform web searches via Serper API and retrieve rich results.

    It is able to retrieve organic search results, people also ask,
    related searches, and knowledge graph.

    Args:
        q: Search query string
        gl: Optional region code for search results in ISO 3166-1 alpha-2 format (e.g., 'us')
        hl: Optional language code for search results in ISO 639-1 format (e.g., 'en')
        location: Optional location for search results (e.g., 'SoHo, New York, United States', 'California, United States')
        num: Number of results to return (default: 10)
        tbs: Time-based search filter ('qdr:h' for past hour, 'qdr:d' for past day, 'qdr:w' for past week,
            'qdr:m' for past month, 'qdr:y' for past year)
        page: Page number of results to return (default: 1)
        autocorrect: Whether to autocorrect spelling in query

    Returns:
        Dictionary containing search results and metadata
    """

    # Check for API key
    if not SERPER_API_KEY:
        return {
            "success": False,
            "error": "SERPER_API_KEY environment variable not set",
            "results": [],
        }

    # Validate required parameter
    if not q or not q.strip():
        return {
            "success": False,
            "error": "Search query 'q' is required and cannot be empty",
            "results": [],
        }

    try:
        # Build payload with all supported parameters
        payload: dict[str, Any] = {
            "q": q.strip(),
            "gl": gl,
            "hl": hl,
        }

        # Add optional parameters if provided
        if location:
            payload["location"] = location
        if num is not None:
            payload["num"] = num
        else:
            payload["num"] = 10  # Default
        if tbs:
            payload["tbs"] = tbs
        if page is not None:
            payload["page"] = page
        if autocorrect is not None:
            payload["autocorrect"] = autocorrect

        # Set up headers
        headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}

        # Make the API request
        response = make_serper_request(payload, headers)
        data = response.json()

        # filter out HuggingFace dataset or space urls
        organic_results = []
        if "organic" in data:
            for item in data["organic"]:
                if _is_huggingface_dataset_or_space_url(item.get("link", "")):
                    continue
                organic_results.append(item)

        # Build comprehensive response
        response_data = {
            "organic": organic_results,
            "searchParameters": data.get("searchParameters", {}),
        }

        return response_data

    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {str(e)}", "results": []}


if __name__ == "__main__":
    mcp.run()
