# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

import logging
import os

from anthropic import Anthropic
from fastmcp import FastMCP

logger = logging.getLogger("miroflow")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")

# Initialize FastMCP server
mcp = FastMCP("reasoning-mcp-server")


@mcp.tool()
async def reasoning(question: str) -> str:
    """You can use this tool to solve hard math problem, puzzle, riddle and IQ test question that requires a lot of chain of thought efforts.
    DO NOT use this tool for simple and obvious question.

    Args:
        question: The hard question.

    Returns:
        The answer to the question.
    """
    messages_for_llm = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": question,
                }
            ],
        }
    ]

    client = Anthropic(api_key=ANTHROPIC_API_KEY, base_url=ANTHROPIC_BASE_URL)
    response = client.messages.create(
        model="claude-3-7-sonnet-20250219",
        max_tokens=21000,
        thinking={
            "type": "enabled",
            "budget_tokens": 19000,
        },
        messages=messages_for_llm,
        stream=False,
    )

    try:
        return response.content[-1].text
    except Exception:
        logger.info("Reasoning Error: only thinking content is returned")
        return response.content[-1].thinking


if __name__ == "__main__":
    mcp.run(transport="stdio")
