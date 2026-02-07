# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

"""
Parsing utilities for LLM responses and tool calls.

This module provides functions for:
- Parsing tool calls from LLM responses (both OpenAI and MCP formats)
- Extracting text content from responses
- Safe JSON parsing with automatic repair
- Failure experience summary extraction
"""

import json
import logging
import re
from typing import Any, Dict, List, Union

from json_repair import repair_json

logger = logging.getLogger("miroflow_agent")


def parse_tool_server_mapping(system_prompt: str) -> dict:
    """
    Parse system prompt to extract tool_name → server_name mapping.

    Parses patterns like:
        ## Server name: tool-python
        ### Tool name: run_python_code

    Only extracts mappings for the 3 target tools that models commonly get wrong:
    run_python_code, google_search, scrape_and_extract_info.

    Args:
        system_prompt: The system prompt containing MCP tool definitions

    Returns:
        Dict mapping tool_name to correct server_name, e.g.
        {"run_python_code": "tool-python", "google_search": "search_and_scrape_webpage", ...}
    """
    TARGET_TOOLS = {"run_python_code", "google_search", "scrape_and_extract_info"}
    mapping = {}
    current_server = None
    for line in system_prompt.split("\n"):
        server_match = re.match(r"## Server name:\s*(.+)", line)
        if server_match:
            current_server = server_match.group(1).strip()
            continue
        tool_match = re.match(r"### Tool name:\s*(.+)", line)
        if tool_match and current_server:
            tool_name = tool_match.group(1).strip()
            if tool_name in TARGET_TOOLS:
                mapping[tool_name] = current_server
    return mapping


# Module-level cache for tool_server_mapping
_tool_server_mapping: dict = {}


def set_tool_server_mapping(system_prompt: str) -> None:
    """
    Parse system prompt and cache the tool_name → server_name mapping.

    Should be called once when system prompt is available.

    Args:
        system_prompt: The system prompt containing MCP tool definitions
    """
    global _tool_server_mapping
    _tool_server_mapping = parse_tool_server_mapping(system_prompt)


def fix_server_name_in_text(text: str) -> str:
    """
    Fix incorrect server_name and tool_name in MCP XML tool calls.

    Uses the cached tool_server_mapping (parsed from system prompt) to determine
    the correct server_name for each tool. Only fixes the 3 target tools:
    run_python_code, google_search, scrape_and_extract_info.

    Also handles the special case where model outputs tool_name=python
    (should be run_python_code).

    Args:
        text: The LLM response text containing MCP tool calls

    Returns:
        Text with corrected server_name and tool_name if needed
    """
    if not isinstance(text, str):
        return text

    mapping = _tool_server_mapping
    if not mapping:
        return text

    # Special case: tool_name=python or python_code → rename to run_python_code
    # Only apply if system prompt defines run_python_code (not python)
    if "run_python_code" in mapping:
        for wrong_name in ("python", "python_code"):
            tag = f"<tool_name>{wrong_name}</tool_name>"
            if tag in text:
                text = text.replace(tag, "<tool_name>run_python_code</tool_name>")

    # Fix server_name for each target tool using the mapping from system prompt
    for tool_name, correct_server in mapping.items():
        tool_tag = f"<tool_name>{tool_name}</tool_name>"
        if tool_tag not in text:
            continue
        correct_server_tag = f"<server_name>{correct_server}</server_name>"
        if correct_server_tag in text:
            continue
        text = re.sub(
            r'<server_name>[^<]+</server_name>(\s*' + re.escape(tool_tag) + r')',
            correct_server_tag + r'\1',
            text,
        )

    return text


def filter_none_values(arguments: Union[Dict, Any]) -> Union[Dict, Any]:
    """
    Filter out keys with None values from arguments dictionary.

    Args:
        arguments: A dictionary to filter, or any other value

    Returns:
        The filtered dictionary, or the original value if not a dict
    """
    if not isinstance(arguments, dict):
        return arguments
    return {k: v for k, v in arguments.items() if v is not None}


def _fix_backslash_escapes(json_str: str) -> str:
    """
    Fix common backslash escape issues in JSON strings.
    This handles cases where backslashes in string values are not properly escaped.

    Common issues:
    - Unescaped backslashes before non-escape characters

    Note: This is a conservative fix that preserves valid escape sequences
    (\\, \", \/, \b, \f, \n, \r, \t) and only fixes clearly problematic cases.
    """
    fixed_str = json_str

    # Fix backslashes that are not part of valid escape sequences
    # Valid JSON escape sequences: \\, \", \/, \b, \f, \n, \r, \t, \uXXXX
    # Pattern: backslash not followed by a valid escape character
    # This regex matches \ followed by anything except valid escape chars
    # But we need to be careful not to match already-escaped backslashes (\\)

    # Strategy: Find all backslashes, but skip those that are:
    # 1. Already escaped (\\)
    # 2. Part of valid escape sequences (\", \/, \b, \f, \n, \r, \t, \u)

    # More conservative approach: Only fix backslashes before uppercase letters
    # (common in Windows paths) and other clearly problematic patterns
    # This avoids breaking valid JSON escape sequences

    # Fix backslashes before uppercase letters (Windows paths like C:\Users)
    fixed_str = re.sub(
        r"(?<!\\)\\([A-Z])",  # Backslash before uppercase letter, not already escaped
        r"\\\\\1",
        fixed_str,
    )

    # Fix backslashes before digits (common in paths like \1, \2)
    fixed_str = re.sub(
        r"(?<!\\)\\([0-9])",  # Backslash before digit, not already escaped
        r"\\\\\1",
        fixed_str,
    )

    # Fix other unescaped backslashes that are not part of valid escape sequences
    # This is more aggressive but should be safe after json_repair fails
    # Valid escape chars: \\, ", /, b, f, n, r, t, u
    # Use a capturing group to preserve the character after backslash
    fixed_str = re.sub(
        r'(?<!\\)\\([^\\"/bfnrtu])',  # Backslash followed by invalid escape char
        r"\\\\\1",  # Escape it and preserve the character
        fixed_str,
    )

    return fixed_str


def safe_json_loads(arguments_str: str) -> Dict[str, Any]:
    """
    Safely parse a JSON string with multiple fallbacks.

    Parsing strategy:
    1. Try standard json.loads()
    2. If it fails, try json_repair to fix common issues
    3. If all attempts fail, return an error object

    Args:
        arguments_str: JSON string to parse

    Returns:
        Parsed dictionary, or error dict with 'error' and 'raw' keys
    """
    # Step 1: Try standard JSON parsing
    try:
        return json.loads(arguments_str)
    except json.JSONDecodeError:
        pass

    # Step 2: Try json_repair to fix common issues
    try:
        repaired = repair_json(arguments_str, ensure_ascii=False)
        return json.loads(repaired)
    except Exception:
        logger.warning(f"Unable to parse JSON: {arguments_str}")

    # Step 3: Give up and return error information
    return {
        "error": "Failed to parse arguments",
        "raw": arguments_str,
    }


def extract_failure_experience_summary(text: str) -> str:
    """
    Extract failure experience summary from LLM response text.

    The text may contain:
    - <think>...</think> block (thinking content)
    - Main content after </think> and before <use_mcp_tool>
    - <use_mcp_tool>...</use_mcp_tool> block (tool call, ignored)

    Examples:
        "<think>\n{xxx}\n</think>\n\n{content}\n\n<use_mcp_tool>..."
        "<think>\n{xxx}\n</think>\n\n{content}"
        "{content}"  (no think block)

    Returns:
        - If content is empty after strip, return think_content
        - If both think_content and content are non-empty, return content
        - mcp_block is never used
    """
    if not text:
        return ""

    think_content = ""
    content = ""

    # Extract think content
    think_match = re.search(r"<think>([\s\S]*?)</think>", text)
    if think_match:
        think_content = think_match.group(1).strip()
        # Get content after </think>
        after_think = text[think_match.end() :]
    else:
        # No think block, entire text is potential content
        after_think = text

    # Remove <use_mcp_tool>...</use_mcp_tool> block from content
    mcp_match = re.search(r"<use_mcp_tool>[\s\S]*", after_think)
    if mcp_match:
        content = after_think[: mcp_match.start()].strip()
    else:
        content = after_think.strip()

    # Apply the rules:
    # - If content is empty, use think_content
    # - If both are non-empty, use content
    if content:
        return content
    else:
        return think_content


def extract_llm_response_text(llm_response: Union[str, Dict]) -> str:
    """
    Extract text from LLM response, excluding <use_mcp_tool> tags.

    Stops immediately when <use_mcp_tool> tag is encountered, returning
    only the content before it.

    Args:
        llm_response: Either a string or a dict with 'content' key

    Returns:
        Extracted text content, stripped of trailing whitespace
    """
    # If it's a dictionary type, extract the content field
    if isinstance(llm_response, dict):
        content = llm_response.get("content", "")
    else:
        # If it's a string type, use directly
        content = str(llm_response)

    # Find the position of <use_mcp_tool> tag
    tool_start_pattern = r"<use_mcp_tool>"
    match = re.search(tool_start_pattern, content)

    if match:
        # If <use_mcp_tool> tag is found, only return content before the tag
        return content[: match.start()].strip()
    else:
        # If no tag is found, return the complete content
        return content.strip()


def parse_llm_response_for_tool_calls(
    llm_response_content_text: Union[str, Dict, List],
) -> List[Dict[str, Any]]:
    """
    Parse tool calls from LLM response content.

    Supports multiple formats:
    - OpenAI Response API format (dict with 'output' containing function_call items)
    - OpenAI Completion API format (list of tool_call objects)
    - MCP format (<use_mcp_tool> XML tags in text)

    Args:
        llm_response_content_text: Response content in any supported format

    Returns:
        List of tool call dicts with keys: server_name, tool_name, arguments, id
    """
    # tool_calls or MCP reponse are handled differently
    # for openai response api, the tool_calls are in the response text
    if isinstance(llm_response_content_text, dict):
        tool_calls = []
        for item in llm_response_content_text.get("output") or []:
            if item.get("type") == "function_call":
                name = item.get("name", "")
                if "-" in name:
                    server_name, tool_name = name.rsplit("-", maxsplit=1)
                else:
                    server_name = "unknown"
                    tool_name = name
                arguments_str = item.get("arguments")
                arguments = safe_json_loads(arguments_str)
                arguments = filter_none_values(arguments)
                tool_calls.append(
                    dict(
                        server_name=server_name,
                        tool_name=tool_name,
                        arguments=arguments,
                        id=item.get("call_id"),
                    )
                )
        return tool_calls

    # for openai completion api, the tool_calls are in the response text
    if isinstance(llm_response_content_text, list):
        tool_calls = []
        for tool_call in llm_response_content_text:
            name = tool_call.function.name
            if "-" in name:
                server_name, tool_name = name.rsplit("-", maxsplit=1)
            else:
                server_name = "unknown"
                tool_name = name
            arguments_str = tool_call.function.arguments

            # Parse JSON string to dictionary
            try:
                # Try to handle possible newlines and escape characters
                arguments = json.loads(arguments_str)
            except json.JSONDecodeError:
                logger.info(
                    f"Warning: Unable to parse tool arguments JSON: {arguments_str}"
                )
                # Try more lenient parsing or log error
                try:
                    # Try to replace some common error formats, such as Python dict strings
                    arguments_str_fixed = (
                        arguments_str.replace("'", '"')
                        .replace("None", "null")
                        .replace("True", "true")
                        .replace("False", "false")
                    )
                    arguments = json.loads(arguments_str_fixed)
                    logger.info(
                        "Info: Successfully parsed arguments after attempting to fix."
                    )
                except json.JSONDecodeError:
                    logger.info(
                        f"Error: Still unable to parse tool arguments JSON after fixing: {arguments_str}"
                    )
                    arguments = {
                        "error": "Failed to parse arguments",
                        "raw": arguments_str,
                    }

            arguments = filter_none_values(arguments)
            tool_calls.append(
                dict(
                    server_name=server_name,
                    tool_name=tool_name,
                    arguments=arguments,
                    id=tool_call.id,
                )
            )
        return tool_calls

    # for other clients, such as qwen and anthropic, we use MCP instead of tool calls
    tool_calls = []
    # Find all <use_mcp_tool> tags
    tool_call_patterns = re.findall(
        r"<use_mcp_tool>\s*<server_name>(.*?)</server_name>\s*<tool_name>(.*?)</tool_name>\s*<arguments>\s*([\s\S]*?)\s*</arguments>\s*</use_mcp_tool>",
        llm_response_content_text,
        re.DOTALL,
    )

    for match in tool_call_patterns:
        server_name = match[0].strip()
        tool_name = match[1].strip()
        arguments_str = match[2].strip()

        # Parse JSON string to dictionary
        arguments = safe_json_loads(arguments_str)
        arguments = filter_none_values(arguments)

        tool_calls.append(
            {
                "server_name": server_name,
                "tool_name": tool_name,
                "arguments": arguments,
                "id": None,
            }
        )

    return tool_calls
