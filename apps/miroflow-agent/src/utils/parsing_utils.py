# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

import json
import logging
import re

from json_repair import repair_json

logger = logging.getLogger("miroflow_agent")


def filter_none_values(arguments: dict) -> dict:
    """
    Filter out keys with None values from arguments dictionary.
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


def safe_json_loads(arguments_str: str) -> dict:
    """
    Safely parse a JSON string with multiple fallbacks:
    1. Try standard json.loads()
    2. If it fails, try json_repair
    3. If all attempts fail, return an error object
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


def extract_llm_response_text(llm_response):
    """
    Extract text from LLM response, excluding <use_mcp_tool> tags. Stop immediately when this opening tag is encountered.
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


def parse_llm_response_for_tool_calls(llm_response_content_text):
    """
    Parse tool_calls or <use_mcp_tool> tags from LLM response text.
    Returns a list containing tool call information.
    """
    # tool_calls or MCP reponse are handled differently
    # for openai response api, the tool_calls are in the response text
    if isinstance(llm_response_content_text, dict):
        tool_calls = []
        for item in llm_response_content_text.get("output", None):
            if item.get("type") == "function_call":
                server_name, tool_name = item.get("name").rsplit("-", maxsplit=1)
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
            server_name, tool_name = tool_call.function.name.rsplit("-", maxsplit=1)
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
