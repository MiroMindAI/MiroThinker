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

import logging
import os
import random
import time

import requests
from fastmcp import FastMCP

logger = logging.getLogger("miroflow")

REASONING_API_KEY = os.environ.get("REASONING_API_KEY")
REASONING_BASE_URL = os.environ.get("REASONING_BASE_URL")
REASONING_MODEL_NAME = os.environ.get("REASONING_MODEL_NAME")

# Initialize FastMCP server
mcp = FastMCP("reasoning-mcp-server-os")

# Retry configuration
MAX_RETRIES = 10
BACKOFF_BASE = 1.0  # initial backoff in seconds
BACKOFF_MAX = 30.0  # maximum backoff in seconds


def post_with_retry(url, json, headers):
    """Send POST request with retry and exponential backoff.
    Returns response object if success, otherwise None."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(url, json=json, headers=headers, timeout=600)
            if resp.status_code == 200:
                return resp
            else:
                logger.warning(
                    f"HTTP {resp.status_code} on attempt {attempt}: {resp.text[:200]}"
                )
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request failed on attempt {attempt}: {e}")

        # Backoff before next retry
        if attempt < MAX_RETRIES:
            sleep_time = min(BACKOFF_BASE * (2 ** (attempt - 1)), BACKOFF_MAX)
            # Add jitter to avoid thundering herd
            sleep_time *= 0.8 + 0.4 * random.random()
            logger.info(f"Retrying in {sleep_time:.1f}s...")
            time.sleep(sleep_time)

    logger.warning(f"All {MAX_RETRIES} retries failed for {url}")
    return None


@mcp.tool()
async def reasoning(question: str) -> str:
    """You can use this tool use solve hard math problem, puzzle, riddle and IQ test question that requires a lot of chain of thought efforts.
    DO NOT use this tool for simple and obvious question.

    Args:
        question: The hard question.

    Returns:
        The answer to the question.
    """
    payload = {
        "model": REASONING_MODEL_NAME,
        "messages": [{"role": "user", "content": question}],
        "temperature": 0.6,
        "top_p": 0.95,
    }
    headers = {
        "Authorization": f"Bearer {REASONING_API_KEY}",
        "Content-Type": "application/json",
    }

    response = post_with_retry(REASONING_BASE_URL, json=payload, headers=headers)
    if response is None:
        return "Reasoning service unavailable. Please try again later."

    json_response = response.json()
    try:
        content = json_response["choices"][0]["message"]["content"]
        if "</think>" in content:
            content = content.split("</think>", 1)[1].strip()
        return content
    except Exception:
        logger.info("Reasoning Error: only thinking content is returned")
        return json_response["choices"][0]["message"]["reasoning_content"]


if __name__ == "__main__":
    mcp.run(transport="stdio")
