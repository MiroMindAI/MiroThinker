# Copyright (c) 2025 Miromind.ai
# This source code is licensed under the MIT License.

import base64
import os

import aiohttp
import requests
from fastmcp import FastMCP

VISION_API_KEY = os.environ.get("VISION_API_KEY")
VISION_BASE_URL = os.environ.get("VISION_BASE_URL")
VISION_MODEL_NAME = os.environ.get("VISION_MODEL_NAME")

# Initialize FastMCP server
mcp = FastMCP("vision-mcp-server-os")


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
                {"type": "image_url", "image_url": {"url": None}},
                {
                    "type": "text",
                    "text": question,
                },
            ],
        }
    ]

    headers = {
        "Authorization": f"Bearer {VISION_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        if os.path.exists(image_path_or_url):  # Check if the file exists locally
            with open(image_path_or_url, "rb") as image_file:
                image_data = base64.b64encode(image_file.read()).decode("utf-8")
                mime_type = guess_mime_media_type_from_extension(image_path_or_url)
                messages_for_llm[0]["content"][0]["image_url"]["url"] = (
                    f"data:{mime_type};base64,{image_data}"
                )
        elif image_path_or_url.startswith(("http://", "https://")):
            async with aiohttp.ClientSession() as session:
                async with session.get(image_path_or_url) as resp:
                    if resp.status == 200:
                        image_bytes = await resp.read()
                        mime_type = resp.headers.get(
                            "Content-Type", "image/png"
                        )  # fallback MIME type
                        image_data = base64.b64encode(image_bytes).decode("utf-8")
                        messages_for_llm[0]["content"][0]["image_url"]["url"] = (
                            f"data:{mime_type};base64,{image_data}"
                        )
                    else:
                        return f"Failed to fetch image from URL: {image_path_or_url}"
        else:
            messages_for_llm[0]["content"][0]["image_url"]["url"] = image_path_or_url

        payload = {"model": VISION_MODEL_NAME, "messages": messages_for_llm}

        response = requests.post(VISION_BASE_URL, json=payload, headers=headers)

    except Exception as e:
        return f"Error: {e}"

    try:
        return response.json()["choices"][0]["message"]["content"]
    except (AttributeError, IndexError):
        return response.json()


if __name__ == "__main__":
    mcp.run(transport="stdio")
