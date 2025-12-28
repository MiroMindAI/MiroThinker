# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

import argparse
import glob
import json
import os
from pathlib import Path

from common import ProgressChecker

# Benchmark configuration
FILENAME = os.path.basename(__file__)
BENCHMARK_NAME = "deepsearchqa"
BENCHMARK_NAME_STD = "DeepSearchQA"
TASKS_PER_RUN = 900
DATA_PATH = f"../../data/{BENCHMARK_NAME}/standardized_data.jsonl"
TASK_ID_PATTERN = r"task_([a-f0-9]+)"


def extract_eval_details_from_log(log_file: str) -> dict:
    """
    Extract evaluation details from a completed task log file.

    Returns:
        Dict with num_correct, num_expected, num_excessive, or empty dict if not found
    """
    try:
        with open(log_file, "r") as f:
            content = f.read()

        # Try to parse as JSON first (task log files are JSON)
        try:
            log_data = json.loads(content)

            # Method 1: Check for eval_details field (new format - saved directly)
            if "eval_details" in log_data and log_data["eval_details"]:
                eval_details = log_data["eval_details"]
                if all(
                    k in eval_details
                    for k in ["num_correct", "num_expected", "num_excessive"]
                ):
                    return {
                        "num_correct": eval_details["num_correct"],
                        "num_expected": eval_details["num_expected"],
                        "num_excessive": eval_details["num_excessive"],
                    }

            # Method 2: Check if llm_response contains the evaluation output (legacy format)
            if "llm_response" in log_data and log_data["llm_response"]:
                llm_response = log_data["llm_response"]

                # Look for DeepSearchQA Judge output
                if "DeepSearchQA Judge - Correct:" in llm_response:
                    for line in llm_response.split("\n"):
                        if "DeepSearchQA Judge - Correct:" in line:
                            # Parse "Correct: X/Y, Excessive: Z"
                            parts = line.split("Correct:")[1].strip()
                            correct_part, excessive_part = parts.split(", Excessive:")
                            num_correct, num_expected = map(
                                int, correct_part.split("/")
                            )
                            num_excessive = int(excessive_part.strip())

                            return {
                                "num_correct": num_correct,
                                "num_expected": num_expected,
                                "num_excessive": num_excessive,
                            }
        except json.JSONDecodeError:
            # Not JSON, try as plain text (legacy format)
            if "DeepSearchQA Judge - Correct:" in content:
                for line in content.split("\n"):
                    if "DeepSearchQA Judge - Correct:" in line:
                        # Parse "Correct: X/Y, Excessive: Z"
                        parts = line.split("Correct:")[1].strip()
                        correct_part, excessive_part = parts.split(", Excessive:")
                        num_correct, num_expected = map(int, correct_part.split("/"))
                        num_excessive = int(excessive_part.strip())

                        return {
                            "num_correct": num_correct,
                            "num_expected": num_expected,
                            "num_excessive": num_excessive,
                        }
    except Exception:
        pass

    return {}


def calculate_deepsearchqa_metrics_from_logs(base_path: str) -> dict:
    """
    Calculate metrics from individual task log files (for in-progress runs).

    Returns:
        Dict with metrics or None if no completed tasks found
    """
    try:
        # Find all completed task log files
        pattern = os.path.join(base_path, "run_*/task_*.json")
        log_files = glob.glob(pattern)

        if not log_files:
            return None

        num_valid = 0
        num_fully_correct = 0
        num_fully_incorrect = 0
        num_correct_with_extraneous = 0
        f1_list = []

        for log_file in log_files:
            details = extract_eval_details_from_log(log_file)
            if not details:
                continue

            num_correct = details["num_correct"]
            num_expected = details["num_expected"]
            num_excessive = details["num_excessive"]

            # Calculate per-item metrics
            true_positives = num_correct
            false_negatives = num_expected - num_correct
            false_positives = num_excessive

            # Calculate precision and recall for F1
            precision = 0.0
            if (true_positives + false_positives) > 0:
                precision = true_positives / (true_positives + false_positives)

            recall = 0.0
            if (true_positives + false_negatives) > 0:
                recall = true_positives / (true_positives + false_negatives)

            f1 = 0.0
            if (precision + recall) > 0:
                f1 = 2 * (precision * recall) / (precision + recall)

            f1_list.append(f1)

            # Classify into categories
            all_expected_correct = num_correct == num_expected
            has_extraneous = num_excessive > 0

            if all_expected_correct and not has_extraneous:
                num_fully_correct += 1
            elif num_correct == 0:
                num_fully_incorrect += 1
            elif all_expected_correct and has_extraneous:
                num_correct_with_extraneous += 1

            num_valid += 1

        if num_valid > 0:
            return {
                "num_valid": num_valid,
                "fully_correct": num_fully_correct,
                "fully_incorrect": num_fully_incorrect,
                "correct_with_extraneous": num_correct_with_extraneous,
                "pct_fully_correct": num_fully_correct / num_valid,
                "pct_fully_incorrect": num_fully_incorrect / num_valid,
                "pct_correct_with_extraneous": num_correct_with_extraneous / num_valid,
                "avg_f1": sum(f1_list) / len(f1_list),
            }

        return None

    except Exception:
        return None


def calculate_deepsearchqa_metrics(results_file: str) -> dict:
    """
    Calculate DeepSearchQA-specific metrics from results file.
    Following the official Google DeepSearchQA evaluation metrics:
    1. Fully Correct: All expected answers correct + no extraneous answers
    2. Fully Incorrect: No correct answers
    3. Correct with Extraneous Answers: All expected answers correct + has extraneous
    4. F1 Score: Harmonic mean of precision and recall

    Returns:
        Dict with the 4 core metrics
    """
    try:
        results = []
        with open(results_file, "r") as f:
            for line in f:
                if line.strip():
                    results.append(json.loads(line))

        num_valid = 0
        num_fully_correct = 0
        num_fully_incorrect = 0
        num_correct_with_extraneous = 0
        f1_list = []

        for result in results:
            if result.get("status") != "success":
                continue

            # Extract eval_details from attempts
            if "attempts" in result and result["attempts"]:
                for attempt in result["attempts"]:
                    if "eval_details" in attempt and attempt["eval_details"]:
                        details = attempt["eval_details"]
                        num_correct = details.get("num_correct", 0)
                        num_expected = details.get("num_expected", 0)
                        num_excessive = details.get("num_excessive", 0)

                        # Calculate per-item metrics
                        true_positives = num_correct
                        false_negatives = num_expected - num_correct
                        false_positives = num_excessive

                        # Calculate precision and recall for F1
                        precision = 0.0
                        if (true_positives + false_positives) > 0:
                            precision = true_positives / (
                                true_positives + false_positives
                            )

                        recall = 0.0
                        if (true_positives + false_negatives) > 0:
                            recall = true_positives / (true_positives + false_negatives)

                        f1 = 0.0
                        if (precision + recall) > 0:
                            f1 = 2 * (precision * recall) / (precision + recall)

                        f1_list.append(f1)

                        # Classify into categories
                        all_expected_correct = num_correct == num_expected
                        has_extraneous = num_excessive > 0

                        if all_expected_correct and not has_extraneous:
                            num_fully_correct += 1
                        elif num_correct == 0:
                            num_fully_incorrect += 1
                        elif all_expected_correct and has_extraneous:
                            num_correct_with_extraneous += 1

                        num_valid += 1
                        break  # Only use first attempt with details

        if num_valid > 0:
            return {
                "num_valid": num_valid,
                "fully_correct": num_fully_correct,
                "fully_incorrect": num_fully_incorrect,
                "correct_with_extraneous": num_correct_with_extraneous,
                "pct_fully_correct": num_fully_correct / num_valid,
                "pct_fully_incorrect": num_fully_incorrect / num_valid,
                "pct_correct_with_extraneous": num_correct_with_extraneous / num_valid,
                "avg_f1": sum(f1_list) / len(f1_list),
            }
        else:
            return {"num_valid": 0}

    except Exception as e:
        print(f"Warning: Could not calculate DeepSearchQA metrics: {e}")
        return {"num_valid": 0}


def show_deepsearchqa_metrics(base_path: str):
    """
    Show DeepSearchQA-specific metrics for all runs.
    Following Google DeepSearchQA official metrics:
    1. Fully Correct
    2. Fully Incorrect
    3. Correct with Extraneous Answers
    4. F1 Score
    """
    print("\n" + "=" * 80)
    print("DeepSearchQA Metrics (Official Google Metrics)")
    print("=" * 80)

    # Find all benchmark_results.jsonl files
    results_files = glob.glob(os.path.join(base_path, "run_*/benchmark_results.jsonl"))

    if not results_files:
        print("(Metrics will be available after tasks complete)")
        return

    all_fully_correct = []
    all_fully_incorrect = []
    all_correct_with_extraneous = []
    all_f1 = []

    for results_file in sorted(results_files):
        run_dir = Path(results_file).parent.name
        metrics = calculate_deepsearchqa_metrics(results_file)

        if metrics["num_valid"] > 0:
            fully_correct_pct = metrics["pct_fully_correct"]
            fully_incorrect_pct = metrics["pct_fully_incorrect"]
            correct_with_extraneous_pct = metrics["pct_correct_with_extraneous"]
            f1 = metrics["avg_f1"]

            all_fully_correct.append(fully_correct_pct)
            all_fully_incorrect.append(fully_incorrect_pct)
            all_correct_with_extraneous.append(correct_with_extraneous_pct)
            all_f1.append(f1)

            print(f"\n{run_dir} ({metrics['num_valid']} items):")
            print(
                f"  Fully Correct:              {fully_correct_pct:6.2%}  ({metrics['fully_correct']} items)"
            )
            print(
                f"  Fully Incorrect:            {fully_incorrect_pct:6.2%}  ({metrics['fully_incorrect']} items)"
            )
            print(
                f"  Correct w/ Extraneous:      {correct_with_extraneous_pct:6.2%}  ({metrics['correct_with_extraneous']} items)"
            )
            print(f"  F1 Score:                   {f1:6.2%}")

    if all_fully_correct:
        print("\n" + "=" * 80)
        print(f"Average across {len(all_fully_correct)} runs:")
        print("=" * 80)
        avg_fully_correct = sum(all_fully_correct) / len(all_fully_correct)
        avg_fully_incorrect = sum(all_fully_incorrect) / len(all_fully_incorrect)
        avg_correct_with_extraneous = sum(all_correct_with_extraneous) / len(
            all_correct_with_extraneous
        )
        avg_f1 = sum(all_f1) / len(all_f1)

        print(f"  Fully Correct:              {avg_fully_correct:6.2%}")
        print(f"  Fully Incorrect:            {avg_fully_incorrect:6.2%}")
        print(f"  Correct w/ Extraneous:      {avg_correct_with_extraneous:6.2%}")
        print(f"  F1 Score:                   {avg_f1:6.2%}")

    print("=" * 80)


def parse_args():
    parser = argparse.ArgumentParser(
        description=f"Check progress of {BENCHMARK_NAME_STD} benchmark runs."
    )
    parser.add_argument(
        "path", help=f"Path to {BENCHMARK_NAME_STD} benchmark directory"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    try:
        # Create progress checker and run analysis
        checker = ProgressChecker(
            args.path, task_per_run=TASKS_PER_RUN, data_path=DATA_PATH
        )
        summary = checker.run_analysis(
            benchmark_name_std=BENCHMARK_NAME_STD, task_id_pattern=TASK_ID_PATTERN
        )

        # Show DeepSearchQA-specific metrics (only if runs are complete)
        # Check if any run has completed all its tasks
        has_complete_run = False
        run_dirs = glob.glob(os.path.join(args.path, "run_*"))
        for run_dir in run_dirs:
            results_file = os.path.join(run_dir, "benchmark_results.jsonl")
            if os.path.exists(results_file):
                has_complete_run = True
                break

        if has_complete_run:
            show_deepsearchqa_metrics(args.path)
        elif summary.total_completed > 0:
            # Try to show intermediate metrics from completed tasks
            interim_metrics = calculate_deepsearchqa_metrics_from_logs(args.path)

            print("\n" + "=" * 80)
            print("DeepSearchQA Metrics (Official Google Metrics)")
            print("=" * 80)

            if interim_metrics and interim_metrics.get("num_valid", 0) > 0:
                num_with_details = interim_metrics["num_valid"]
                print(
                    f"⚠️  INTERIM RESULTS (based on {num_with_details}/{summary.total_completed} tasks with eval_details)"
                )
                if num_with_details < summary.total_completed:
                    print(
                        f"    Note: {summary.total_completed - num_with_details} completed tasks don't have eval_details (likely ran before the update)"
                    )
                print("-" * 80)

                fully_correct_pct = interim_metrics["pct_fully_correct"]
                fully_incorrect_pct = interim_metrics["pct_fully_incorrect"]
                correct_with_extraneous_pct = interim_metrics[
                    "pct_correct_with_extraneous"
                ]
                f1 = interim_metrics["avg_f1"]

                print(
                    f"  Fully Correct:              {fully_correct_pct:6.2%}  ({interim_metrics['fully_correct']} items)"
                )
                print(
                    f"  Fully Incorrect:            {fully_incorrect_pct:6.2%}  ({interim_metrics['fully_incorrect']} items)"
                )
                print(
                    f"  Correct w/ Extraneous:      {correct_with_extraneous_pct:6.2%}  ({interim_metrics['correct_with_extraneous']} items)"
                )
                print(f"  F1 Score:                   {f1:6.2%}")
                print()
                print(
                    f"Note: Based on {interim_metrics['num_valid']} completed tasks. Final metrics may differ."
                )
            else:
                print(f"Tasks in progress... ({summary.total_completed} completed)")
                print("Detailed metrics will be available when runs complete.")

            print("=" * 80)

        # Exit with appropriate code
        if summary.total_tasks == 0:
            print("No task files found in any run directories")
        elif summary.total_completed == 0:
            print("No tasks completed yet")

    except FileNotFoundError as e:
        print(f"Error: {e}")
    except PermissionError as e:
        print(f"Error: {e}")
    except ValueError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")
