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

import asyncio
import base64
import contextlib
import mimetypes
import os
import tempfile
import wave
from urllib.parse import urlparse

import requests
from fastmcp import FastMCP
from mutagen import File as MutagenFile
from openai import OpenAI

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

# Initialize FastMCP server
mcp = FastMCP("audio-mcp-server")


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
        return f"[ERROR]: Failed to get audio duration: {e}"


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
        audio_path_or_url: The path of the audio file locally or its URL. Path from sandbox is not supported. YouTube URL is not supported.

    Returns:
        The transcription of the audio file.
    """
    max_retries = 3
    retry = 0
    transcription = None

    while retry < max_retries:
        try:
            client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
            if os.path.exists(audio_path_or_url):  # Check if the file exists locally
                with open(audio_path_or_url, "rb") as audio_file:
                    transcription = client.audio.transcriptions.create(
                        model="gpt-4o-transcribe", file=audio_file
                    )
            elif "home/user" in audio_path_or_url:
                return "[ERROR]: The audio_transcription tool cannot access to sandbox file, please use the local path provided by original instruction"
            else:
                # download the audio file from the URL
                response = requests.get(audio_path_or_url)
                response.raise_for_status()  # Raise an exception for bad status codes

                # Basic content validation - check if response has content
                if not response.content:
                    return (
                        "[ERROR]: Audio transcription failed: Downloaded file is empty"
                    )

                # Check content type if available
                content_type = response.headers.get("content-type", "").lower()

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
                            model="gpt-4o-mini-transcribe", file=audio_file
                        )
                finally:
                    # Clean up the temp file
                    if os.path.exists(temp_audio_path):
                        os.remove(temp_audio_path)
            break

        except requests.RequestException as e:
            retry += 1
            if retry >= max_retries:
                return f"[ERROR]: Audio transcription failed: Failed to download audio file - {e}.\nNote: Files from sandbox are not available. You should use local path given in the instruction. \nURLs must include the proper scheme (e.g., 'https://') and be publicly accessible. The file should be in a common audio format such as MP3, WAV, or M4A.\nNote: YouTube video URL is not supported."
            await asyncio.sleep(5 * (2**retry))
        except Exception as e:
            retry += 1
            if retry >= max_retries:
                return f"[ERROR]: Audio transcription failed: {e}\nNote: Files from sandbox are not available. You should use local path given in the instruction. The file should be in a common audio format such as MP3, WAV, or M4A.\nNote: YouTube video URL is not supported."
            await asyncio.sleep(5 * (2**retry))

    return transcription.text


@mcp.tool()
async def audio_question_answering(audio_path_or_url: str, question: str) -> str:
    """
    Answer the question based on the given audio information.

    Args:
        audio_path_or_url: The path of the audio file locally or its URL. Path from sandbox is not supported. YouTube URL is not supported.
        question: The question to answer.

    Returns:
        The answer to the question, and the duration of the audio file.
    """
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)

        text_prompt = f"""Answer the following question based on the given \
        audio information:\n\n{question}"""

        if os.path.exists(audio_path_or_url):  # Check if the file exists locally
            encoded_string, file_format = _encode_audio_file(audio_path_or_url)
            duration = _get_audio_duration(audio_path_or_url)
        elif "home/user" in audio_path_or_url:
            return "The audio_question_answering tool cannot access to sandbox file, please use the local path provided by original instruction"
        else:
            # download the audio file from the URL
            response = requests.get(
                audio_path_or_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                },
            )
            response.raise_for_status()  # Raise an exception for bad status codes

            # Basic content validation - check if response has content
            if not response.content:
                return "[ERROR]: Audio question answering failed: Downloaded file is empty.\nNote: Files from sandbox are not available. You should use local path given in the instruction. \nURLs must include the proper scheme (e.g., 'https://') and be publicly accessible. The file should be in a common audio format such as MP3.\nNote: YouTube video URL is not supported."

            # Check content type if available
            content_type = response.headers.get("content-type", "").lower()

            # Get proper extension for the temporary file
            file_extension = _get_audio_extension(audio_path_or_url, content_type)

            # Use proper temporary file handling with correct extension
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=file_extension
            ) as temp_file:
                temp_file.write(response.content)
                temp_audio_path = temp_file.name

            try:
                encoded_string, file_format = _encode_audio_file(temp_audio_path)
                duration = _get_audio_duration(temp_audio_path)
            finally:
                # Clean up the temp file
                if os.path.exists(temp_audio_path):
                    os.remove(temp_audio_path)

        if encoded_string is None or file_format is None:
            return "[ERROR]: Audio question answering failed: Failed to encode audio file.\nNote: Files from sandbox are not available. You should use local path given in the instruction. \nURLs must include the proper scheme (e.g., 'https://') and be publicly accessible. The file should be in a common audio format such as MP3.\nNote: YouTube video URL is not supported."

        response = client.chat.completions.create(
            model="gpt-4o-audio-preview",
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant specializing in audio analysis.",
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text_prompt},
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": encoded_string,
                                "format": file_format,
                            },
                        },
                    ],
                },
            ],
        )
    except Exception as e:
        return f"[ERROR]: Audio question answering failed when calling OpenAI API: {e}\nNote: Files from sandbox are not available. You should use local path given in the instruction. The file should be in a common audio format such as MP3, WAV, or M4A.\nNote: YouTube video URL is not supported."

    response = response.choices[0].message.content
    response += f"\n\nAudio duration: {duration} seconds"

    return response


if __name__ == "__main__":
    mcp.run(transport="stdio")
