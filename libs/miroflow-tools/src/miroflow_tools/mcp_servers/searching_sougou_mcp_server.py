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

import os
from fastmcp import FastMCP
import asyncio
import json
import requests

from tencentcloud.common.common_client import CommonClient
from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
    TencentCloudSDKException,
)
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile


TENCENTCLOUD_SECRET_ID = os.environ.get("TENCENTCLOUD_SECRET_ID", "")
TENCENTCLOUD_SECRET_KEY = os.environ.get("TENCENTCLOUD_SECRET_KEY", "")
JINA_API_KEY = os.environ.get("JINA_API_KEY", "")

# Initialize FastMCP server
mcp = FastMCP("searching-sougou-mcp-server")


@mcp.tool()
async def sougou_search(Query: str, Cnt: int = 10) -> str:
    """
    Performs web searches using the Tencent Cloud SearchPro API to retrieve comprehensive information, with Sougou search offering superior results for Chinese-language queries.

    Capabilities:
        - Retrieves structured search results with core details like titles, source URLs, summaries

    Usage examples:
        1. Basic natural search: `{"Query": "today's weather in Beijing", "Cnt": 10}` returns standard weather information and related web results

    Args:
        Query: The core search query string. Be specific to improve result relevance (e.g., "2024 World Cup final results"). (Required, no default value)
        Cnt: Number of search results to return (Can only be 10/20/30/40/50). Optional, default: 10)

    Returns:
        The search results in JSON format, including the following core fields:
        - Query: The original search query (consistent with the input Query, for request verification)
        - Pages: Array of JSON strings, each containing details of a single search result (e.g., title, url, passage, date, site, favicon)
    """

    if TENCENTCLOUD_SECRET_ID == "" or TENCENTCLOUD_SECRET_KEY == "":
        return "TENCENTCLOUD_SECRET_ID or TENCENTCLOUD_SECRET_KEY is not set, sougou_search tool is not available."

    retry_count = 0
    max_retries = 3

    while retry_count < max_retries:
        try:
            cred = credential.Credential(
                TENCENTCLOUD_SECRET_ID, TENCENTCLOUD_SECRET_KEY
            )
            httpProfile = HttpProfile()
            httpProfile.endpoint = "wsa.tencentcloudapi.com"
            clientProfile = ClientProfile()
            clientProfile.httpProfile = httpProfile

            params = f'{{"Query":"{Query}","Mode":0, "Cnt":{Cnt}}}'
            common_client = CommonClient(
                "wsa", "2025-05-08", cred, "", profile=clientProfile
            )
            result = common_client.call_json("SearchPro", json.loads(params))[
                "Response"
            ]
            del result["RequestId"]
            pages = []
            for page in result["Pages"]:
                page_json = json.loads(page)
                new_page = {}
                new_page["title"] = page_json["title"]
                new_page["url"] = page_json["url"]
                new_page["passage"] = page_json["passage"]
                new_page["date"] = page_json["date"]
                # new_page["content"] = page_json["content"]
                new_page["site"] = page_json["site"]
                # new_page["favicon"] = page_json["favicon"]
                pages.append(new_page)
            result["Pages"] = pages
            return json.dumps(result, ensure_ascii=False)
        except TencentCloudSDKException:
            retry_count += 1

            if retry_count >= max_retries:
                return f"Tool execution failed after {max_retries} connection attempts: Unexpected error occurred."

            await asyncio.sleep(
                min(3 * retry_count, 10)
            )  # Exponential backoff with cap


@mcp.tool()
async def scrape_website(url: str) -> str:
    """Extracts and retrieves content from publicly accessible webpages. This tool fetches the HTML content from a specified URL and returns the text content for analysis or information extraction.

    Capabilities:
    - Scrapes static content from publicly accessible webpages
    - Returns raw HTML or text content for further processing

    Limitations:
    - Cannot scrape search engines or search engine results
    - Cannot bypass paywalls, login walls, or access restricted content
    - Limited effectiveness with dynamic websites that load content via JavaScript
    - Does not handle authentication requirements
    - Cannot extract content from PDFs, images, or non-HTML content
    - Does not automatically respect robots.txt or handle rate limiting

    Usage Examples:
    1. Extracting article content: scrape_website(url="https://example.com/article/123") → Returns the article text content
    2. Gathering product information: scrape_website(url="https://example.com/products/smartphone") → Returns product details as displayed on the page

    Args:
        url: The complete URL of the website to scrape, including the protocol (http:// or https://).

    Returns:
        The scraped website content.
    """
    # Validate URL format
    if not url or not url.startswith(("http://", "https://")):
        return f"Invalid URL: '{url}'. URL must start with http:// or https://"

    # Check for restricted domains
    if "huggingface.co/datasets" in url or "huggingface.co/spaces" in url:
        return "You are trying to scrape a Hugging Face dataset for answers, please do not use the scrape tool for this purpose."

    if JINA_API_KEY == "":
        return "JINA_API_KEY is not set, scrape_website tool is not available."

    try:
        # Use Jina.ai reader API to convert URL to LLM-friendly text
        jina_url = f"https://r.jina.ai/{url}"

        # Make request with proper headers
        headers = {"Authorization": f"Bearer {JINA_API_KEY}"}

        response = requests.get(jina_url, headers=headers, timeout=60)
        response.raise_for_status()

        # Get the content
        content = response.text.strip()

        if not content:
            return f"No content retrieved from URL: {url}"

        return content

    except requests.exceptions.Timeout:
        return f"Timeout Error: Request timed out while scraping '{url}'. The website may be slow or unresponsive."

    except requests.exceptions.ConnectionError:
        return f"Connection Error: Failed to connect to '{url}'. Please check if the URL is correct and accessible."

    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response else "unknown"
        if status_code == 404:
            return f"Page Not Found (404): The page at '{url}' does not exist."
        elif status_code == 403:
            return f"Access Forbidden (403): Access to '{url}' is forbidden."
        elif status_code == 500:
            return f"Server Error (500): The server at '{url}' encountered an internal error."
        else:
            return f"HTTP Error ({status_code}): Failed to scrape '{url}'. {str(e)}"

    except requests.exceptions.RequestException as e:
        return f"Request Error: Failed to scrape '{url}'. {str(e)}"

    except Exception as e:
        return f"Unexpected Error: An unexpected error occurred while scraping '{url}': {str(e)}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
