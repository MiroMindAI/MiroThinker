# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

import json
import logging
import os
from typing import Any, Dict

import httpx
from mcp.server.fastmcp import FastMCP
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from tencentcloud.common import credential
from tencentcloud.common.common_client import CommonClient
from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
    TencentCloudSDKException,
)
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile

from ..mcp_servers.utils.url_unquote import decode_http_urls_in_dict

# Configure logging
logger = logging.getLogger("miroflow")

SERPER_BASE_URL = os.getenv("SERPER_BASE_URL", "https://google.serper.dev")
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")

TENCENTCLOUD_SECRET_ID = os.getenv("TENCENTCLOUD_SECRET_ID", "")
TENCENTCLOUD_SECRET_KEY = os.getenv("TENCENTCLOUD_SECRET_KEY", "")

# Initialize FastMCP server
mcp = FastMCP("search_and_scrape_webpage")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type(
        (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError)
    ),
)
async def make_serper_request(
    payload: Dict[str, Any], headers: Dict[str, str]
) -> httpx.Response:
    """Make HTTP request to Serper API with retry logic."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{SERPER_BASE_URL}/search",
            json=payload,
            headers=headers,
        )
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
async def google_search(
    q: str,
    gl: str = "us",
    hl: str = "en",
    location: str = None,
    num: int = None,
    tbs: str = None,
    page: int = None,
    autocorrect: bool = None,
):
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
        tbs: Time-based search filter ('qdr:h' for past hour, 'qdr:d' for past day, 'qdr:w' for past week, 'qdr:m' for past month, 'qdr:y' for past year)
        page: Page number of results to return (default: 1)
        autocorrect: Whether to autocorrect spelling in query

    Returns:
        Dictionary containing search results and metadata.
    """
    # Check for API key
    if not SERPER_API_KEY:
        return json.dumps(
            {
                "success": False,
                "error": "SERPER_API_KEY environment variable not set",
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
        # Helper function to perform a single search
        async def perform_search(search_query: str) -> tuple[list, dict]:
            """Perform a search and return organic results and search parameters."""
            # Build payload with all supported parameters
            payload: dict[str, Any] = {
                "q": search_query.strip(),
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
            headers = {
                "X-API-KEY": SERPER_API_KEY,
                "Content-Type": "application/json",
            }

            # Make the API request
            response = await make_serper_request(payload, headers)
            data = response.json()

            # filter out HuggingFace dataset or space urls
            organic_results = []
            if "organic" in data:
                for item in data["organic"]:
                    if _is_huggingface_dataset_or_space_url(item.get("link", "")):
                        continue
                    organic_results.append(item)

            return organic_results, data.get("searchParameters", {})

        # Perform initial search
        original_query = q.strip()
        organic_results, search_params = await perform_search(original_query)

        # If no results and query contains quotes, retry without quotes
        if not organic_results and '"' in original_query:
            # Remove all types of quotes
            query_without_quotes = original_query.replace('"', "").strip()
            if query_without_quotes:  # Make sure we still have a valid query
                organic_results, search_params = await perform_search(
                    query_without_quotes
                )

        # Build comprehensive response
        response_data = {
            "organic": organic_results,
            "searchParameters": search_params,
        }
        response_data = decode_http_urls_in_dict(response_data)

        return json.dumps(response_data, ensure_ascii=False)

    except Exception as e:
        return json.dumps(
            {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "results": [],
            },
            ensure_ascii=False,
        )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type(TencentCloudSDKException),
)
async def make_sogou_request(query: str, cnt: int) -> Dict[str, Any]:
    """Make request to Tencent Cloud SearchPro API with retry logic."""
    cred = credential.Credential(TENCENTCLOUD_SECRET_ID, TENCENTCLOUD_SECRET_KEY)
    httpProfile = HttpProfile()
    httpProfile.endpoint = "wsa.tencentcloudapi.com"
    clientProfile = ClientProfile()
    clientProfile.httpProfile = httpProfile

    params = f'{{"Query":"{query}","Mode":0, "Cnt":{cnt}}}'
    common_client = CommonClient("wsa", "2025-05-08", cred, "", profile=clientProfile)
    result = common_client.call_json("SearchPro", json.loads(params))["Response"]
    return result


@mcp.tool()
async def sogou_search(
    q: str,
    num: int = 10,
) -> str:
    """
    Tool to perform web searches via Tencent Cloud SearchPro API (Sogou search engine).

    Sogou search offers superior results for Chinese-language queries compared to Google.

    Args:
        q: Search query string (Required)
        num: Number of search results to return (Can only be 10/20/30/40/50, default: 10)

    Returns:
        JSON string containing search results with the following fields:
        - Query: The original search query
        - Pages: Array of search results, each containing title, url, passage, date, and site
    """
    # Check for API credentials
    if not TENCENTCLOUD_SECRET_ID or not TENCENTCLOUD_SECRET_KEY:
        return json.dumps(
            {
                "success": False,
                "error": "TENCENTCLOUD_SECRET_ID or TENCENTCLOUD_SECRET_KEY environment variable not set",
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

    # Validate num parameter
    if num not in [10, 20, 30, 40, 50]:
        return json.dumps(
            {
                "success": False,
                "error": f"Invalid num value: {num}. Must be one of 10, 20, 30, 40, 50",
                "results": [],
            },
            ensure_ascii=False,
        )

    try:
        # Make the API request
        result = await make_sogou_request(q.strip(), num)

        # Remove RequestId from response
        if "RequestId" in result:
            del result["RequestId"]

        # Process and simplify the Pages field
        pages = []
        if "Pages" in result:
            for page in result["Pages"]:
                page_json = json.loads(page)
                new_page = {
                    "title": page_json.get("title", ""),
                    "url": page_json.get("url", ""),
                    "passage": page_json.get("passage", ""),
                    "date": page_json.get("date", ""),
                    "site": page_json.get("site", ""),
                }
                pages.append(new_page)
            result["Pages"] = pages

        # Decode URLs in the response
        result = decode_http_urls_in_dict(result)

        return json.dumps(result, ensure_ascii=False)

    except TencentCloudSDKException as e:
        return json.dumps(
            {
                "success": False,
                "error": f"Tencent Cloud API error: {str(e)}",
                "results": [],
            },
            ensure_ascii=False,
        )

    except Exception as e:
        return json.dumps(
            {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "results": [],
            },
            ensure_ascii=False,
        )


if __name__ == "__main__":
    mcp.run()
