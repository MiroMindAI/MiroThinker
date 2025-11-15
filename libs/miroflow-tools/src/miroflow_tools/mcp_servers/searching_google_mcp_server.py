# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

import asyncio
import calendar
import datetime
import json
import os
import sys

import requests
import wikipedia
from fastmcp import FastMCP
from mcp import ClientSession, StdioServerParameters  # (already imported in config.py)
from mcp.client.stdio import stdio_client

from .utils import strip_markdown_links

SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "")
SERPER_BASE_URL = os.environ.get("SERPER_BASE_URL", "https://google.serper.dev")
JINA_API_KEY = os.environ.get("JINA_API_KEY", "")
JINA_BASE_URL = os.environ.get("JINA_BASE_URL", "https://r.jina.ai")

# Google search result filtering environment variables
REMOVE_SNIPPETS = os.environ.get("REMOVE_SNIPPETS", "").lower() in ("true", "1", "yes")
REMOVE_KNOWLEDGE_GRAPH = os.environ.get("REMOVE_KNOWLEDGE_GRAPH", "").lower() in (
    "true",
    "1",
    "yes",
)
REMOVE_ANSWER_BOX = os.environ.get("REMOVE_ANSWER_BOX", "").lower() in (
    "true",
    "1",
    "yes",
)

# Initialize FastMCP server
mcp = FastMCP("searching-google-mcp-server")


def filter_google_search_result(result_content: str) -> str:
    """Filter google search result content based on environment variables.

    Args:
        result_content: The JSON string result from google search

    Returns:
        Filtered JSON string result
    """
    try:
        # Parse JSON
        data = json.loads(result_content)

        # Remove knowledgeGraph if requested
        if REMOVE_KNOWLEDGE_GRAPH and "knowledgeGraph" in data:
            del data["knowledgeGraph"]

        # Remove answerBox if requested
        if REMOVE_ANSWER_BOX and "answerBox" in data:
            del data["answerBox"]

        # Remove snippets if requested
        if REMOVE_SNIPPETS:
            # Remove snippets from organic results
            if "organic" in data:
                for item in data["organic"]:
                    if "snippet" in item:
                        del item["snippet"]

            # Remove snippets from peopleAlsoAsk
            if "peopleAlsoAsk" in data:
                for item in data["peopleAlsoAsk"]:
                    if "snippet" in item:
                        del item["snippet"]

        # Return filtered JSON
        return json.dumps(data, ensure_ascii=False, indent=2)

    except (json.JSONDecodeError, Exception):
        # If filtering fails, return original content
        return result_content


@mcp.tool()
async def google_search(
    q: str,
    gl: str = "us",
    hl: str = "en",
    location: str = None,
    num: int = 10,
    tbs: str = None,
    page: int = 1,
) -> str:
    """Perform google searches via Serper API and retrieve rich results.
    It is able to retrieve organic search results, people also ask, related searches, and knowledge graph.

    Args:
        q: Search query string.
        gl: Country context for search (e.g., 'us' for United States, 'cn' for China, 'uk' for United Kingdom). Influences regional results priority. Default is 'us'.
        hl: Google interface language (e.g., 'en' for English, 'zh' for Chinese, 'es' for Spanish). Affects snippet language preference. Default is 'en'.
        location: City-level location for search results (e.g., 'SoHo, New York, United States', 'California, United States').
        num: The number of results to return (default: 10).
        tbs: Time-based search filter ('qdr:h' for past hour, 'qdr:d' for past day, 'qdr:w' for past week, 'qdr:m' for past month, 'qdr:y' for past year).
        page: The page number of results to return (default: 1).

    Returns:
        The search results.
    """
    if SERPER_API_KEY == "":
        return (
            "[ERROR]: SERPER_API_KEY is not set, google_search tool is not available."
        )

    tool_name = "google_search"
    arguments = {
        "q": q,
        "gl": gl,
        "hl": hl,
        "num": num,
        "page": page,
        "autocorrect": False,
    }
    if location:
        arguments["location"] = location
    if tbs:
        arguments["tbs"] = tbs
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "miroflow_tools.mcp_servers.serper_mcp_server"],
        env={"SERPER_API_KEY": SERPER_API_KEY, "SERPER_BASE_URL": SERPER_BASE_URL},
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
                    ), "Empty result from google_search tool, please try again."
                    # Apply filtering based on environment variables
                    filtered_result = filter_google_search_result(result_content)
                    return filtered_result  # Success, exit retry loop
        except Exception as error:
            retry_count += 1
            if retry_count >= max_retries:
                return f"[ERROR]: google_search tool execution failed after {max_retries} attempts: {str(error)}"
            # Wait before retrying
            await asyncio.sleep(min(2**retry_count, 60))

    return "[ERROR]: Unknown error occurred in google_search tool, please try again."


# @mcp.tool()
async def wiki_get_page_content(entity: str, first_sentences: int = 10) -> str:
    """Get specific Wikipedia page content for the specific entity (people, places, concepts, events) and return structured information.

    This tool searches Wikipedia for the given entity and returns either the first few sentences
    (which typically contain the summary/introduction) or full page content based on parameters.
    It handles disambiguation pages and provides clean, structured output.

    Args:
        entity: The entity to search for in Wikipedia.
        first_sentences: Number of first sentences to return from the page. Set to 0 to return full content. Defaults to 10.

    Returns:
        str: Formatted search results containing title, first sentences/full content, and URL.
             Returns error message if page not found or other issues occur.
    """
    try:
        # Try to get the Wikipedia page directly
        page = wikipedia.page(title=entity, auto_suggest=False)

        # Prepare the result
        result_parts = [f"Page Title: {page.title}"]

        if first_sentences > 0:
            # Get summary with specified number of sentences
            try:
                summary = wikipedia.summary(
                    entity, sentences=first_sentences, auto_suggest=False
                )
                result_parts.append(
                    f"First {first_sentences} sentences (introduction): {summary}"
                )
            except Exception:
                # Fallback to page summary if direct summary fails
                content_sentences = page.content.split(". ")[:first_sentences]
                summary = (
                    ". ".join(content_sentences) + "."
                    if content_sentences
                    else page.content[:5000] + "..."
                )
                result_parts.append(
                    f"First {first_sentences} sentences (introduction): {summary}"
                )
        else:
            # Return full content if first_sentences is 0
            # TODO: Context Engineering Needed
            result_parts.append(f"Content: {page.content}")

        result_parts.append(f"URL: {page.url}")

        return "\n\n".join(result_parts)

    except wikipedia.exceptions.DisambiguationError as e:
        options_list = "\n".join(
            [f"- {option}" for option in e.options[:10]]
        )  # Limit to first 10
        output = (
            f"Disambiguation Error: Multiple pages found for '{entity}'.\n\n"
            f"Available options:\n{options_list}\n\n"
            f"Please be more specific in your search query."
        )

        try:
            search_results = wikipedia.search(entity, results=5)
            if search_results:
                output += f"Try to search {entity} in Wikipedia: {search_results}"
            return output
        except Exception:
            pass

        return output

    except wikipedia.exceptions.PageError:
        # Try a search if direct page lookup fails
        try:
            search_results = wikipedia.search(entity, results=5)
            if search_results:
                suggestion_list = "\n".join(
                    [f"- {result}" for result in search_results[:5]]
                )
                return (
                    f"Page Not Found: No Wikipedia page found for '{entity}'.\n\n"
                    f"Similar pages found:\n{suggestion_list}\n\n"
                    f"Try searching for one of these suggestions instead."
                )
            else:
                return (
                    f"Page Not Found: No Wikipedia page found for '{entity}' "
                    f"and no similar pages were found. Please try a different search term."
                )
        except Exception as search_error:
            return (
                f"Page Not Found: No Wikipedia page found for '{entity}'. "
                f"Search for alternatives also failed: {str(search_error)}"
            )

    except wikipedia.exceptions.RedirectError:
        return f"Redirect Error: Failed to follow redirect for '{entity}'"

    except requests.exceptions.RequestException as e:
        return f"Network Error: Failed to connect to Wikipedia: {str(e)}"

    except wikipedia.exceptions.WikipediaException as e:
        return f"Wikipedia Error: An error occurred while searching Wikipedia: {str(e)}"

    except Exception as e:
        return f"Unexpected Error: An unexpected error occurred: {str(e)}"


# @mcp.tool()
async def search_wiki_revision(
    entity: str, year: int, month: int, max_revisions: int = 50
) -> str:
    """Search for an entity in Wikipedia and return the revision history for a specific month.

    Args:
        entity: The entity to search for in Wikipedia.
        year: The year of the revision (e.g. 2024).
        month: The month of the revision (1-12).
        max_revisions: Maximum number of revisions to return. Defaults to 50.

    Returns:
        str: Formatted revision history with timestamps, revision IDs, and URLs.
             Returns error message if page not found or other issues occur.
    """
    # Auto-adjust date values and track changes
    adjustments = []
    original_year, original_month = year, month
    current_year = datetime.datetime.now().year

    # Adjust year to valid range
    if year < 2000:
        year = 2000
        adjustments.append(
            f"Year adjusted from {original_year} to 2000 (minimum supported)"
        )
    elif year > current_year:
        year = current_year
        adjustments.append(
            f"Year adjusted from {original_year} to {current_year} (current year)"
        )

    # Adjust month to valid range
    if month < 1:
        month = 1
        adjustments.append(f"Month adjusted from {original_month} to 1")
    elif month > 12:
        month = 12
        adjustments.append(f"Month adjusted from {original_month} to 12")

    # Prepare adjustment message if any changes were made
    if adjustments:
        adjustment_msg = (
            "Date auto-adjusted: "
            + "; ".join(adjustments)
            + f". Using {year}-{month:02d} instead.\n\n"
        )
    else:
        adjustment_msg = ""

    base_url = "https://en.wikipedia.org/w/api.php"

    try:
        # Construct the time range
        start_date = datetime.datetime(year, month, 1)
        last_day = calendar.monthrange(year, month)[1]
        end_date = datetime.datetime(year, month, last_day, 23, 59, 59)

        # Convert to ISO format (UTC time)
        start_iso = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_iso = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")

        # API parameters configuration
        params = {
            "action": "query",
            "format": "json",
            "titles": entity,
            "prop": "revisions",
            "rvlimit": min(max_revisions, 500),  # Wikipedia API limit
            "rvstart": start_iso,
            "rvend": end_iso,
            "rvdir": "newer",
            "rvprop": "timestamp|ids",
        }

        response = requests.get(base_url, params=params)
        response.raise_for_status()

        data = response.json()

        # Check for API errors
        if "error" in data:
            return f"[ERROR]: Wikipedia API Error: {data['error'].get('info', 'Unknown error')}"

        # Process the response
        pages = data.get("query", {}).get("pages", {})

        if not pages:
            return f"[ERROR]: No results found for entity '{entity}'"

        # Check if page exists
        page_id = list(pages.keys())[0]
        if page_id == "-1":
            return f"[ERROR]: Page Not Found: No Wikipedia page found for '{entity}'"

        page_info = pages[page_id]
        page_title = page_info.get("title", entity)

        if "revisions" not in page_info or not page_info["revisions"]:
            return (
                adjustment_msg + f"Page Title: {page_title}\n\n"
                f"No revisions found for '{entity}' in {year}-{month:02d}.\n\n"
                f"The page may not have been edited during this time period."
            )

        # Format the results
        result_parts = [
            f"Page Title: {page_title}",
            f"Revision Period: {year}-{month:02d}",
            f"Total Revisions Found: {len(page_info['revisions'])}",
        ]

        # Add revision details
        revisions_details = []
        for i, rev in enumerate(page_info["revisions"], 1):
            revision_id = rev["revid"]
            timestamp = rev["timestamp"]

            # Format timestamp for better readability
            try:
                dt = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
            except Exception:
                formatted_time = timestamp

            # Construct revision URL
            rev_url = f"https://en.wikipedia.org/w/index.php?title={entity}&oldid={revision_id}"

            revisions_details.append(
                f"{i}. Revision ID: {revision_id}\n"
                f"   Timestamp: {formatted_time}\n"
                f"   URL: {rev_url}"
            )

        if revisions_details:
            result_parts.append("Revisions:\n" + "\n\n".join(revisions_details))

        return (
            adjustment_msg
            + "\n\n".join(result_parts)
            + "\n\nHint: You can use the `scrape_website` tool to get the webpage content of a URL."
        )

    except requests.exceptions.Timeout:
        return f"[ERROR]: Network Error: Request timed out while fetching revision history for '{entity}'"

    except requests.exceptions.RequestException as e:
        return f"[ERROR]: Network Error: Failed to connect to Wikipedia: {str(e)}"

    except ValueError as e:
        return f"[ERROR]: Date Error: Invalid date values - {str(e)}"

    except Exception as e:
        return f"[ERROR]: Unexpected Error: An unexpected error occurred: {str(e)}"


# @mcp.tool()
async def search_archived_webpage(url: str, year: int, month: int, day: int) -> str:
    """Search the Wayback Machine (archive.org) for archived versions of a webpage, optionally for a specific date.

    Args:
        url: The URL to search for in the Wayback Machine.
        year: The target year (e.g., 2023).
        month: The target month (1-12).
        day: The target day (1-31).

    Returns:
        str: Formatted archive information including archived URL, timestamp, and status.
             Returns error message if URL not found or other issues occur.
    """
    # Handle empty URL
    if not url:
        return f"[ERROR]: Invalid URL: '{url}'. URL cannot be empty."

    # Auto-add https:// if no protocol is specified
    protocol_hint = ""
    if not url.startswith(("http://", "https://")):
        original_url = url
        url = f"https://{url}"
        protocol_hint = f"[NOTE]: Automatically added 'https://' to URL '{original_url}' -> '{url}'\n\n"

    hint_message = ""
    if ".wikipedia.org" in url:
        hint_message = "Note: You are trying to search a Wikipedia page, you can also use the `search_wiki_revision` tool to get the revision content of a Wikipedia page.\n\n"

    # Check if specific date is requested
    date = ""
    adjustment_msg = ""
    if year > 0 and month > 0:
        # Auto-adjust date values and track changes
        adjustments = []
        original_year, original_month, original_day = year, month, day
        current_year = datetime.datetime.now().year

        # Adjust year to valid range
        if year < 1995:
            year = 1995
            adjustments.append(
                f"Year adjusted from {original_year} to 1995 (minimum supported)"
            )
        elif year > current_year:
            year = current_year
            adjustments.append(
                f"Year adjusted from {original_year} to {current_year} (current year)"
            )

        # Adjust month to valid range
        if month < 1:
            month = 1
            adjustments.append(f"Month adjusted from {original_month} to 1")
        elif month > 12:
            month = 12
            adjustments.append(f"Month adjusted from {original_month} to 12")

        # Adjust day to valid range for the given month/year
        max_day = calendar.monthrange(year, month)[1]
        if day < 1:
            day = 1
            adjustments.append(f"Day adjusted from {original_day} to 1")
        elif day > max_day:
            day = max_day
            adjustments.append(
                f"Day adjusted from {original_day} to {max_day} (max for {year}-{month:02d})"
            )

        # Update the date string with adjusted values
        date = f"{year:04d}{month:02d}{day:02d}"

        try:
            # Validate the final adjusted date
            datetime.datetime(year, month, day)
        except ValueError as e:
            return f"[ERROR]: Invalid date: {year}-{month:02d}-{day:02d}. {str(e)}"

        # Prepare adjustment message if any changes were made
        if adjustments:
            adjustment_msg = (
                "Date auto-adjusted: "
                + "; ".join(adjustments)
                + f". Using {date} instead.\n\n"
            )

    try:
        base_url = "https://archive.org/wayback/available"
        # Search with specific date if provided
        if date:
            retry_count = 0
            # retry 5 times if the response is not valid
            while retry_count < 5:
                response = requests.get(f"{base_url}?url={url}&timestamp={date}")
                response.raise_for_status()
                data = response.json()
                if (
                    "archived_snapshots" in data
                    and "closest" in data["archived_snapshots"]
                ):
                    break
                retry_count += 1
                await asyncio.sleep(min(2**retry_count, 60))

            if "archived_snapshots" in data and "closest" in data["archived_snapshots"]:
                closest = data["archived_snapshots"]["closest"]
                archived_url = closest["url"]
                archived_timestamp = closest["timestamp"]
                available = closest.get("available", True)

                if not available:
                    return (
                        hint_message
                        + adjustment_msg
                        + (
                            f"Archive Status: Snapshot exists but is not available\n\n"
                            f"Original URL: {url}\n"
                            f"Requested Date: {year:04d}-{month:02d}-{day:02d}\n"
                            f"Closest Snapshot: {archived_timestamp}\n\n"
                            f"Try a different date"
                        )
                    )

                # Format timestamp for better readability
                try:
                    dt = datetime.datetime.strptime(archived_timestamp, "%Y%m%d%H%M%S")
                    formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
                except Exception:
                    formatted_time = archived_timestamp

                return (
                    protocol_hint
                    + hint_message
                    + adjustment_msg
                    + (
                        f"Archive Found: Archived version located\n\n"
                        f"Original URL: {url}\n"
                        f"Requested Date: {year:04d}-{month:02d}-{day:02d}\n"
                        f"Archived URL: {archived_url}\n"
                        f"Archived Timestamp: {formatted_time}\n"
                    )
                    + "\n\nHint: You can also use the `scrape_website` tool to get the webpage content of a URL."
                )

        # Search without specific date (most recent)
        retry_count = 0
        # retry 5 times if the response is not valid
        while retry_count < 5:
            response = requests.get(f"{base_url}?url={url}")
            response.raise_for_status()
            data = response.json()
            if "archived_snapshots" in data and "closest" in data["archived_snapshots"]:
                break
            retry_count += 1
            await asyncio.sleep(min(2**retry_count, 60))

        if "archived_snapshots" in data and "closest" in data["archived_snapshots"]:
            closest = data["archived_snapshots"]["closest"]
            archived_url = closest["url"]
            archived_timestamp = closest["timestamp"]
            available = closest.get("available", True)

            if not available:
                return (
                    protocol_hint
                    + hint_message
                    + (
                        f"Archive Status: Most recent snapshot exists but is not available\n\n"
                        f"Original URL: {url}\n"
                        f"Most Recent Snapshot: {archived_timestamp}\n\n"
                        f"The URL may have been archived but access is restricted"
                    )
                )

            # Format timestamp for better readability
            try:
                dt = datetime.datetime.strptime(archived_timestamp, "%Y%m%d%H%M%S")
                formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
            except Exception:
                formatted_time = archived_timestamp

            return (
                protocol_hint
                + hint_message
                + (
                    f"Archive Found: Most recent archived version\n\n"
                    f"Original URL: {url}\n"
                    f"Archived URL: {archived_url}\n"
                    f"Archived Timestamp: {formatted_time}\n"
                )
                + "\n\nHint: You can also use the `scrape_website` tool to get the webpage content of a URL."
            )
        else:
            return (
                protocol_hint
                + hint_message
                + (
                    f"Archive Not Found: No archived versions available\n\n"
                    f"Original URL: {url}\n\n"
                    f"The URL '{url}' has not been archived by the Wayback Machine.\n"
                    f"You may want to:\n"
                    f"- Check if the URL is correct\n"
                    f"- Try a different URL and date\n"
                )
            )

    except requests.exceptions.RequestException as e:
        return f"[ERROR]: Network Error: Failed to connect to Wayback Machine: {str(e)}"

    except ValueError as e:
        return f"[ERROR]: Data Error: Failed to parse response from Wayback Machine: {str(e)}"

    except Exception as e:
        return f"[ERROR]: Unexpected Error: An unexpected error occurred: {str(e)}"


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
