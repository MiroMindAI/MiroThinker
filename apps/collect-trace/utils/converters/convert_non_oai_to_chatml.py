# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

import json
import sys
from pathlib import Path
from typing import Any, Dict, List


def convert_to_json_chatml(messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    Convert message list to OpenAI JSON format ChatML
    Filter out messages with role 'tool', convert content None to empty string
    """
    chatml_list = []
    for message in messages:
        role = message.get("role", "")
        if role == "tool":
            continue  # Skip tool messages
        if role == "system":
            continue  # Skip system messages
        content = message.get("content", "")
        if content is None:
            content = ""
        # Handle different content formats
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
            content = " ".join(text_parts)
        elif isinstance(content, str):
            pass
        else:
            content = str(content)
        chatml_list.append({"role": role, "content": content})
    return chatml_list


def extract_and_save_chat_history(
    log_data: Dict[str, Any], output_dir: Path, input_filename: str
):
    """
    Extract message history from log data and save as ChatML format

    Args:
        log_data: Log data dictionary
        output_dir: Output directory
        input_filename: Input filename (without extension)
    """
    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Extract main_agent_message_history
    main_agent_history = log_data.get("main_agent_message_history", {})
    if main_agent_history and "message_history" in main_agent_history:
        main_messages = main_agent_history["message_history"]
        if main_messages:
            chatml_list = convert_to_json_chatml(main_messages)
            chatml_list.insert(
                0,
                {
                    "role": "system",
                    "content": main_agent_history.get("system_prompt", ""),
                },
            )
            # Save main agent chat records
            main_output_file = output_dir / f"{input_filename}_main_agent_chatml.json"
            with open(main_output_file, "w", encoding="utf-8") as f:
                json.dump(chatml_list, f, ensure_ascii=False, indent=2)

            print(f"✓ Saved main agent chat records: {main_output_file}")

    # 2. Extract sub_agent_message_history_sessions
    sub_agent_sessions = log_data.get("sub_agent_message_history_sessions", {})
    if sub_agent_sessions:
        for session_name, session_data in sub_agent_sessions.items():
            if "message_history" in session_data:
                sub_agent_messages = session_data["message_history"]
                if sub_agent_messages:
                    chatml_list = convert_to_json_chatml(sub_agent_messages)
                    chatml_list.insert(
                        0,
                        {
                            "role": "system",
                            "content": session_data.get("system_prompt", ""),
                        },
                    )

                    # Save browser agent chat records
                    sub_agent_output_file = (
                        output_dir / f"{input_filename}_{session_name}_chatml.json"
                    )
                    with open(sub_agent_output_file, "w", encoding="utf-8") as f:
                        json.dump(chatml_list, f, ensure_ascii=False, indent=2)

                    print(f"✓ Saved sub agent chat records: {sub_agent_output_file}")


def main():
    """Main function"""
    if len(sys.argv) < 2:
        print("Usage: python convert_non_oai_to_chatml.py <log_file_path> [output_dir]")
        print(
            "Example: python convert_non_oai_to_chatml.py logs/debug_logs/task_1.json"
        )
        print(
            "Example: python convert_non_oai_to_chatml.py logs/debug_logs/task_1.json ./extracted_chats"
        )
        sys.exit(1)

    log_file_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("extracted_chats")

    # Check if input file exists
    if not log_file_path.exists():
        print(f"Error: Log file does not exist: {log_file_path}")
        sys.exit(1)

    try:
        # Read log file
        print(f"Reading log file: {log_file_path}")
        with open(log_file_path, "r", encoding="utf-8") as f:
            log_data = json.load(f)

        # Extract input filename (without extension)
        input_filename = log_file_path.stem

        # Extract and save chat history
        print(f"Extracting chat history to: {output_dir}")
        extract_and_save_chat_history(log_data, output_dir, input_filename)

        print("\n✓ Chat history extraction completed!")
        print(f"Output directory: {output_dir.absolute()}")

    except json.JSONDecodeError as e:
        print(f"Error: Cannot parse JSON file: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
