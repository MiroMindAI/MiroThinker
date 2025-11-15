# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

import base64
import os

from anthropic import Anthropic
from fastmcp import FastMCP

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")

# Initialize FastMCP server
mcp = FastMCP("vision-mcp-server")


def guess_mime_media_type_from_extension(file_path: str) -> str:
    """Guess the MIME type based on the file extension."""
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()
    if ext in [".jpg", ".jpeg"]:
        return "image/jpeg"
    elif ext == ".png":
        return "image/png"
    elif ext == ".gif":
        return "image/gif"
    else:
        return "image/jpeg"  # Default to JPEG if unknown


@mcp.tool()
async def visual_question_answering(image_path_or_url: str, question: str) -> str:
    """Ask question about an image or a video and get the answer with a vision language model.

    Args:
        image_path_or_url: The path of the image file locally or its URL.
        question: The question to ask about the image.

    Returns:
        The answer to the image-related question.
    """
    messages_for_llm = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": None,
                },
                {
                    "type": "text",
                    "text": question,
                },
            ],
        }
    ]

    try:
        if os.path.exists(image_path_or_url):  # Check if the file exists locally
            with open(image_path_or_url, "rb") as image_file:
                image_data = base64.b64encode(image_file.read()).decode("utf-8")
                messages_for_llm[0]["content"][0]["source"] = dict(
                    type="base64",
                    media_type=guess_mime_media_type_from_extension(image_path_or_url),
                    data=image_data,
                )
        else:  # Otherwise, assume it's a URL
            messages_for_llm[0]["content"][0]["source"] = dict(
                type="url", url=image_path_or_url
            )

        client = Anthropic(api_key=ANTHROPIC_API_KEY, base_url=ANTHROPIC_BASE_URL)
        response = client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=1024,
            messages=messages_for_llm,
        )
    except Exception as e:
        return f"Error: {e}"

    try:
        return response.content[0].text
    except (AttributeError, IndexError):
        return str(response)


if __name__ == "__main__":
    mcp.run(transport="stdio")
