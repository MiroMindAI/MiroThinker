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
import tempfile
import requests
from urllib.parse import urlparse
from fastmcp import FastMCP
from openai import OpenAI
import base64
import mimetypes
import wave
import contextlib
from mutagen import File as MutagenFile

WHISPER_API_KEY = os.environ.get("WHISPER_API_KEY")
WHISPER_BASE_URL = os.environ.get("WHISPER_BASE_URL")
WHISPER_MODEL_NAME = os.environ.get("WHISPER_MODEL_NAME")

# Initialize FastMCP server
mcp = FastMCP("audio-mcp-server-os")


def _get_audio_extension(url: str, content_type: str = None) -> str:
    """
    Determine the appropriate audio file extension from URL or content type.

    Args:
        url: The URL of the audio file
        content_type: The content type from HTTP headers

    Returns:
        File extension (with dot) to use for temporary file
    """
    # First try to get extension from URL
    parsed_url = urlparse(url)
    path = parsed_url.path.lower()

    # Common audio extensions
    audio_extensions = [".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".wma"]
    for ext in audio_extensions:
        if path.endswith(ext):
            return ext

    # If no extension found in URL, try content type
    if content_type:
        content_type = content_type.lower()
        if "mp3" in content_type or "mpeg" in content_type:
            return ".mp3"
        elif "wav" in content_type:
            return ".wav"
        elif "m4a" in content_type:
            return ".m4a"
        elif "aac" in content_type:
            return ".aac"
        elif "ogg" in content_type:
            return ".ogg"
        elif "flac" in content_type:
            return ".flac"

    # Default fallback to mp3
    return ".mp3"


def _get_audio_duration(audio_path: str) -> float:
    """
    Get audio duration in seconds.

    Tries to use wave (for .wav), then falls back to mutagen (for mp3, etc).
    """
    # Try using wave for .wav files
    try:
        with contextlib.closing(wave.open(audio_path, "rb")) as f:
            frames = f.getnframes()
            rate = f.getframerate()
            duration = frames / float(rate)
            if duration > 0:
                return duration
    except Exception:
        pass  # Not a wav file or failed

    # Try using mutagen for other audio formats (mp3, etc)
    try:
        audio = MutagenFile(audio_path)
        if (
            audio is not None
            and hasattr(audio, "info")
            and hasattr(audio.info, "length")
        ):
            duration = float(audio.info.length)
            if duration > 0:
                return duration
    except Exception as e:
        return f"Failed to get audio duration: {e}"


def _encode_audio_file(audio_path: str) -> tuple[str, str]:
    """Encode audio file to base64 and determine format."""
    with open(audio_path, "rb") as audio_file:
        audio_data = audio_file.read()
        encoded_string = base64.b64encode(audio_data).decode("utf-8")

    # Determine file format from file extension
    mime_type, _ = mimetypes.guess_type(audio_path)
    if mime_type and mime_type.startswith("audio/"):
        mime_format = mime_type.split("/")[-1]
        # Map MIME type formats to OpenAI supported formats
        format_mapping = {
            "mpeg": "mp3",  # audio/mpeg -> mp3
            "wav": "wav",  # audio/wav -> wav
            "wave": "wav",  # audio/wave -> wav
        }
        file_format = format_mapping.get(mime_format, "mp3")
    else:
        # Default to mp3 if we can't determine
        file_format = "mp3"

    return encoded_string, file_format


@mcp.tool()
async def audio_transcription(audio_path_or_url: str) -> str:
    """
    Transcribe audio file to text and return the transcription.
    Args:
        audio_path_or_url: The path of the audio file locally or its URL.

    Returns:
        The transcription of the audio file.
    """

    client = OpenAI(base_url=WHISPER_BASE_URL, api_key=WHISPER_API_KEY)

    try:
        if os.path.exists(audio_path_or_url):  # Check if the file exists locally
            with open(audio_path_or_url, "rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    model=WHISPER_MODEL_NAME, file=audio_file
                )
        else:
            # download the audio file from the URL
            response = requests.get(audio_path_or_url)
            response.raise_for_status()  # Raise an exception for bad status codes

            # Basic content validation - check if response has content
            if not response.content:
                return "Audio transcription failed: Downloaded file is empty"

            # Check content type if available
            content_type = response.headers.get("content-type", "").lower()
            if content_type and not any(
                media_type in content_type
                for media_type in ["audio", "video", "application/octet-stream"]
            ):
                return f"Audio transcription failed: Invalid content type '{content_type}'. Expected audio file."

            # Get proper extension for the temporary file
            file_extension = _get_audio_extension(audio_path_or_url, content_type)

            # Use proper temporary file handling with correct extension
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=file_extension
            ) as temp_file:
                temp_file.write(response.content)
                temp_audio_path = temp_file.name

            try:
                with open(temp_audio_path, "rb") as audio_file:
                    transcription = client.audio.transcriptions.create(
                        model="whisper-large-v3-turbo", file=audio_file
                    )
            finally:
                # Clean up the temp file
                if os.path.exists(temp_audio_path):
                    os.remove(temp_audio_path)

    except requests.RequestException as e:
        return f"Audio transcription failed: Failed to download audio file - {e}"
    except Exception as e:
        return f"Audio transcription failed: {e}"

    return transcription.text


if __name__ == "__main__":
    mcp.run(transport="stdio")
