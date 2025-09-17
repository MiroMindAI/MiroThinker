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
import os
import sys
import tempfile
from pathlib import Path

# Add parent directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from utils.converters import (
    extract_and_save_chat_history,
    extract_message_history_from_log,
)


def example_1_basic_conversion():
    """Example 1: Basic conversion using Python API"""
    print("=== Example 1: Basic Conversion ===")

    # Sample log data
    log_data = {
        "main_agent_message_history": {
            "system_prompt": "You are a helpful assistant.",
            "message_history": [
                {
                    "role": "developer",
                    "content": [
                        {"type": "text", "text": "You are a helpful assistant."}
                    ],
                },
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "Hello, how are you?"}],
                },
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "I'm doing well, thank you!"}],
                },
            ],
        },
        "browser_agent_message_history_sessions": {
            "browser_agent_1": {
                "system_prompt": "You are a browsing agent.",
                "message_history": [
                    {
                        "role": "developer",
                        "content": [
                            {"type": "text", "text": "You are a browsing agent."}
                        ],
                    },
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": "Search for something"}],
                    },
                    {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "I found it."}],
                    },
                ],
            }
        },
        "env_info": {"llm_provider": "openai"},
    }

    # Convert using OAI method
    chatml_data = extract_message_history_from_log(log_data)
    print(
        f"OAI conversion result: {len(chatml_data['main_agent'])} messages in main agent"
    )
    print(
        f"OAI conversion result: {len(chatml_data['browser_agents']['browser_agent_1'])} messages in browser agent"
    )

    # Convert using Non-OAI method
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        extract_and_save_chat_history(log_data, temp_path, "example")

        # Check generated files
        main_file = temp_path / "example_main_agent_chatml.json"
        browser_file = temp_path / "example_browser_agent_1_chatml.json"

        if main_file.exists():
            with open(main_file, "r") as f:
                main_content = json.load(f)
                print(
                    f"Non-OAI conversion result: {len(main_content)} messages in main agent"
                )

        if browser_file.exists():
            with open(browser_file, "r") as f:
                browser_content = json.load(f)
                print(
                    f"Non-OAI conversion result: {len(browser_content)} messages in browser agent"
                )


if __name__ == "__main__":
    print("ChatML Conversion Utilities - Usage Examples")
    print("=" * 50)

    example_1_basic_conversion()

    print("\n" + "=" * 50)
    print("Examples completed successfully!")
    print("\nFor more information, see the README.md file.")
