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
import requests

REASONING_API_KEY = os.environ.get("REASONING_API_KEY")
REASONING_BASE_URL = os.environ.get("REASONING_BASE_URL")
REASONING_MODEL_NAME = os.environ.get("REASONING_MODEL_NAME")

# Initialize FastMCP server
mcp = FastMCP("reasoning-mcp-server-os")


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
    }
    headers = {
        "Authorization": f"Bearer {REASONING_API_KEY}",
        "Content-Type": "application/json",
    }

    response = requests.post(REASONING_BASE_URL, json=payload, headers=headers)
    json_response = response.json()
    try:
        content = json_response["choices"][0]["message"]["content"]
        if "</think>" in content:
            content = content.split("</think>", 1)[1].strip()
        return content
    except Exception:
        print("Reasoning Error: only thinking content is returned")
        return json_response["choices"][0]["message"]["reasoning_content"]


if __name__ == "__main__":
    mcp.run(transport="stdio")
