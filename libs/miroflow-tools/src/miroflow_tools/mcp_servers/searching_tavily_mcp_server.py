# Copyright (c) 2025 MiroMind
# This source code is licensed under the Apache 2.0 License.

import asyncio
import json
import os
import sys

import requests
from fastmcp import FastMCP
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .utils import strip_markdown_links

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
JINA_API_KEY = os.environ.get("JINA_API_KEY", "")
JINA_BASE_URL = os.environ.get("JINA_BASE_URL", "https://r.jina.ai")

# Initialize FastMCP server
mcp = FastMCP("searching-tavily-mcp-server")


@mcp.tool()
async def tavily_search(
    q: str,
    num: int = 10,
    search_depth: str = "basic",
    topic: str = "general",
) -> str:
    """Perform web searches via Tavily API and retrieve rich results.
    It is able to retrieve organic search results with titles, URLs, and content snippets.

    Args:
        q: Search query string.
        num: The number of results to return (default: 10).
        search_depth: Search depth - 'basic' for fast results or 'advanced' for higher relevance (default: 'basic').
        topic: Search topic - 'general', 'news', or 'finance' (default: 'general').

    Returns:
        The search results.
    """
    if TAVILY_API_KEY == "":
        return (
            "[ERROR]: TAVILY_API_KEY is not set, tavily_search tool is not available."
        )

    tool_name = "tavily_search"
    arguments = {
        "q": q,
        "num": num,
        "search_depth": search_depth,
        "topic": topic,
    }
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "miroflow_tools.mcp_servers.tavily_mcp_server"],
        env={"TAVILY_API_KEY": TAVILY_API_KEY},
    )
    result_content = ""

    retry_count = 0
    max_retries = 3

    while retry_count < max_retries:
        try:
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(
                    read, write, sampling_callback=None
                ) as session:
                    await session.initialize()
                    tool_result = await session.call_tool(
                        tool_name, arguments=arguments
                    )
                    result_content = (
                        tool_result.content[-1].text if tool_result.content else ""
                    )
                    assert (
                        result_content is not None and result_content.strip() != ""
                    ), "Empty result from tavily_search tool, please try again."
                    return result_content  # Success, exit retry loop
        except Exception as error:
            retry_count += 1
            if retry_count >= max_retries:
                return f"[ERROR]: tavily_search tool execution failed after {max_retries} attempts: {str(error)}"
            # Wait before retrying
            await asyncio.sleep(min(2**retry_count, 60))

    return "[ERROR]: Unknown error occurred in tavily_search tool, please try again."


@mcp.tool()
async def scrape_website(url: str) -> str:
    """This tool is used to scrape a website for its content. Search engines are not supported by this tool. This tool can also be used to get YouTube video non-visual information (however, it may be incomplete), such as video subtitles, titles, descriptions, key moments, etc.

    Args:
        url: The URL of the website to scrape.
    Returns:
        The scraped website content.
    """
    # Validate URL format
    if not url or not url.startswith(("http://", "https://")):
        return f"Invalid URL: '{url}'. URL must start with http:// or https://"

    # Avoid duplicate Jina URL prefix
    if url.startswith("https://r.jina.ai/") and url.count("http") >= 2:
        url = url[len("https://r.jina.ai/") :]

    # Check for restricted domains
    if "huggingface.co/datasets" in url or "huggingface.co/spaces" in url:
        return "You are trying to scrape a Hugging Face dataset for answers, please do not use the scrape tool for this purpose."

    if JINA_API_KEY == "":
        return "JINA_API_KEY is not set, scrape_website tool is not available."

    try:
        # Use Jina.ai reader API to convert URL to LLM-friendly text
        jina_url = f"{JINA_BASE_URL}/{url}"

        # Make request with proper headers
        headers = {"Authorization": f"Bearer {JINA_API_KEY}"}

        response = requests.get(jina_url, headers=headers, timeout=60)
        response.raise_for_status()

        # Get the content
        content = response.text.strip()
        content = strip_markdown_links(content)

        if not content:
            return f"No content retrieved from URL: {url}"

        return content

    except requests.exceptions.Timeout:
        return f"[ERROR]: Timeout Error: Request timed out while scraping '{url}'. The website may be slow or unresponsive."

    except requests.exceptions.ConnectionError:
        return f"[ERROR]: Connection Error: Failed to connect to '{url}'. Please check if the URL is correct and accessible."

    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response else "unknown"
        if status_code == 404:
            return f"[ERROR]: Page Not Found (404): The page at '{url}' does not exist."
        elif status_code == 403:
            return f"[ERROR]: Access Forbidden (403): Access to '{url}' is forbidden."
        elif status_code == 500:
            return f"[ERROR]: Server Error (500): The server at '{url}' encountered an internal error."
        else:
            return f"[ERROR]: HTTP Error ({status_code}): Failed to scrape '{url}'. {str(e)}"

    except requests.exceptions.RequestException as e:
        return f"[ERROR]: Request Error: Failed to scrape '{url}'. {str(e)}"

    except Exception as e:
        return f"[ERROR]: Unexpected Error: An unexpected error occurred while scraping '{url}': {str(e)}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
