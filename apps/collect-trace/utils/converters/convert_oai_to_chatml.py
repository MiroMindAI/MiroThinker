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
import sys
import os
from pathlib import Path
from copy import deepcopy
from typing import Dict, Any
from datetime import datetime
import ast

from system_prompts import (
    main_system_prompt_foreword,
    sub_agent_system_prompt_foreword,
    system_prompt_tool_instrcutions,
)

# Initialize creation_time_str with current time
creation_time_str = datetime.now().strftime("%Y-%m-%d")


def oai_tool_message_to_chat_message(oai_messages, agent_type, tool_definition):
    def convert_oai_tool_call_to_mcp_tool_call_str(oai_tool_call):
        if isinstance(oai_tool_call, list):
            assert len(oai_tool_call) >= 1
        if isinstance(oai_tool_call, str):
            oai_tool_call = [json.loads(oai_tool_call)]

        mcp_tool_call_templates = []
        for each_oai_tool_call in oai_tool_call:
            assert isinstance(
                each_oai_tool_call, dict
            ), f"oai_tool_call should be a dict, but got {type(each_oai_tool_call)}"

            server_name, tool_name = each_oai_tool_call["function"]["name"].rsplit(
                "-", maxsplit=1
            )
            arguments = json.loads(each_oai_tool_call["function"]["arguments"])
            mcp_tool_call_template = f"<use_mcp_tool>\n<server_name>{server_name}</server_name>\n<tool_name>{tool_name}</tool_name>\n<arguments>\n{json.dumps(arguments)}\n</arguments>\n</use_mcp_tool>"
            mcp_tool_call_templates.append(mcp_tool_call_template)

        return "\n\n".join(mcp_tool_call_templates)

    def safe_get_text(content):
        """Safely extract text content, handling different content formats"""
        if isinstance(content, list) and content:
            if isinstance(content[0], dict) and "text" in content[0]:
                return content[0]["text"]
            elif isinstance(content[0], str):
                return content[0]
            else:
                return str(content[0])
        elif isinstance(content, str):
            return content
        elif content is None:
            return ""
        else:
            return str(content)

    def generate_mcp_servers_str(tool_definition):
        mcp_servers_str = ""
        if tool_definition and len(tool_definition) > 0:
            for server in tool_definition:
                mcp_servers_str += f"## Server name: {server['name']}\n"
                if "tools" in server and len(server["tools"]) > 0:
                    for tool in server["tools"]:
                        # Skip tools that failed to load (they only have 'error' key)
                        if "error" in tool and "name" not in tool:
                            continue
                        mcp_servers_str += f"### Tool name: {tool['name']}\n"
                        mcp_servers_str += f"Description: {tool['description']}\n"
                        mcp_servers_str += f"Input JSON schema: {tool['schema']}\n"
        return mcp_servers_str

    oai_messages = deepcopy(oai_messages)
    chat_messages = []
    idx = 0
    pending_user_tool_contents = []

    # Merge pending_user_tool_contents into a single user message and add to chat_messages
    def flush_pending(pending_user_tool_contents, chat_messages):
        if pending_user_tool_contents:
            combined_content = "\n\n".join(pending_user_tool_contents)
            chat_messages.append(
                {
                    "role": "user",
                    "content": combined_content,
                }
            )
        return []  # Always return a new empty list

    try:
        for idx, msg in enumerate(oai_messages):
            if msg["role"] in ["developer", "system"]:
                assert idx == 0, "System messages should be the first message"

                time_str = f" Today is: {creation_time_str}\n"
                tool_definition_str = generate_mcp_servers_str(tool_definition)
                ori_system_prompt = msg["content"][0]["text"]

                system_prompt_after_general_objective = ori_system_prompt[
                    ori_system_prompt.find("# General Objective") :
                ]

                if agent_type == "main":
                    system_prompt = (
                        main_system_prompt_foreword
                        + time_str
                        + system_prompt_tool_instrcutions
                        + tool_definition_str
                        + system_prompt_after_general_objective
                    )
                elif agent_type == "sub_agent":
                    system_prompt = (
                        sub_agent_system_prompt_foreword
                        + time_str
                        + system_prompt_tool_instrcutions
                        + tool_definition_str
                        + system_prompt_after_general_objective
                    )
                else:
                    raise ValueError(f"Unknown agent type: {agent_type}")

                chat_messages.append(
                    {
                        "role": "system",
                        "content": system_prompt,
                    }
                )

            elif msg["role"] in ["user", "tool"]:
                content = safe_get_text(msg["content"])
                pending_user_tool_contents.append(content)
            elif msg["role"] == "assistant" and "tool_calls" in msg:
                # Flush pending user/tool messages
                pending_user_tool_contents = flush_pending(
                    pending_user_tool_contents, chat_messages
                )

                content = safe_get_text(msg.get("content", ""))

                if content != "":
                    content += "\n\n"  # Concatenate thinking text with tool call

                chat_messages.append(
                    {
                        "role": "assistant",
                        "content": content
                        + convert_oai_tool_call_to_mcp_tool_call_str(msg["tool_calls"]),
                    }
                )
            elif msg["role"] == "assistant" and "tool_calls" not in msg:
                # Flush pending user/tool messages
                pending_user_tool_contents = flush_pending(
                    pending_user_tool_contents, chat_messages
                )

                content = safe_get_text(msg["content"])

                chat_messages.append(
                    {
                        "role": "assistant",
                        "content": content,
                    }
                )
            else:
                raise ValueError(f"Unknown role: {msg['role']}")

        assert (
            len(pending_user_tool_contents) == 0
        ), "Error: Trace ends with user/tool round. Pending user/tool contents should be empty."

    except Exception as e:
        raise ValueError(f"Error processing messages: {e}")

    return chat_messages


def extract_message_history_from_log(
    log_data: Dict[str, Any],
):
    """
    Extract message history from log data and convert to OpenAI ChatML format

    Args:
        log_data: Log data dictionary

    Returns:
        Dictionary containing main_agent and sub_agents message history
    """
    result = {"main_agent": [], "sub_agents": {}}

    # Extract main_agent_message_history
    main_agent_history = log_data.get("main_agent_message_history", {})
    if main_agent_history and "message_history" in main_agent_history:
        main_messages = main_agent_history["message_history"]
        if main_messages:
            tool_main_agent_definition = extract_step_message(
                log_data, "get_main_tool_definitions"
            )

            result["main_agent"] = oai_tool_message_to_chat_message(
                main_messages,
                "main",
                tool_main_agent_definition,
            )

    # Extract sub_agent_message_history_sessions
    sub_agent_sessions = log_data.get("sub_agent_message_history_sessions", {})
    if sub_agent_sessions:
        for session_name, session_data in sub_agent_sessions.items():
            if "message_history" in session_data:
                sub_agent_messages = session_data["message_history"]
                if sub_agent_messages:
                    sub_agent_type = session_name.split("_")[0]

                    tool_sub_agent_definition = extract_step_message(
                        log_data, f"get_sub_{sub_agent_type}_tool_definitions"
                    )
                    result["sub_agents"][session_name] = (
                        oai_tool_message_to_chat_message(
                            sub_agent_messages, "sub_agent", tool_sub_agent_definition
                        )
                    )

    return result


def save_chatml_to_files(
    chatml_data: Dict[str, Any],
    output_dir: Path,
    input_filename: str,
):
    """
    Save ChatML format messages to files

    Args:
        chatml_data: Dictionary containing message history
        output_dir: Output directory
        input_filename: Input filename (without extension)
    """
    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save main agent messages
    if chatml_data["main_agent"]:
        main_output_file = output_dir / f"{input_filename}_main_agent_chatml.json"
        with open(main_output_file, "w", encoding="utf-8") as f:
            json.dump(chatml_data["main_agent"], f, ensure_ascii=False, indent=2)
        print(f"✓ Saved main agent ChatML: {main_output_file}")

    # Save sub agent messages
    for session_name, messages in chatml_data["sub_agents"].items():
        # Extract numeric suffix

        sub_agent_output_file = (
            output_dir / f"{input_filename}_{session_name}_chatml.json"
        )

        with open(sub_agent_output_file, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)
        print(f"✓ Saved sub agent {session_name} ChatML: {sub_agent_output_file}")


def extract_step_message(data, target_step_name):
    try:
        # Check if step_logs field exists
        if "step_logs" not in data:
            print("step_logs field not found in log file")
            return None

        # Iterate through step_logs to find target step_name
        for i, step in enumerate(data["step_logs"]):
            step_name = step.get("step_name")
            if step_name == target_step_name:
                message = step.get("message")
                return ast.literal_eval(message)

        print(f"No record found with step_name '{target_step_name}'")
        return None

    except Exception as e:
        print(f"Error processing file: {e}")
        return None


def process_log_file(log_file_path: str, output_dir: str = "extracted_chatml"):
    """
    Process a single log file, extract message history and convert to ChatML format

    Args:
        log_file_path: Log file path
        output_dir: Output directory
    """
    log_path = Path(log_file_path)
    output_path = Path(output_dir)

    if not log_path.exists():
        print(f"Error: Log file does not exist: {log_file_path}")
        return

    # Get file creation time
    global creation_time_str
    try:
        stat_info = os.stat(log_path)
        creation_time = datetime.fromtimestamp(stat_info.st_ctime)
        creation_time_str = creation_time.strftime("%Y-%m-%d")
        print(f"File creation time: {creation_time_str}")
    except Exception as e:
        print(f"Warning: Could not get file creation time: {e}")

    try:
        # Read log file
        print(f"Reading log file: {log_path}")
        with open(log_path, "r", encoding="utf-8") as f:
            log_data = json.load(f)

        # Extract input filename (without extension)
        input_filename = log_path.stem

        # Extract message history and convert to ChatML format
        print("Extracting message history...")
        chatml_data = extract_message_history_from_log(log_data)

        # Save to files
        print(f"Saving ChatML files to: {output_path}")
        save_chatml_to_files(chatml_data, output_path, input_filename)

        print("\n✓ Processing completed!")
        print(f"Output directory: {output_path.absolute()}")

    except json.JSONDecodeError as e:
        print(f"Error: Cannot parse JSON file: {e}")
    except Exception as e:
        print(f"Error: {e}")


def main():
    """Main function"""
    if len(sys.argv) < 2:
        print("Usage: python convert_oai_to_chatml.py <log_file_path> [output_dir]")
        print("Example: python convert_oai_to_chatml.py logs/debug_logs/task_1.json")
        print(
            "Example: python convert_oai_to_chatml.py logs/debug_logs/task_1.json ./extracted_chatml"
        )
        sys.exit(1)

    log_file_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "extracted_chatml"

    process_log_file(log_file_path, output_dir)


if __name__ == "__main__":
    main()
