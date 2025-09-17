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

import argparse
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from eval_utils import verify_answer_by_llm


def validate_answer(
    predicted_answer: str, ground_truth: str, question: str = ""
) -> bool:
    """
    Validate answer using LLM as judge with fallback to string matching.
    """
    if not predicted_answer or not ground_truth:
        return False

    # Try LLM evaluation
    result = verify_answer_by_llm(question, ground_truth, predicted_answer)
    print(f"    LLM Judge: {result}")
    return result == "CORRECT"


def load_metadata(metadata_path: str) -> Dict[str, Dict]:
    """Load ground truth metadata from JSONL file."""
    metadata = {}
    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    data = json.loads(line)
                    task_id = data.get("task_id")
                    if task_id:
                        # Only handle original GAIA format
                        ground_truth = data.get("Final answer", "")
                        question = data.get("Question", "")
                        file_name = data.get("file_name", "")

                        metadata[task_id] = {
                            "task_id": task_id,
                            "ground_truth": ground_truth,
                            "question": question,
                            "file_path": file_name,
                            "raw_data": data,
                        }
        print(f"Loaded metadata for {len(metadata)} tasks from {metadata_path}")
        return metadata
    except FileNotFoundError:
        print(f"Error: Metadata file not found at {metadata_path}")
        return {}
    except Exception as e:
        print(f"Error loading metadata: {e}")
        return {}


def process_log_file(log_path: str) -> Optional[Dict]:
    """Process a single log file and extract relevant information."""
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            log_data = json.load(f)

        # Extract key information
        task_id = log_data.get("task_id")
        status = log_data.get("status")
        final_boxed_answer = log_data.get("final_boxed_answer", "")

        if not task_id:
            print(f"Warning: No task_id found in {log_path}")
            return None

        return {
            "task_id": task_id,
            "status": status,
            "final_boxed_answer": final_boxed_answer,
            "log_file": log_path,
            "log_data": log_data,
        }

    except Exception as e:
        print(f"Error processing log file {log_path}: {e}")
        return None


def collect_and_validate_traces(
    logs_dir: str, metadata_path: str
) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """
    Go through logs, validate with metadata, and categorize results.

    Returns:
        - correct_traces: List of traces with correct answers
        - incorrect_traces: List of traces with incorrect answers
        - failed_traces: List of traces that failed to process
    """

    # Load metadata
    metadata = load_metadata(metadata_path)
    if not metadata:
        print("No metadata loaded, cannot validate answers")
        return [], [], []

    # Get all log files
    logs_path = Path(logs_dir)
    if not logs_path.exists():
        print(f"Error: Logs directory not found at {logs_dir}")
        return [], [], []

    log_files = list(logs_path.glob("*.json"))
    print(f"Found {len(log_files)} log files in {logs_dir}")

    correct_traces = []
    incorrect_traces = []
    failed_traces = []

    for log_file in log_files:
        print(f"\nProcessing: {log_file.name}")

        # Process log file
        log_info = process_log_file(str(log_file))
        if not log_info:
            failed_traces.append(
                {"log_file": str(log_file), "error": "Failed to process log file"}
            )
            continue

        task_id = log_info["task_id"]

        # Check if we have ground truth for this task
        if task_id not in metadata:
            print(f"  Warning: No ground truth found for task {task_id}")
            failed_traces.append(
                {
                    "log_file": str(log_file),
                    "task_id": task_id,
                    "error": "No ground truth available",
                }
            )
            continue

        ground_truth = metadata[task_id]["ground_truth"]
        predicted_answer = log_info["final_boxed_answer"]
        question = metadata[task_id]["question"]

        print(f"  Task ID: {task_id}")
        print(f"  Status: {log_info['status']}")
        print(
            f"  Question: {question[:100]}..."
            if len(question) > 100
            else f"  Question: {question}"
        )
        print(f"  Predicted: '{predicted_answer}'")
        print(f"  Ground Truth: '{ground_truth}'")

        # Validate answer
        is_correct = validate_answer(predicted_answer, ground_truth, question)

        # Add validation info to log_infou
        log_info["ground_truth"] = ground_truth
        log_info["question"] = question
        log_info["is_correct"] = is_correct
        log_info["metadata"] = metadata[task_id]

        if is_correct:
            print("  ✓ CORRECT")
            correct_traces.append(log_info)
        else:
            print("  ✗ INCORRECT")
            incorrect_traces.append(log_info)

    return correct_traces


def analyze_success_patterns(correct_traces: List[Dict]):
    """Analyze patterns in successful traces."""
    if not correct_traces:
        print("No correct traces to analyze")
        return

    print("\n=== SUCCESS PATTERN ANALYSIS ===")

    # Analyze by difficulty level
    levels = {}
    for trace in correct_traces:
        metadata = trace["metadata"].get("raw_data", {})
        level = metadata.get("Level", "Unknown")
        if level not in levels:
            levels[level] = 0
        levels[level] += 1

    print("Success by difficulty level:")
    for level, count in sorted(levels.items()):
        print(f"  Level {level}: {count} tasks")

    # Analyze tool usage patterns
    tool_usage = {}
    for trace in correct_traces:
        log_data = trace["log_data"]
        if "main_agent_turns" in log_data:
            task_tools = set()
            for turn in log_data["main_agent_turns"]:
                if "tool_calls" in turn:
                    for tool_call in turn["tool_calls"]:
                        tool_name = (
                            f"{tool_call['server_name']}/{tool_call['tool_name']}"
                        )
                        task_tools.add(tool_name)

            for tool in task_tools:
                if tool not in tool_usage:
                    tool_usage[tool] = 0
                tool_usage[tool] += 1

    print("\nTool usage in successful tasks:")
    for tool, count in sorted(tool_usage.items(), key=lambda x: x[1], reverse=True):
        print(f"  {tool}: {count} tasks")

    # Analyze execution time patterns
    times = []
    for trace in correct_traces:
        metadata = trace["metadata"].get("raw_data", {})
        annotator_meta = metadata.get("Annotator Metadata", {})
        time_taken = annotator_meta.get("How long did this take?", "")
        if "minute" in time_taken.lower():
            try:
                # Extract minutes
                import re

                minutes = re.findall(r"(\d+)", time_taken)
                if minutes:
                    times.append(int(minutes[0]))
            except Exception as e:
                print(f"Error extracting time from {time_taken}: {e}")
                pass

    if times:
        avg_time = sum(times) / len(times)
        print(f"\nAverage completion time: {avg_time:.1f} minutes")
        print(f"Time range: {min(times)} - {max(times)} minutes")


def proceed_with_next_step(correct_traces: List[Dict]):
    """Process correct traces for the next step."""
    if not correct_traces:
        print("No correct traces to process for next step")
        return

    print("\n=== PROCEEDING WITH NEXT STEP ===")
    print(f"Processing {len(correct_traces)} correct traces...")

    # Analyze success patterns
    analyze_success_patterns(correct_traces)

    # Example next steps - customize based on your needs
    print("\n=== NEXT STEP PROCESSING ===")
    for trace in correct_traces:
        task_id = trace["task_id"]
        print(f"\nNext step for task {task_id}:")
        print(f"  - Status: {trace['status']}")
        print("  - Answer validated: ✓")
        print(f"  - Log file: {trace['log_file']}")

        # Extract difficulty level
        metadata = trace["metadata"].get("raw_data", {})
        if "Level" in metadata:
            print(f"  - Difficulty level: {metadata['Level']}")

        # Extract and analyze reasoning steps
        annotator_meta = metadata.get("Annotator Metadata", {})
        if "Steps" in annotator_meta:
            steps = annotator_meta["Steps"]
            step_count = len(steps.split("\n")) if isinstance(steps, str) else 0
            print(f"  - Expected steps: {step_count}")

        # Extract tool usage patterns from log
        log_data = trace["log_data"]
        if "main_agent_turns" in log_data:
            tool_calls = []
            for turn in log_data["main_agent_turns"]:
                if "tool_calls" in turn:
                    for tool_call in turn["tool_calls"]:
                        tool_calls.append(
                            {
                                "server": tool_call["server_name"],
                                "tool": tool_call["tool_name"],
                            }
                        )

            if tool_calls:
                unique_tools = list(
                    set([f"{t['server']}/{t['tool']}" for t in tool_calls])
                )
                print(f"  - Tools used: {', '.join(unique_tools)}")
                print(f"  - Total tool calls: {len(tool_calls)}")

        print("  - Ready for next processing step")


def convert_trace_to_sft_data(file_path):
    """Convert trace to SFT data.

    Args:
        file_path: Path to the trace file to convert

    Returns:
        The loaded trace data
    """
    with open(file_path, "r") as f:
        data = json.load(f)

    main_agent_turns = data["main_agent_turns"]

    main_agent_messages = []
    for turn in main_agent_turns:
        if main_agent_messages == []:
            main_agent_messages.append(
                {"role": "system", "content": turn["system_prompt"]}
            )

        main_agent_messages.append({"role": "user", "content": turn["user_input"]})
        main_agent_messages.append(
            {"role": "assistant", "content": turn["assistant_response"]}
        )

    browser_agent_messages_groups = []
    for browser_agent_id, browser_agent_turns in data["browser_agent_sessions"].items():
        browser_agent_messages = []
        for turn in browser_agent_turns:
            if browser_agent_messages == []:
                browser_agent_messages.append(
                    {"role": "system", "content": turn["system_prompt"]}
                )
            browser_agent_messages.append(
                {"role": "user", "content": turn["user_input"]}
            )
            browser_agent_messages.append(
                {"role": "assistant", "content": turn["assistant_response"]}
            )
        browser_agent_messages_groups.append({"messages": browser_agent_messages})

    return main_agent_messages, browser_agent_messages_groups


def main():
    """Main function to collect traces and validate."""
    parser = argparse.ArgumentParser(description="Collect and validate trace logs.")
    parser.add_argument(
        "--logs_dir",
        type=str,
        default="../../logs",
        help="Directory containing the log files.",
    )
    parser.add_argument(
        "--metadata_path",
        type=str,
        default="../../data/gaia-2023-validation/metadata.jsonl",
        help="Path to the metadata JSONL file.",
    )
    args = parser.parse_args()

    print("=== Collect Trace Validation ===")

    logs_dir = args.logs_dir
    metadata_path = args.metadata_path

    print(f"Logs directory: {logs_dir}")
    print(f"Metadata file: {metadata_path}")

    # Collect and validate traces using synchronous method
    correct_traces = collect_and_validate_traces(logs_dir, metadata_path)

    correct_trace_paths = [trace["log_file"] for trace in correct_traces]

    all_main_agent_messages = []
    all_browser_agent_messages_groups = []
    for file_path in correct_trace_paths:
        main_agent_messages, browser_agent_messages_groups = convert_trace_to_sft_data(
            file_path
        )
        all_main_agent_messages.append({"messages": main_agent_messages})
        all_browser_agent_messages_groups.extend(browser_agent_messages_groups)

    # Save the collected messages to a file
    os.makedirs("logs", exist_ok=True)
    output_file = "logs/main_agent_messages.json"
    print(f"\nSaving {len(all_main_agent_messages)} messages to {output_file}")
    with open(output_file, "w") as f:
        json.dump(all_main_agent_messages, f, indent=2)

    output_file = "logs/browser_agent_messages.json"
    print(
        f"\nSaving {len(all_browser_agent_messages_groups)} messages to {output_file}"
    )
    with open(output_file, "w") as f:
        json.dump(all_browser_agent_messages_groups, f, indent=2)


if __name__ == "__main__":
    main()
