# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

import asyncio
import base64
import os

from fastmcp import FastMCP
from openai import OpenAI

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

# Initialize FastMCP server
mcp = FastMCP("vision-mcp-server")

# Maximum file size for vision processing (20MB for images, 50MB for videos)
MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20MB
MAX_VIDEO_SIZE = 50 * 1024 * 1024  # 50MB


def guess_mime_media_type_from_extension(file_path: str) -> tuple[str, str]:
    """
    Guess the MIME type and media category based on the file extension.

    Returns:
        Tuple of (mime_type, media_category) where media_category is 'image' or 'video'
    """
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    # Image formats
    if ext in [".jpg", ".jpeg"]:
        return "image/jpeg", "image"
    elif ext == ".png":
        return "image/png", "image"
    elif ext == ".gif":
        return "image/gif", "image"
    elif ext == ".webp":
        return "image/webp", "image"
    elif ext == ".bmp":
        return "image/bmp", "image"
    elif ext == ".tiff" or ext == ".tif":
        return "image/tiff", "image"

    # Video formats
    elif ext == ".mp4":
        return "video/mp4", "video"
    elif ext == ".mov":
        return "video/quicktime", "video"
    elif ext == ".avi":
        return "video/x-msvideo", "video"
    elif ext == ".mkv":
        return "video/x-matroska", "video"
    elif ext == ".webm":
        return "video/webm", "video"

    # Default to JPEG for unknown formats
    return "image/jpeg", "image"


def _validate_file_size(file_path: str, media_category: str) -> tuple[bool, str]:
    """
    Validate file size based on media category.

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        file_size = os.path.getsize(file_path)
        max_size = MAX_VIDEO_SIZE if media_category == "video" else MAX_IMAGE_SIZE
        max_size_mb = max_size / (1024 * 1024)

        if file_size > max_size:
            return (
                False,
                f"[ERROR]: File size ({file_size / (1024 * 1024):.2f}MB) exceeds maximum allowed size ({max_size_mb}MB) for {media_category}",
            )

        if file_size == 0:
            return False, "[ERROR]: File is empty"

        return True, ""
    except Exception as e:
        return False, f"[ERROR]: Failed to check file size: {e}"


@mcp.tool()
async def visual_question_answering(media_path_or_url: str, question: str) -> str:
    """Ask question about an image or a video and get the answer with GPT-4o vision model.

    Args:
        media_path_or_url: The path of the image/video file locally or its URL. Supports images (jpg, png, gif, webp, bmp, tiff) and videos (mp4, mov, avi, mkv, webm).
        question: The question to ask about the image or video.

    Returns:
        The answer to the media-related question.
    """
    max_retries = 3
    retry = 0

    # Create client once outside the retry loop
    client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)

    # Initialize variables
    response = None
    media_data = None
    mime_type = None
    media_category = None

    while retry < max_retries:
        try:
            # Build message content
            content = [{"type": "text", "text": question}]

            if os.path.exists(media_path_or_url):  # Check if the file exists locally
                # Get media type and validate
                mime_type, media_category = guess_mime_media_type_from_extension(
                    media_path_or_url
                )

                # Validate file size
                is_valid, error_msg = _validate_file_size(
                    media_path_or_url, media_category
                )
                if not is_valid:
                    return error_msg

                # Read and encode file
                with open(media_path_or_url, "rb") as media_file:
                    media_data = base64.b64encode(media_file.read()).decode("utf-8")

                # Add image_url content (works for both images and videos in OpenAI API)
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{media_data}"},
                    }
                )

            elif "home/user" in media_path_or_url:
                return "[ERROR]: The visual_question_answering tool cannot access sandbox files, please use the local path provided by original instruction"

            else:  # Otherwise, assume it's a URL
                # Basic URL validation
                if not media_path_or_url.startswith(("http://", "https://")):
                    return "[ERROR]: Invalid URL format. URLs must start with http:// or https://"

                content.append(
                    {"type": "image_url", "image_url": {"url": media_path_or_url}}
                )

            # Make API call
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": content}],
                max_tokens=1024,
            )

            # If we reach here, the API call was successful
            break

        except FileNotFoundError:
            return f"[ERROR]: File not found: {media_path_or_url}"
        except PermissionError:
            return f"[ERROR]: Permission denied when reading file: {media_path_or_url}"
        except Exception as e:
            retry += 1
            if retry >= max_retries:
                error_type = (
                    "API call"
                    if media_data is not None or not os.path.exists(media_path_or_url)
                    else "file processing"
                )
                return f"[ERROR]: Visual question answering failed during {error_type}: {e}\nNote: Files from sandbox are not available. You should use local path given in the instruction.\nSupported image formats: jpg, png, gif, webp, bmp, tiff\nSupported video formats: mp4, mov, avi, mkv, webm\nURLs must be publicly accessible and start with http:// or https://"
            await asyncio.sleep(5 * (2**retry))

    # Extract and return response
    try:
        if response and response.choices and len(response.choices) > 0:
            return response.choices[0].message.content
        else:
            return "[ERROR]: Received empty response from API"
    except (AttributeError, IndexError) as e:
        return f"[ERROR]: Failed to parse API response: {e}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
