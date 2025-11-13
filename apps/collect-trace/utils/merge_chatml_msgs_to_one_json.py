# Copyright (c) 2025 Miromind.ai
# This source code is licensed under the MIT License.

import argparse
import glob
import json
import os


def merge_json_files(input_dir, type="main"):
    # List to store all messages
    all_conversations = []

    # Get all JSON files matching the pattern
    json_files = glob.glob(os.path.join(input_dir, f"*{type}*.json"))

    # Read each JSON file and merge its content
    for json_file in json_files:
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                conversation = {
                    "messages": data,
                }
                all_conversations.append(conversation)
            print(f"Successfully processed: {json_file}")
        except Exception as e:
            print(f"Error processing {json_file}: {str(e)}")

    output_file = os.path.join(input_dir, f"{type}_merged.json")
    # Write the merged data to a new JSON file
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_conversations, f, ensure_ascii=False, indent=2)

    print(
        f"\nMerging complete! All {type} JSON files have been merged into {output_file}"
    )
    print(f"Total number of files processed: {len(json_files)}")
    print(f"Total number of messages: {len(all_conversations)}")


def main():
    parser = argparse.ArgumentParser(
        description="Merge multiple JSON files which contain chat messages into a single file"
    )
    parser.add_argument(
        "--input_dir",
        type=str,
        required=True,
        help="File pattern with wildcards to match JSON files (e.g., '*.json' or 'data/*main*.json')",
    )

    args = parser.parse_args()

    merge_json_files(args.input_dir, type="main_agent")
    merge_json_files(args.input_dir, type="agent-browsing")


if __name__ == "__main__":
    main()
