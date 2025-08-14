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

import json
import logging
import re

logger = logging.getLogger("miroflow_agent")


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
        return content[:match.start()].strip()
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
                try:
                    # Try to handle possible newlines and escape characters
                    arguments = json.loads(arguments_str)
                except json.JSONDecodeError:
                    print(
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
                        print(
                            "Info: Successfully parsed arguments after attempting to fix."
                        )
                    except json.JSONDecodeError:
                        print(
                            f"Error: Still unable to parse tool arguments JSON after fixing: {arguments_str}"
                        )
                        arguments = {
                            "error": "Failed to parse arguments",
                            "raw": arguments_str,
                        }
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
                arguments = {"error": "Failed to parse arguments", "raw": arguments_str}

        tool_calls.append(
            {
                "server_name": server_name,
                "tool_name": tool_name,
                "arguments": arguments,
                "id": None,
            }
        )

    return tool_calls
