# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

import argparse
import json
import os
import shutil


def get_successful_log_paths(jsonl_file_path: str) -> list:
    """
    Collects the paths of successful log files from a dataset.

    This function extracts log file paths of successful records based on
    the value of `final_judge_result`. If the dataset has been fully
    processed, it reads from a `benchmark_results.jsonl` file. Otherwise,
    if processing was interrupted, it falls back to scanning individual
    `.json` files in the given directory.

    Success is determined by:
    - `PASS_AT_K_SUCCESS` for records in JSONL files.
    - `CORRECT` for records in individual JSON files.

    Args:
        jsonl_file_path (str): Path to a JSONL file or a directory of JSON files.

    Returns:
        list: A list of log file paths for successful records.
    """
    log_paths = []

    if jsonl_file_path.endswith(".jsonl"):
        with open(jsonl_file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        if data.get("final_judge_result") == "PASS_AT_K_SUCCESS":
                            log_path = data.get("log_file_path")
                            if log_path:
                                log_paths.append(log_path)
                    except json.JSONDecodeError:
                        continue
    else:
        filenames = os.listdir(jsonl_file_path)
        filenames = [filename for filename in filenames if filename.endswith(".json")]
        for filename in filenames:
            filepath = os.path.join(jsonl_file_path, filename)
            try:
                data = json.load(open(filepath, "r"))
            except Exception:
                continue
            try:
                final_judge_result = data["final_judge_result"]
            except KeyError:
                print(data.keys())
                continue
            if final_judge_result == "CORRECT":
                log_paths.append(filepath)

    return log_paths


# Usage example
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract successful log paths from JSONL file"
    )
    parser.add_argument(
        "file_path", help="Path to the JSONL file containing benchmark results"
    )
    args = parser.parse_args()

    result = get_successful_log_paths(args.file_path)

    # Get the parent directory of args.file_path
    parent_dir = os.path.abspath(os.path.dirname(args.file_path))

    # Create successful logs directory
    success_log_dir = parent_dir + "/successful_logs"
    success_chatml_log_dir = parent_dir + "/successful_chatml_logs"
    os.makedirs(success_log_dir, exist_ok=True)
    print(f"Successful logs directory: {success_log_dir}")

    for i, path in enumerate(result, 1):
        basename = os.path.basename(path)
        print(f"Copying file: {path} to {success_log_dir}/{basename}")
        shutil.copy(path, f"{success_log_dir}/{basename}")

    os.system(
        f"uv run utils/converters/convert_to_chatml_auto_batch.py {success_log_dir}/*.json -o {success_chatml_log_dir}"
    )
    os.system(
        f"uv run utils/merge_chatml_msgs_to_one_json.py --input_dir {success_chatml_log_dir}"
    )
