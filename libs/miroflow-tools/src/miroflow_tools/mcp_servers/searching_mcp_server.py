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
import requests
import datetime
import calendar
import time
from fastmcp import FastMCP
from mcp.client.stdio import stdio_client
from mcp import ClientSession, StdioServerParameters  # (already imported in config.py)
import wikipedia
import asyncio
from google import genai
from google.genai import types
# from miroflow_agent.logging.task_logger import logger

SERPER_API_KEY = os.environ.get("SERPER_API_KEY", "")
JINA_API_KEY = os.environ.get("JINA_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# Initialize FastMCP server
mcp = FastMCP("searching-mcp-server")


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
    """Performs Google searches via Serper API to retrieve comprehensive web information including organic search results, knowledge graphs, 'People Also Ask' sections, and related searches. Use this tool when you need up-to-date information that may not be in your training data, for fact-checking, researching current events, finding location-specific information, or discovering related topics.

    Capabilities:
    - Retrieves structured search results with titles, links, and snippets
    - Supports filtering by region, language, location, and time period
    - Can paginate through multiple result pages for thorough research

    Limitations:
    - Cannot access content behind paywalls or login screens
    - Cannot guarantee the accuracy or verify information automatically
    - May not have access to very recent information not yet indexed\n- Returns search metadata, not full website content

    Usage examples:
    1. Basic search: `{\"q\": \"latest climate change research\"}` returns current climate science findings
    2. Location-specific: `{\"q\": \"best restaurants\", \"location\": \"SoHo, New York\", \"num\": 5}` finds top dining spots in SoHo
    3. Time-filtered: `{\"q\": \"technology news\", \"tbs\": \"qdr:w\"}` returns tech news from the past week
    4. International: `{\"q\": \"olympic games\", \"gl\": \"jp\", \"hl\": \"ja\"}` searches for Olympic content in Japanese

    Args:
        q: The search query string. Be specific to get more relevant results. Use quotes for exact phrases. (e.g. "renewable energy" developments 2023)
        gl: The region code for search results in ISO 3166-1 alpha-2 format (default: 'us').
        hl: The language code for search results in ISO 639-1 format (default: 'en').
        location: Geographic location for search results (e.g., 'SoHo, New York, United States', 'California, United States').
        num: The number of search results to return (1-100). Higher values provide more comprehensive results but may use more credits. (default: 10).
        tbs: Time-based search filter (Use 'qdr:h' for past hour, 'qdr:d' for past day, 'qdr:w' for past week, 'qdr:m' for past month, 'qdr:y' for past year).
        page: The page number of results to return. Use for navigating through multiple pages of results. (default: 1).

    Returns:
        The search results.
    """
    if SERPER_API_KEY == "":
        return "SERPER_API_KEY is not set, google_search tool is not available."
    tool_name = "google_search"
    arguments = {"q": q, "gl": gl, "hl": hl, "num": num, "page": page}
    if location:
        arguments["location"] = location
    if tbs:
        arguments["tbs"] = tbs
    arguments["autocorrect"] = False
    server_params = StdioServerParameters(
        command="npx",
        args=["-y", "serper-search-scrape-mcp-server"],
        env={"SERPER_API_KEY": SERPER_API_KEY},
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
                    try:
                        tool_result = await session.call_tool(
                            tool_name, arguments=arguments
                        )
                        result_content = (
                            tool_result.content[-1].text if tool_result.content else ""
                        )
                        break  # Success, exit retry loop
                    except Exception as tool_error:
                        error_msg = str(tool_error).lower()
                        # Check for non-recoverable errors
                        if any(
                            err in error_msg
                            for err in [
                                "epipe",
                                "broken pipe",
                                "connection reset",
                                "connection refused",
                            ]
                        ):
                            # logger.warning(
                            #     f"Non-recoverable error in tool execution: {tool_error}"
                            # )
                            return f"Tool execution failed: {str(tool_error)}"

                        retry_count += 1
                        # logger.warning(
                        #     f"Tool execution attempt {retry_count} failed: {tool_error}"
                        # )
                        if retry_count >= max_retries:
                            return f"Tool execution failed after {max_retries} attempts: {str(tool_error)}"
                        break  # Exit current session, will retry with new session

        except Exception as outer_error:
            error_msg = str(outer_error).lower()
            # Check for non-recoverable errors
            if any(
                err in error_msg
                for err in [
                    "epipe",
                    "broken pipe",
                    "connection reset",
                    "connection refused",
                ]
            ):
                # logger.warning(f"Non-recoverable connection error: {outer_error}")
                return f"Tool execution failed: Connection error - {str(outer_error)}"

            retry_count += 1
            # logger.warning(f"Connection attempt {retry_count} failed: {outer_error}")
            if retry_count >= max_retries:
                return f"Tool execution failed after {max_retries} connection attempts: Unexpected error occurred."

            # Wait before retrying
            await asyncio.sleep(
                min(3 * retry_count, 10)
            )  # Exponential backoff with cap

    return result_content


@mcp.tool()
async def wiki_search(entity: str, summary_sentences: int = 10) -> str:
    """Search Wikipedia for information about specific entities (people, places, concepts, events) and return structured results.

    This tool queries Wikipedia's English version to retrieve factual, encyclopedic knowledge about a specified entity. It can provide either a concise summary or full article content based on your parameters.

    Capabilities:
    - Retrieves factual information from Wikipedia pages
    - Handles disambiguation pages by reporting multiple matches
    - Returns structured results with title, content, and URL

    Limitations:
    - Information may not be up-to-date (limited by Wikipedia's update cycle)
    - Cannot verify information accuracy beyond what's on Wikipedia
    - Only searches English Wikipedia
    - Cannot search within page content for specific information

    Usage Examples:
    1. Basic entity search: `wiki_search(entity="Albert Einstein")` returns a 10-sentence summary about Einstein
    2. Full article retrieval: `wiki_search(entity="Python programming language", summary_sentences=0)` returns the full Wikipedia article
    3. Custom summary length: `wiki_search(entity="Tokyo", summary_sentences=5)` returns a 5-sentence summary about Tokyo
    4. Handling ambiguity: `wiki_search(entity="Mercury")` would inform you that Mercury could refer to the planet, element, deity, etc.

    Args:
        entity: The specific entity, topic, person, place, or concept to search for in Wikipedia. Use precise terms for best results. (e.g. "Marie Curie")
        summary_sentences: Number of sentences to return in summary. Set to 0 to return full content. Defaults to 10.

    Returns:
        str: Formatted search results containing title, summary/content, and optionally URL.
             Returns error message if page not found or other issues occur.
    """
    try:
        # Try to get the Wikipedia page directly
        page = wikipedia.page(title=entity, auto_suggest=False)

        # Prepare the result
        result_parts = [f"Page Title: {page.title}"]

        if summary_sentences > 0:
            # Get summary with specified number of sentences
            try:
                summary = wikipedia.summary(
                    entity, sentences=summary_sentences, auto_suggest=False
                )
                result_parts.append(f"Summary: {summary}")
            except Exception:
                # Fallback to page summary if direct summary fails
                content_sentences = page.content.split(".")[:summary_sentences]
                summary = (
                    ".".join(content_sentences) + "."
                    if content_sentences
                    else page.content[:500] + "..."
                )
                result_parts.append(f"Summary: {summary}")
        else:
            # Return full content if summary_sentences is 0
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


@mcp.tool()
async def wiki_search_revision(
    entity: str, year: int, month: int, max_revisions: int = 50
) -> str:
    """Search for a Wikipedia article and retrieve its revision history for a specific month and year. This tool is useful for: (1) Obtaining the web URL of a historical version of a Wikipedia article, (2) Researching how a Wikipedia article has evolved during a specific month, (3) Investigating who made changes to an article in a particular timeframe, (4) Analyzing edit frequency patterns, (5) Identifying significant revisions for academic or research purposes.

    The returned data includes timestamps, revision IDs, and direct URLs to each revision. Note that this tool only returns revision metadata, not the actual content changes.

    Limitations: Cannot retrieve content differences between revisions, search across multiple months, filter by editor, or search within revision content.

    Examples:
    - `wiki_search_revision(entity="Albert Einstein", year=2023, month=6)` returns revision history for the Albert Einstein article in June 2023
    - `wiki_search_revision(entity="COVID-19 pandemic", year=2020, month=3, max_revisions=100)` returns up to 100 revisions for the COVID-19 pandemic article from March 2020
    - `wiki_search_revision(entity="C++ (programming language)", year=2022, month=1)` handles special characters in entity names correctly

    Args:
        entity: The Wikipedia article title to search for. Can include spaces and special characters (e.g., 'World War II', 'C++ (programming language)').
        year: The year of the revisions to retrieve. Must be between 2001 (Wikipedia's founding) and the current year.
        month: The month of the revision (1-12).
        max_revisions: Maximum number of revisions to return. Defaults to 50.

    Returns:
        str: Formatted revision history with timestamps, revision IDs, and URLs.
             Returns error message if page not found or other issues occur.
    """
    # Validate month input
    if not (1 <= month <= 12):
        return f"Invalid month: {month}. Month must be between 1 and 12."

    # Validate year input
    current_year = datetime.datetime.now().year
    if year < 2001 or year > current_year:
        return f"Invalid year: {year}. Year must be between 2001 and {current_year}."

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
            return f"Wikipedia API Error: {data['error'].get('info', 'Unknown error')}"

        # Process the response
        pages = data.get("query", {}).get("pages", {})

        if not pages:
            return f"No results found for entity '{entity}'"

        # Check if page exists
        page_id = list(pages.keys())[0]
        if page_id == "-1":
            return f"Page Not Found: No Wikipedia page found for '{entity}'"

        page_info = pages[page_id]
        page_title = page_info.get("title", entity)

        if "revisions" not in page_info or not page_info["revisions"]:
            return (
                f"Page Title: {page_title}\n\n"
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

        return "\n\n".join(result_parts)

    except requests.exceptions.Timeout:
        return f"Network Error: Request timed out while fetching revision history for '{entity}'"

    except requests.exceptions.RequestException as e:
        return f"Network Error: Failed to connect to Wikipedia API: {str(e)}"

    except ValueError as e:
        return f"Date Error: Invalid date values - {str(e)}"

    except Exception as e:
        return f"Unexpected Error: An unexpected error occurred: {str(e)}"


@mcp.tool()
async def search_archived_webpage(url: str, date: str = "") -> str:
    """Searches the Internet Archive's Wayback Machine for archived snapshots of web pages that are no longer available or to view how websites appeared at specific points in time.

    This tool helps retrieve historical versions of web pages by accessing the Internet Archive's repository. It's useful for research, verification of past information, or accessing content that has been removed or modified.

    Capabilities:
    - Retrieves information about archived versions of public web pages
    - Can search for archives from a specific date or find the most recent snapshot
    - Returns formatted metadata including archive timestamp and accessible URL

    Limitations:
    - Only returns pages previously archived by the Wayback Machine
    - Cannot archive new pages or content behind logins/paywalls
    - Some page elements (dynamic content, images, scripts) may be missing in archives
    - No guarantee of archive availability for all URLs or dates

    Examples:
    1. Find the most recent archive of a news website:
       Input: {"url": "https://cnn.com"}
       Output: "Archive found: https://web.archive.org/web/20240520135621/https://cnn.com/ (May 20, 2024)"
    2. Find how a website looked on a specific date:
       Input: {"url": "https://twitter.com", "date": "20100315"}
       Output: "Archive found: https://web.archive.org/web/20100315023632/http://twitter.com/ (March 15, 2010)"
    3. When no archive exists:
       Input: {"url": "https://example-site-that-never-existed.com"}
       Output: "Error: No archives found for this URL. The page may never have been archived."

    Args:
        url: The complete URL of the webpage you want to find in the Wayback Machine archives. Must include protocol (http:// or https://).
        date: The target date to search for archives in YYYYMMDD format (e.g., '20240315' for March 15, 2024). If omitted, returns the most recent archived version. Must be between 1996 (earliest Wayback Machine archives) and the current year.

    Returns:
        str: Formatted archive information including archived URL, timestamp, and status.
             Returns error message if URL not found or other issues occur.
    """
    # Validate URL format
    if not url or not url.startswith(("http://", "https://")):
        return f"Invalid URL: '{url}'. URL must start with http:// or https://"

    # Validate date format if provided
    if date:
        if len(date) != 8 or not date.isdigit():
            return f"Invalid date format: '{date}'. Date must be in YYYYMMDD format (e.g., '20240315')"

        try:
            year = int(date[:4])
            month = int(date[4:6])
            day = int(date[6:8])

            # Basic date validation
            if not (1996 <= year <= datetime.datetime.now().year):
                return f"Invalid year: {year}. Year must be between 1996 and {datetime.datetime.now().year}"
            if not (1 <= month <= 12):
                return f"Invalid month: {month}. Month must be between 1 and 12"
            if not (1 <= day <= 31):
                return f"Invalid day: {day}. Day must be between 1 and 31"

            # Validate actual date
            datetime.datetime(year, month, day)
        except ValueError as e:
            return f"Invalid date: '{date}'. {str(e)}"

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
                time.sleep(5)

            if "archived_snapshots" in data and "closest" in data["archived_snapshots"]:
                closest = data["archived_snapshots"]["closest"]
                archived_url = closest["url"]
                archived_timestamp = closest["timestamp"]
                available = closest.get("available", True)

                if not available:
                    return (
                        f"Archive Status: Snapshot exists but is not available\n\n"
                        f"Original URL: {url}\n"
                        f"Requested Date: {date}\n"
                        f"Closest Snapshot: {archived_timestamp}\n\n"
                        f"Try a different date"
                    )

                # Format timestamp for better readability
                try:
                    dt = datetime.datetime.strptime(archived_timestamp, "%Y%m%d%H%M%S")
                    formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
                except Exception:
                    formatted_time = archived_timestamp

                return (
                    f"Archive Found: Archived version located\n\n"
                    f"Original URL: {url}\n"
                    f"Requested Date: {date}\n"
                    f"Archived URL: {archived_url}\n"
                    f"Archived Timestamp: {formatted_time}\n"
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
            time.sleep(5)

        if "archived_snapshots" in data and "closest" in data["archived_snapshots"]:
            closest = data["archived_snapshots"]["closest"]
            archived_url = closest["url"]
            archived_timestamp = closest["timestamp"]
            available = closest.get("available", True)

            if not available:
                return (
                    f"Archive Status: Most recent snapshot exists but is not available\n\n"
                    f"Original URL: {url}\n"
                    f"Most Recent Snapshot: {archived_timestamp}\n\n"
                    f"The URL may have been archived but access is restricted"
                )

            # Format timestamp for better readability
            try:
                dt = datetime.datetime.strptime(archived_timestamp, "%Y%m%d%H%M%S")
                formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
            except Exception:
                formatted_time = archived_timestamp

            return (
                f"Archive Found: Most recent archived version\n\n"
                f"Original URL: {url}\n"
                f"Archived URL: {archived_url}\n"
                f"Archived Timestamp: {formatted_time}\n"
            )
        else:
            return (
                f"Archive Not Found: No archived versions available\n\n"
                f"Original URL: {url}\n\n"
                f"The URL '{url}' has not been archived by the Wayback Machine.\n"
                f"You may want to:\n"
                f"- Check if the URL is correct\n"
                f"- Try a different URL and date\n"
            )

    except requests.exceptions.RequestException as e:
        return f"Network Error: Failed to connect to Wayback Machine: {str(e)}"

    except ValueError as e:
        return f"Data Error: Failed to parse response from Wayback Machine: {str(e)}"

    except Exception as e:
        return f"Unexpected Error: An unexpected error occurred: {str(e)}"


# @mcp.tool()
# async def scrape_website(url: str) -> str:
#     """This tool is used to scrape a website for information. Search engines are not supported by this tool.
#     Args:
#         url: The URL of the website to scrape.

#     Returns:
#         The scraped website content.
#     """
#     if SERPER_API_KEY == "":
#         return "SERPER_API_KEY is not set, scrape_website tool is not available."
#     server_params = StdioServerParameters(
#         command="npx",
#         args=["-y", "serper-search-scrape-mcp-server"],
#         env={"SERPER_API_KEY": SERPER_API_KEY},
#     )
#     tool_name = "scrape"
#     arguments = {"url": url}
#     result_content = ""
#     retry_count = 0
#     max_retries = 3

#     while retry_count < max_retries:
#         try:
#             async with stdio_client(server_params) as (read, write):
#                 async with ClientSession(
#                     read, write, sampling_callback=None
#                 ) as session:
#                     await session.initialize()
#                     try:
#                         tool_result = await session.call_tool(
#                             tool_name, arguments=arguments
#                         )
#                         result_content = (
#                             tool_result.content[-1].text if tool_result.content else ""
#                         )
#                         if (
#                             "huggingface.co/datasets" in url
#                             or "huggingface.co/spaces" in url
#                         ):
#                             result_content = "You are trying to scrape a Hugging Face dataset for answers, please do not use the scrape tool for this purpose."
#                         break  # Success, exit retry loop
#                     except Exception as tool_error:
#                         error_msg = str(tool_error).lower()
#                         # Check for non-recoverable errors (404, not found, EPIPE, etc.)
#                         if any(
#                             err in error_msg
#                             for err in [
#                                 "404",
#                                 "not found",
#                                 "epipe",
#                                 "broken pipe",
#                                 "connection reset",
#                                 "connection refused",
#                             ]
#                         ):
#                             # logger.warning(
#                             #     f"Non-recoverable error in scrape execution: {tool_error}"
#                             # )
#                             return f"Tool execution failed: {str(tool_error)}"

#                         retry_count += 1
#                         # logger.warning(
#                         #     f"Scrape execution attempt {retry_count} failed: {tool_error}"
#                         # )
#                         if retry_count >= max_retries:
#                             return f"Tool execution failed after {max_retries} attempts: {str(tool_error)}"
#                         break  # Exit current session, will retry with new session

#         except Exception as outer_error:
#             error_msg = str(outer_error).lower()
#             # Check for non-recoverable errors
#             if any(
#                 err in error_msg
#                 for err in [
#                     "epipe",
#                     "broken pipe",
#                     "connection reset",
#                     "connection refused",
#                 ]
#             ):
#                 # logger.warning(
#                 #     f"Non-recoverable connection error in scrape: {outer_error}"
#                 # )
#                 return f"Tool execution failed: Connection error - {str(outer_error)}"

#             retry_count += 1
#             # logger.warning(
#             #     f"Scrape connection attempt {retry_count} failed: {outer_error}"
#             # )
#             if retry_count >= max_retries:
#                 return f"Tool execution failed after {max_retries} connection attempts: Unexpected error occurred."

#             # Wait before retrying
#             await asyncio.sleep(
#                 min(3 * retry_count, 10)
#             )  # Exponential backoff with cap

#     return result_content


async def scrape_youtube(url: str) -> str:
    """This function is used to scrape a YouTube video using SERPER for information.
    Args:
        url: The URL of the YouTube video to scrape.
    """
    if SERPER_API_KEY == "":
        return "SERPER_API_KEY is not set, scrape_website tool is not available."
    server_params = StdioServerParameters(
        command="npx",
        args=["-y", "serper-search-scrape-mcp-server"],
        env={"SERPER_API_KEY": SERPER_API_KEY},
    )
    tool_name = "scrape"
    arguments = {"url": url}
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
                    try:
                        tool_result = await session.call_tool(
                            tool_name, arguments=arguments
                        )
                        result_content = (
                            tool_result.content[-1].text if tool_result.content else ""
                        )
                        break  # Success, exit retry loop
                    except Exception as tool_error:
                        error_msg = str(tool_error).lower()
                        # Check for non-recoverable errors (404, not found, EPIPE, etc.)
                        if any(
                            err in error_msg
                            for err in [
                                "404",
                                "not found",
                                "epipe",
                                "broken pipe",
                                "connection reset",
                                "connection refused",
                            ]
                        ):
                            return f"Tool execution failed: {str(tool_error)}"

                        retry_count += 1
                        if retry_count >= max_retries:
                            return f"Tool execution failed after {max_retries} attempts: {str(tool_error)}"
                        break  # Exit current session, will retry with new session

        except Exception as outer_error:
            error_msg = str(outer_error).lower()
            # Check for non-recoverable errors
            if any(
                err in error_msg
                for err in [
                    "epipe",
                    "broken pipe",
                    "connection reset",
                    "connection refused",
                ]
            ):
                return f"Tool execution failed: Connection error - {str(outer_error)}"

            retry_count += 1
            if retry_count >= max_retries:
                return f"Tool execution failed after {max_retries} connection attempts: Unexpected error occurred."

            # Wait before retrying
            await asyncio.sleep(
                min(3 * retry_count, 10)
            )  # Exponential backoff with cap

    result_content += (
        "\n\n"
        + "Hint: If you need to get more information about the video content, please use tool 'ask_youtube_video' instead."
    )
    return result_content


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

    # Use SERPER scrape for youtube websites
    if url.startswith("https://www.youtube.com/"):
        return await scrape_youtube(url)

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


# The tool ask_youtube_video only support single YouTube URL as input for now, though GEMINI can support multiple URLs up to 10 per request.
@mcp.tool()
async def ask_youtube_video(
    url: str, question: str = "", provide_transcribe: bool = False
) -> str:
    """Analyzes YouTube video content to answer specific questions about visual elements or spoken content at particular timestamps, or provides full video transcription. This tool uses a multimodal model to understand both audio and visual components.

    Capabilities:
    - Extract information from specific timestamps (e.g., visual elements, spoken dialogue)
    - Analyze visual elements appearing at certain timestamps
    - Transcribe spoken content with timestamps
    - Provide comprehensive video understanding combining audio and visual elements

    Limitations:
    - Only works with public YouTube videos (no private/restricted videos or other platforms)
    - Analysis quality depends on video clarity, audio quality, and question specificity
    - Cannot modify, edit, or download video content
    - Performance may vary with very long videos or complex scenes

    Usage Examples:
    1. Question about visual content:
       Question: "What is displayed on the screen at 01:30?"
       Result: "At 01:30, a diagram showing the water cycle is displayed with labels for evaporation, condensation, and precipitation."

    2. Question about dialogue:
       Question: "What does the speaker say about climate change at 05:20-05:40?"
       Result: "Between 05:20-05:40, the speaker explains that climate change is increasing the frequency of extreme weather events and mentions that global temperatures have risen by 1.1°C since pre-industrial times."

    3. Full transcription request:
       Set provide_transcription to True (leaving question blank or asking for something else)
       Result: A complete timestamped transcription of spoken content and visual descriptions throughout the video.

    Args:
        url: The YouTube video URL. Must be a public video that doesn't require login credentials.
        question: The specific question about the video content. Use timestamp format MM:SS or MM:SS-MM:SS to specify when the content appears (e.g., "What happens at 01:45?" or "What is said between 03:20-03:45?"). Leave empty if only requesting transcription.
        provide_transcribe: When set to true, returns a complete timestamped transcription of both spoken content and visual elements throughout the video. Useful for longer videos or when comprehensive understanding is needed.

    Returns:
        The answer to the question or the transcription of the video.
    """
    if GEMINI_API_KEY == "":
        return "GEMINI_API_KEY is not set, ask_youtube_video tool is not available."

    if not url.startswith("https://www.youtube.com/"):
        return "Invalid URL: '{url}'. The YouTube URL must start with https://www.youtube.com/"

    if question == "" and not provide_transcribe:
        return "You must provide a question to ask about the video content or set provide_transcribe to True."

    client = genai.Client(api_key=GEMINI_API_KEY)
    if provide_transcribe:
        # prompt from GEMINI official document
        prompt = "Transcribe the audio from this video, giving timestamps for salient events in the video. Also provide visual descriptions."
        try:
            transcribe_response = client.models.generate_content(
                model="gemini-2.5-pro",
                contents=types.Content(
                    parts=[
                        types.Part(text=prompt),
                        types.Part(file_data=types.FileData(file_uri=url)),
                    ]
                ),
            )
            transcribe_content = (
                "Transcription:\n\n" + transcribe_response.text + "\n\n"
            )
        except Exception as e:
            transcribe_content = f"Error: Failed to transcribe the video: {str(e)}"
    else:
        transcribe_content = ""

    if question != "":
        prompt = f"Answer the following question: {question}"
        try:
            response = client.models.generate_content(
                model="gemini-2.5-pro",
                contents=types.Content(
                    parts=[
                        types.Part(text=prompt),
                        types.Part(file_data=types.FileData(file_uri=url)),
                    ]
                ),
            )
            answer_content = (
                "Answer of the question: " + question + "\n\n" + response.text + "\n\n"
            )
        except Exception as e:
            answer_content = f"Error: Failed to answer the question: {str(e)}"
    else:
        answer_content = ""

    hint = "Hint: If you need more website information rather than video content itself, you should also call tool 'scrape_website'."
    return transcribe_content + answer_content + hint


if __name__ == "__main__":
    mcp.run(transport="stdio")
