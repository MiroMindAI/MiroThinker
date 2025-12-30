# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

import asyncio
import json
import logging
import os
from typing import Any, Dict

import httpx
from mcp.server.fastmcp import FastMCP

# Configure logging
logger = logging.getLogger("miroflow")

SUMMARY_LLM_BASE_URL = os.environ.get("SUMMARY_LLM_BASE_URL")
SUMMARY_LLM_MODEL_NAME = os.environ.get("SUMMARY_LLM_MODEL_NAME")
SUMMARY_LLM_API_KEY = os.environ.get("SUMMARY_LLM_API_KEY")

JINA_API_KEY = os.environ.get("JINA_API_KEY", "")
JINA_BASE_URL = os.environ.get("JINA_BASE_URL", "https://r.jina.ai")

# Initialize FastMCP server
mcp = FastMCP("jina_scrape_llm_summary")


@mcp.tool()
async def scrape_and_extract_info(
    url: str, info_to_extract: str, custom_headers: Dict[str, str] = None
):
    """
    Scrape content from a URL, including web pages, PDFs, code files, and other supported resources, and extract meaningful information using an LLM.
    If you need to extract information from a PDF, please use this tool.

    Args:
        url (str): The URL to scrape content from. Supports various types of URLs such as web pages, PDFs, raw text/code files (e.g., GitHub, Gist), and similar sources.
        info_to_extract (str): The specific types of information to extract (usually a question)
        custom_headers (Dict[str, str]): Additional headers to include in the scraping request

    Returns:
        Dict[str, Any]: A dictionary containing:
            - success (bool): Whether the operation was successful
            - url (str): The original URL
            - extracted_info (str): The extracted information
            - error (str): Error message if the operation failed
    """
    if _is_huggingface_dataset_or_space_url(url):
        return json.dumps(
            {
                "success": False,
                "url": url,
                "extracted_info": "",
                "error": "You are trying to scrape a Hugging Face dataset for answers, please do not use the scrape tool for this purpose.",
            },
            ensure_ascii=False,
        )

    # First, scrape the content with Jina
    scrape_result = await scrape_url_with_jina(url, custom_headers)

    # If Jina fails, try direct Python scraping as fallback
    if not scrape_result["success"]:
        logger.warning(
            f"Jina Scrape and Extract Info: Jina scraping failed: {scrape_result['error']}, trying direct Python scraping as fallback"
        )
        scrape_result = await scrape_url_with_python(url, custom_headers)

        if not scrape_result["success"]:
            logger.error(
                f"Jina Scrape and Extract Info: Both Jina and Python scraping failed: {scrape_result['error']}"
            )
            return json.dumps(
                {
                    "success": False,
                    "url": url,
                    "extracted_info": "",
                    "error": f"Scraping failed (both Jina and Python): {scrape_result['error']}",
                },
                ensure_ascii=False,
            )
        else:
            logger.info(
                f"Jina Scrape and Extract Info: Python fallback scraping succeeded for URL: {url}"
            )

    # Then, summarize the content
    extracted_result = await extract_info_with_llm(
        url=url,
        content=scrape_result["content"],
        info_to_extract=info_to_extract,
        model=SUMMARY_LLM_MODEL_NAME,
        max_tokens=8192,
    )

    # Combine results
    return json.dumps(
        {
            "success": extracted_result["success"],
            "url": url,
            "extracted_info": extracted_result["extracted_info"],
            "error": extracted_result["error"],
        },
        ensure_ascii=False,
    )


def _is_huggingface_dataset_or_space_url(url):
    """
    Check if the URL is a HuggingFace dataset or space URL.
    :param url: The URL to check
    :return: True if it's a HuggingFace dataset or space URL, False otherwise
    """
    if not url:
        return False
    return "huggingface.co/datasets" in url or "huggingface.co/spaces" in url


async def scrape_url_with_jina(
    url: str, custom_headers: Dict[str, str] = None, max_chars: int = 102400 * 4
) -> Dict[str, Any]:
    """
    Scrape content from a URL and save to a temporary file. Need to read the content from the temporary file.


    Args:
        url (str): The URL to scrape content from
        custom_headers (Dict[str, str]): Additional headers to include in the request
        max_chars (int): Maximum number of characters to reserve for the scraped content

    Returns:
        Dict[str, Any]: A dictionary containing:
            - success (bool): Whether the operation was successful
            - filename (str): Absolute path to the temporary file containing the scraped content
            - content (str): The scraped content (truncated to max_chars if necessary)
            - error (str): Error message if the operation failed
    """

    # Validate input
    if not url or not url.strip():
        return {
            "success": False,
            "filename": "",
            "content": "",
            "error": "URL cannot be empty",
        }

    # Get API key from environment
    if not JINA_API_KEY:
        return {
            "success": False,
            "filename": "",
            "content": "",
            "error": "JINA_API_KEY environment variable is not set",
        }

    # Avoid duplicate Jina URL prefix
    if url.startswith("https://r.jina.ai/") and url.count("http") >= 2:
        url = url[len("https://r.jina.ai/") :]

    # Construct the Jina.ai API URL
    jina_url = f"{JINA_BASE_URL}/{url}"

    try:
        # Prepare headers
        headers = {
            "Authorization": f"Bearer {JINA_API_KEY}",
        }

        # Add custom headers if provided
        if custom_headers:
            headers.update(custom_headers)

        # Retry configuration
        retry_delays = [1, 2, 4, 8]

        for attempt, delay in enumerate(retry_delays, 1):
            try:
                # Make the request using httpx library
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        jina_url,
                        headers=headers,
                        timeout=httpx.Timeout(None, connect=20, read=60),
                        follow_redirects=True,  # Follow redirects (equivalent to curl -L)
                    )

                # Check if request was successful
                response.raise_for_status()
                break  # Success, exit retry loop

            except httpx.ConnectTimeout as e:
                # connection timeout, retry
                if attempt < len(retry_delays):
                    logger.info(
                        f"Jina Scrape: Connection timeout, {delay}s before next attempt (attempt {attempt + 1})"
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(
                        f"Jina Scrape: Connection retry attempts exhausted, url: {url}"
                    )
                    raise e

            except httpx.ConnectError as e:
                # connection error, retry
                if attempt < len(retry_delays):
                    logger.info(
                        f"Jina Scrape: Connection error: {e}, {delay}s before next attempt"
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(
                        f"Jina Scrape: Connection retry attempts exhausted, url: {url}"
                    )
                    raise e

            except httpx.ReadTimeout as e:
                # read timeout, retry
                if attempt < len(retry_delays):
                    logger.info(
                        f"Jina Scrape: Read timeout, {delay}s before next attempt (attempt {attempt + 1})"
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(
                        f"Jina Scrape: Read timeout retry attempts exhausted, url: {url}"
                    )
                    raise e

            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code

                # Retryable: 5xx (server errors) + specific 4xx (408, 409, 425, 429)
                should_retry = status_code >= 500 or status_code in [408, 409, 425, 429]

                if should_retry and attempt < len(retry_delays):
                    logger.info(
                        f"Jina Scrape: HTTP {status_code} (retryable), retry in {delay}s, url: {url}"
                    )
                    await asyncio.sleep(delay)
                    continue
                elif should_retry:
                    logger.error(
                        f"Jina Scrape: HTTP {status_code} retry exhausted, url: {url}"
                    )
                    raise e
                else:
                    logger.error(
                        f"Jina Scrape: HTTP {status_code} (non-retryable), url: {url}"
                    )
                    raise e

            except httpx.RequestError as e:
                if attempt < len(retry_delays):
                    logger.info(
                        f"Jina Scrape: Unknown request exception: {e}, url: {url}, {delay}s before next attempt (attempt {attempt + 1})"
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(
                        f"Jina Scrape: Unknown request exception retry attempts exhausted, url: {url}"
                    )
                    raise e

    except Exception as e:
        error_msg = f"Jina Scrape: Unexpected error occurred: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "filename": "",
            "content": "",
            "error": error_msg,
        }

    # Get the scraped content
    content = response.text

    if not content:
        return {
            "success": False,
            "filename": "",
            "content": "",
            "error": "No content returned from Jina.ai API",
        }

    # handle insufficient balance error
    try:
        content_dict = json.loads(content)
    except json.JSONDecodeError:
        content_dict = None
    if (
        isinstance(content_dict, dict)
        and content_dict.get("name") == "InsufficientBalanceError"
    ):
        return {
            "success": False,
            "filename": "",
            "content": "",
            "error": "Insufficient balance",
        }

    # Extract first max_chars characters
    displayed_content = content[:max_chars]

    return {
        "success": True,
        "content": displayed_content,
        "error": "",
    }


async def scrape_url_with_python(
    url: str, custom_headers: Dict[str, str] = None, max_chars: int = 102400 * 4
) -> Dict[str, Any]:
    """
    Fallback scraping method using Python's httpx library directly.

    Args:
        url (str): The URL to scrape content from
        custom_headers (Dict[str, str]): Additional headers to include in the request
        max_chars (int): Maximum number of characters to reserve for the scraped content

    Returns:
        Dict[str, Any]: A dictionary containing:
            - success (bool): Whether the operation was successful
            - content (str): The scraped content (truncated to max_chars if necessary)
            - error (str): Error message if the operation failed
    """
    # Validate input
    if not url or not url.strip():
        return {
            "success": False,
            "content": "",
            "error": "URL cannot be empty",
        }

    try:
        # Prepare headers
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        # Add custom headers if provided
        if custom_headers:
            headers.update(custom_headers)

        # Retry configuration
        retry_delays = [1, 2, 4]

        for attempt, delay in enumerate(retry_delays, 1):
            try:
                # Make the request using httpx library
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        url,
                        headers=headers,
                        timeout=httpx.Timeout(None, connect=20, read=60),
                        follow_redirects=True,
                    )

                # Check if request was successful
                response.raise_for_status()
                break  # Success, exit retry loop

            except httpx.ConnectTimeout as e:
                if attempt < len(retry_delays):
                    logger.info(
                        f"Python Scrape: Connection timeout, {delay}s before next attempt (attempt {attempt + 1})"
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(
                        f"Python Scrape: Connection retry attempts exhausted, url: {url}"
                    )
                    raise e

            except httpx.ConnectError as e:
                if attempt < len(retry_delays):
                    logger.info(
                        f"Python Scrape: Connection error: {e}, {delay}s before next attempt"
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(
                        f"Python Scrape: Connection retry attempts exhausted, url: {url}"
                    )
                    raise e

            except httpx.ReadTimeout as e:
                if attempt < len(retry_delays):
                    logger.info(
                        f"Python Scrape: Read timeout, {delay}s before next attempt (attempt {attempt + 1})"
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(
                        f"Python Scrape: Read timeout retry attempts exhausted, url: {url}"
                    )
                    raise e

            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code

                # Retryable: 5xx (server errors) + specific 4xx (408, 409, 425, 429)
                should_retry = status_code >= 500 or status_code in [408, 409, 425, 429]

                if should_retry and attempt < len(retry_delays):
                    logger.info(
                        f"Python Scrape: HTTP {status_code} (retryable), retry in {delay}s, url: {url}"
                    )
                    await asyncio.sleep(delay)
                    continue
                elif should_retry:
                    logger.error(
                        f"Python Scrape: HTTP {status_code} retry exhausted, url: {url}"
                    )
                    raise e
                else:
                    logger.error(
                        f"Python Scrape: HTTP {status_code} (non-retryable), url: {url}"
                    )
                    raise e

            except httpx.RequestError as e:
                if attempt < len(retry_delays):
                    logger.info(
                        f"Python Scrape: Unknown request exception: {e}, url: {url}, {delay}s before next attempt (attempt {attempt + 1})"
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(
                        f"Python Scrape: Unknown request exception retry attempts exhausted, url: {url}"
                    )
                    raise e

    except Exception as e:
        error_msg = f"Python Scrape: Unexpected error occurred: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "content": "",
            "error": error_msg,
        }

    # Get the scraped content
    content = response.text

    if not content:
        return {
            "success": False,
            "content": "",
            "error": "No content returned from URL",
        }

    # Extract first max_chars characters
    displayed_content = content[:max_chars]

    return {
        "success": True,
        "content": displayed_content,
        "error": "",
    }


EXTRACT_INFO_PROMPT = """You are given a piece of content and the requirement of information to extract. Your task is to extract the information specifically requested. Be precise and focus exclusively on the requested information.

INFORMATION TO EXTRACT:
{}

INSTRUCTIONS:
1. Extract the information relevant to the focus above.
2. If the exact information is not found, extract the most closely related details.
3. Be specific and include exact details when available.
4. Clearly organize the extracted information for easy understanding.
5. Do not include general summaries or unrelated content.

CONTENT TO ANALYZE:
{}

EXTRACTED INFORMATION:"""


def get_prompt_with_truncation(
    info_to_extract: str, content: str, truncate_last_num_chars: int = -1
) -> str:
    if truncate_last_num_chars > 0:
        content = content[:-truncate_last_num_chars] + "[...truncated]"

    # Prepare the prompt
    prompt = EXTRACT_INFO_PROMPT.format(info_to_extract, content)
    return prompt


async def extract_info_with_llm(
    url: str,
    content: str,
    info_to_extract: str,
    model: str = "LLM",
    max_tokens: int = 4096,
) -> Dict[str, Any]:
    """
    Summarize content using an LLM API.

    Args:
        content (str): The content to summarize
        info_to_extract (str): The specific types of information to extract (usually a question)
        model (str): The model to use for summarization
        max_tokens (int): Maximum tokens for the response

    Returns:
        Dict[str, Any]: A dictionary containing:
            - success (bool): Whether the operation was successful
            - extracted_info (str): The extracted information
            - error (str): Error message if the operation failed
            - model_used (str): The model used for summarization
            - tokens_used (int): Number of tokens used (if available)
    """

    # Validate input
    if not content or not content.strip():
        return {
            "success": False,
            "extracted_info": "",
            "error": "Content cannot be empty",
            "model_used": model,
            "tokens_used": 0,
        }

    prompt = get_prompt_with_truncation(info_to_extract, content)

    # Prepare the payload
    if "gpt" in model:
        payload = {
            "model": model,
            "max_completion_tokens": max_tokens,
            "messages": [
                {"role": "user", "content": prompt},
            ],
        }
        # Add cost-saving parameters for GPT-5 models
        if "gpt-5" in model.lower() or "gpt5" in model.lower():
            # payload["service_tier"] = "flex"
            payload["reasoning_effort"] = "minimal"
    else:
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "user", "content": prompt},
            ],
            "temperature": 1.0,
            # "top_p": 0.8,
            # "top_k": 20,
        }

    # Validate LLM endpoint configuration early for clearer errors
    if not SUMMARY_LLM_BASE_URL or not SUMMARY_LLM_BASE_URL.strip():
        return {
            "success": False,
            "extracted_info": "",
            "error": "SUMMARY_LLM_BASE_URL environment variable is not set",
            "model_used": model,
            "tokens_used": 0,
        }

    # Prepare headers (add Authorization if API key is available)
    headers = {"Content-Type": "application/json"}
    if SUMMARY_LLM_API_KEY:
        headers["Authorization"] = f"Bearer {SUMMARY_LLM_API_KEY}"

    try:
        # Retry configuration
        connect_retry_delays = [1, 2, 4, 8]

        for attempt, delay in enumerate(connect_retry_delays, 1):
            try:
                # Make the API request using httpx
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        SUMMARY_LLM_BASE_URL,
                        headers=headers,
                        json=payload,
                        timeout=httpx.Timeout(None, connect=30, read=300),
                    )
                    if response.text and len(response.text) >= 50:
                        tail_50 = response.text[-50:]
                        repeat_count = response.text.count(tail_50)
                        if repeat_count > 5:
                            logger.info("Repeat detected in extract_info_with_llm")
                            continue

                # Check if the request was successful
                if (
                    "Requested token count exceeds the model's maximum context length"
                    in response.text
                    or "longer than the model's context length" in response.text
                ):
                    prompt = get_prompt_with_truncation(
                        info_to_extract,
                        content,
                        truncate_last_num_chars=40960 * attempt,
                    )  # remove 40k * num_attempts chars from the end of the content
                    payload["messages"][0]["content"] = prompt
                    continue  # no need to raise error here, just try again

                response.raise_for_status()
                break  # Success, exit retry loop

            except httpx.ConnectTimeout as e:
                # connection timeout, retry
                if attempt < len(connect_retry_delays):
                    logger.info(
                        f"Jina Scrape and Extract Info: Connection timeout, {delay}s before next attempt (attempt {attempt + 1})"
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(
                        "Jina Scrape and Extract Info: Connection retry attempts exhausted"
                    )
                    raise e

            except httpx.ConnectError as e:
                # connection error, retry
                if attempt < len(connect_retry_delays):
                    logger.info(
                        f"Jina Scrape and Extract Info: Connection error: {e}, {delay}s before next attempt"
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(
                        "Jina Scrape and Extract Info: Connection retry attempts exhausted"
                    )
                    raise e

            except httpx.ReadTimeout as e:
                # read timeout, LLM API is too slow, no need to retry
                if attempt < len(connect_retry_delays):
                    logger.info(
                        f"Jina Scrape and Extract Info: LLM API attempt {attempt} read timeout"
                    )
                    continue
                else:
                    logger.error(
                        f"Jina Scrape and Extract Info: LLM API read timeout retry attempts exhausted, please check the request complexity, information to extract: {info_to_extract}, length of content: {len(content)}, url: {url}"
                    )
                    raise e

            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code

                # Special case: GPT-5 service_tier parameter compatibility issue
                if (
                    "gpt-5" in model.lower() or "gpt5" in model.lower()
                ) and "service_tier" in payload:
                    logger.info(
                        "Extract Info: GPT-5 service_tier error, removing and retrying"
                    )
                    payload.pop("service_tier", None)
                    if attempt < len(connect_retry_delays):
                        await asyncio.sleep(delay)
                        continue

                # Retryable: 5xx (server errors) + specific 4xx (408, 409, 425, 429)
                should_retry = status_code >= 500 or status_code in [408, 409, 425, 429]

                if should_retry and attempt < len(connect_retry_delays):
                    logger.info(
                        f"Extract Info: HTTP {status_code} (retryable), retry in {delay}s"
                    )
                    await asyncio.sleep(delay)
                    continue
                elif should_retry:
                    logger.error(f"Extract Info: HTTP {status_code} retry exhausted")
                    raise e
                else:
                    logger.error(f"Extract Info: HTTP {status_code} (non-retryable)")
                    raise httpx.HTTPStatusError(
                        f"response.text: {response.text}",
                        request=e.request,
                        response=e.response,
                    ) from e

            except httpx.RequestError as e:
                logger.error(
                    f"Jina Scrape and Extract Info: Unknown request exception: {e}"
                )
                raise e

    except Exception as e:
        error_msg = f"Jina Scrape and Extract Info: Unexpected error during LLM API call: {str(e)}"
        logger.error(error_msg)
        return {
            "success": False,
            "extracted_info": "",
            "error": error_msg,
            "model_used": model,
            "tokens_used": 0,
        }

    # Parse the response
    try:
        response_data = response.json()

    except json.JSONDecodeError as e:
        error_msg = (
            f"Jina Scrape and Extract Info: Failed to parse LLM API response: {str(e)}"
        )
        logger.error(error_msg)
        logger.error(f"Raw response: {response.text}")
        return {
            "success": False,
            "extracted_info": "",
            "error": error_msg,
            "model_used": model,
            "tokens_used": 0,
        }

    # Extract summary from response
    if "choices" in response_data and len(response_data["choices"]) > 0:
        try:
            summary = response_data["choices"][0]["message"]["content"]
        except Exception as e:
            error_msg = f"Jina Scrape and Extract Info: Failed to get summary from LLM API response: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "extracted_info": "",
                "error": error_msg,
                "model_used": model,
                "tokens_used": 0,
            }

        # Extract token usage if available
        tokens_used = 0
        if "usage" in response_data:
            tokens_used = response_data["usage"].get("total_tokens", 0)

        return {
            "success": True,
            "extracted_info": summary,
            "error": "",
            "model_used": model,
            "tokens_used": tokens_used,
        }
    elif "error" in response_data:
        error_msg = (
            f"Jina Scrape and Extract Info: LLM API error: {response_data['error']}"
        )
        logger.error(error_msg)
        return {
            "success": False,
            "extracted_info": "",
            "error": error_msg,
            "model_used": model,
            "tokens_used": 0,
        }
    else:
        error_msg = f"Jina Scrape and Extract Info: No valid response from LLM API, response data: {response_data}"
        logger.error(error_msg)
        return {
            "success": False,
            "extracted_info": "",
            "error": error_msg,
            "model_used": model,
            "tokens_used": 0,
        }


if __name__ == "__main__":
    # Example usage and testing

    # Run the MCP server
    mcp.run(transport="stdio")
