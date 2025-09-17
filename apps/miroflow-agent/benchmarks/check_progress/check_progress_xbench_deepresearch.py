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

import glob
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from io import StringIO
from typing import Dict, List, Optional, Tuple

# Constants
XBENCH_DEEPRESEARCH_TASKS_PER_RUN = 100
XBENCH_DEEPRESEARCH_DATA_PATH = "../../data/xbench_deepresearch/standardized_data.jsonl"
TASK_ID_PATTERN = r"task_([a-f0-9]+)"
DEFAULT_TASK_TIME_MINUTES = 3.5
MINUTES_PER_HOUR = 60
HOURS_PER_DAY = 24
MINUTES_PER_DAY = MINUTES_PER_HOUR * HOURS_PER_DAY


def create_progress_bar(percentage: float, width: int = 20) -> str:
    """Create a visual progress bar for percentage display"""
    filled = int(width * percentage / 100)
    bar = "█" * filled + "░" * (width - filled)

    # Add color based on percentage
    if percentage >= 80:
        color = "\033[92m"  # Green
    elif percentage >= 60:
        color = "\033[93m"  # Yellow
    elif percentage >= 40:
        color = "\033[33m"  # Orange
    else:
        color = "\033[91m"  # Red

    reset = "\033[0m"
    return f"{color}[{bar}] {percentage:.1f}%{reset}"


@dataclass
class TaskStats:
    """Statistics for a single task"""

    completed: int = 0
    running: int = 0
    failed: int = 0
    judge_correct: int = 0
    total: int = 0

    # Difficulty level statistics for individual run
    easy_completed: int = 0
    easy_correct: int = 0
    medium_completed: int = 0
    medium_correct: int = 0
    hard_completed: int = 0
    hard_correct: int = 0

    # Completed files for timing analysis
    completed_files: List[str] = None

    def __post_init__(self):
        if self.completed_files is None:
            self.completed_files = []

    @property
    def judge_accuracy(self) -> float:
        """Calculate judge accuracy percentage"""
        return (
            (self.judge_correct / self.completed * 100) if self.completed > 0 else 0.0
        )

    @property
    def completion_rate(self) -> float:
        """Calculate completion rate percentage"""
        return (self.completed / self.total * 100) if self.total > 0 else 0.0

    @property
    def easy_accuracy(self) -> float:
        """Calculate easy difficulty accuracy percentage"""
        return (
            (self.easy_correct / self.easy_completed * 100)
            if self.easy_completed > 0
            else 0.0
        )

    @property
    def medium_accuracy(self) -> float:
        """Calculate medium difficulty accuracy percentage"""
        return (
            (self.medium_correct / self.medium_completed * 100)
            if self.medium_completed > 0
            else 0.0
        )

    @property
    def hard_accuracy(self) -> float:
        """Calculate hard difficulty accuracy percentage"""
        return (
            (self.hard_correct / self.hard_completed * 100)
            if self.hard_completed > 0
            else 0.0
        )


@dataclass
class SummaryStats:
    """Summary statistics across all runs"""

    total_tasks: int = 0
    total_completed: int = 0
    total_running: int = 0
    total_failed: int = 0
    total_judge_correct: int = 0

    # Difficulty level statistics
    easy_completed: int = 0
    easy_correct: int = 0
    medium_completed: int = 0
    medium_correct: int = 0
    hard_completed: int = 0
    hard_correct: int = 0

    @property
    def total_judge_accuracy(self) -> float:
        """Calculate overall judge accuracy percentage"""
        return (
            (self.total_judge_correct / self.total_completed * 100)
            if self.total_completed > 0
            else 0.0
        )

    @property
    def total_completion_rate(self) -> float:
        """Calculate overall completion rate percentage"""
        return (
            (self.total_completed / self.total_tasks * 100)
            if self.total_tasks > 0
            else 0.0
        )

    @property
    def easy_accuracy(self) -> float:
        """Calculate easy difficulty accuracy percentage"""
        return (
            (self.easy_correct / self.easy_completed * 100)
            if self.easy_completed > 0
            else 0.0
        )

    @property
    def medium_accuracy(self) -> float:
        """Calculate medium difficulty accuracy percentage"""
        return (
            (self.medium_correct / self.medium_completed * 100)
            if self.medium_completed > 0
            else 0.0
        )

    @property
    def hard_accuracy(self) -> float:
        """Calculate hard difficulty accuracy percentage"""
        return (
            (self.hard_correct / self.hard_completed * 100)
            if self.hard_completed > 0
            else 0.0
        )


def find_earliest_start_time(completed_files: List[str]) -> Optional[datetime]:
    """Find the earliest start time from all completed files"""
    earliest_time = None

    for file_path in completed_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if "start_time" in data:
                # Parse UTC time and convert to naive datetime
                start_time_str = data["start_time"]
                if start_time_str.endswith("Z"):
                    start_time_str = start_time_str[:-1] + "+00:00"
                start_time = datetime.fromisoformat(start_time_str)
                # Convert to naive datetime for comparison
                start_time = start_time.replace(tzinfo=None)

                if earliest_time is None or start_time < earliest_time:
                    earliest_time = start_time

        except (json.JSONDecodeError, KeyError, ValueError, OSError):
            continue  # Skip files with invalid timing data

    return earliest_time


def estimate_completion_time(
    total_tasks: int, completed_tasks: int, completed_files: List[str]
) -> str:
    """Estimate completion time based on overall progress rate"""
    if completed_tasks == 0:
        return "Cannot estimate (no completed tasks)"

    # Check if all tasks are completed
    remaining_tasks = total_tasks - completed_tasks
    if remaining_tasks <= 0:
        return "All tasks completed"

    # Find earliest start time and calculate overall rate
    earliest_start = find_earliest_start_time(completed_files)
    current_time = datetime.now()

    if earliest_start is None:
        # Fallback to default estimation if no valid timing data
        estimated_minutes = remaining_tasks * DEFAULT_TASK_TIME_MINUTES
    else:
        # Calculate overall elapsed time and rate
        elapsed_time = current_time - earliest_start
        elapsed_minutes = elapsed_time.total_seconds() / 60

        if elapsed_minutes <= 0:
            return "Cannot estimate (time interval too short)"

        # Calculate average time per task
        avg_minutes_per_task = elapsed_minutes / completed_tasks
        if avg_minutes_per_task <= 0:
            return "Cannot estimate (invalid time per task)"

        # Estimate remaining time
        estimated_minutes = remaining_tasks * avg_minutes_per_task

    # Always return in minutes
    return f"~{int(estimated_minutes)} minutes"


class ProgressChecker:
    """Main class for checking benchmark progress"""

    def __init__(self, target_path: str):
        self.target_path = target_path
        self.run_dirs: List[str] = []
        self.total_tasks_per_run = XBENCH_DEEPRESEARCH_TASKS_PER_RUN

        # XBench-DeepResearch data for difficulty levels
        self.task_difficulty_map: Dict[str, str] = {}
        self._load_xbench_deepresearch_data()

    def _load_xbench_deepresearch_data(self):
        """Load XBench-DeepResearch dataset information for difficulty levels"""
        try:
            if os.path.exists(XBENCH_DEEPRESEARCH_DATA_PATH):
                with open(XBENCH_DEEPRESEARCH_DATA_PATH) as f:
                    for line in f:
                        data = json.loads(line)
                        task_id = data.get("task_id", "")
                        difficulty = data.get("metadata", {}).get(
                            "difficulty_level", ""
                        )
                        if task_id and difficulty:
                            self.task_difficulty_map[task_id] = difficulty
        except Exception as e:
            print(f"Warning: Could not load XBench-DeepResearch data: {e}")

    def find_run_directories(self) -> List[str]:
        """Find all run directories in the target path"""
        run_dirs = []

        if not os.path.exists(self.target_path):
            raise FileNotFoundError(f"Path '{self.target_path}' does not exist")

        # Check if target_path itself is a run directory
        if os.path.basename(self.target_path).startswith("run_"):
            run_dirs.append(self.target_path)
        else:
            # Find run_* directories under target_path
            try:
                for item in os.listdir(self.target_path):
                    item_path = os.path.join(self.target_path, item)
                    if os.path.isdir(item_path) and item.startswith("run_"):
                        run_dirs.append(item_path)
            except PermissionError:
                raise PermissionError(
                    f"No permission to access directory '{self.target_path}'"
                )

        # Sort by run number
        run_dirs.sort(key=lambda x: self._extract_run_number(x))

        if not run_dirs:
            raise ValueError(f"No run directories found in '{self.target_path}'")

        return run_dirs

    def _extract_run_number(self, path: str) -> int:
        """Extract run number from directory path for sorting"""
        basename = os.path.basename(path)
        parts = basename.split("_")
        if len(parts) > 1 and parts[1].isdigit():
            return int(parts[1])
        return 0

    def _extract_task_id(self, filename: str) -> Optional[str]:
        """Extract task ID from filename"""
        xbench_deepresearch_match = re.match(TASK_ID_PATTERN, filename)
        if xbench_deepresearch_match:
            return f"task_id_{xbench_deepresearch_match.group(1)}"
        return None

    def _get_latest_task_files(self, run_dir: str) -> List[str]:
        """Get the latest task file for each task ID in a run directory"""
        json_files = glob.glob(os.path.join(run_dir, "task_*.json"))

        if not json_files:
            return []

        # Group by task ID, keep only the latest file for each task
        task_groups: Dict[str, Dict] = {}

        for json_file in json_files:
            filename = os.path.basename(json_file)
            task_id = self._extract_task_id(filename)

            if task_id:
                try:
                    # Read the JSON file to get the start_time
                    with open(json_file, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    start_time_str = data.get("start_time", "")
                    if start_time_str:
                        # Parse the ISO format timestamp
                        from datetime import datetime

                        start_time = datetime.fromisoformat(
                            start_time_str.replace("Z", "+00:00")
                        )
                        start_timestamp = start_time.timestamp()
                    else:
                        # Fallback to file modification time if start_time is not available
                        start_timestamp = os.path.getmtime(json_file)

                    if (
                        task_id not in task_groups
                        or start_timestamp > task_groups[task_id]["timestamp"]
                    ):
                        task_groups[task_id] = {
                            "file": json_file,
                            "timestamp": start_timestamp,
                        }
                except (json.JSONDecodeError, ValueError, OSError) as e:
                    # Fallback to file modification time if JSON parsing fails
                    print(f"Warning: Could not parse {json_file}: {e}")
                    file_mtime = os.path.getmtime(json_file)
                    if (
                        task_id not in task_groups
                        or file_mtime > task_groups[task_id]["timestamp"]
                    ):
                        task_groups[task_id] = {
                            "file": json_file,
                            "timestamp": file_mtime,
                        }

        return [info["file"] for info in task_groups.values()]

    def _is_task_completed(self, data: Dict) -> bool:
        """Check if a task is completed based on its data"""
        end_time = data.get("end_time", "")
        error = data.get("error", "")
        status = data.get("status", "")
        final_answer = data.get("final_boxed_answer", "")

        return (
            (end_time != "" and error == "")
            or (status == "completed")
            or (final_answer != "" and error == "")
        )

    def _is_judge_correct(self, judge_result) -> bool:
        """Determine if LLM judge result indicates correct answer"""
        if isinstance(judge_result, bool):
            return judge_result
        elif isinstance(judge_result, str):
            return judge_result.lower() in ["correct", "true", "1", "yes", "pass"]
        elif isinstance(judge_result, (int, float)):
            return judge_result > 0
        elif isinstance(judge_result, dict):
            return judge_result.get("correct", False) or judge_result.get(
                "is_correct", False
            )
        return False

    def analyze_run_directory(self, run_dir: str) -> TaskStats:
        """Analyze a single run directory and return statistics"""
        latest_files = self._get_latest_task_files(run_dir)

        # Use the correct total tasks for XBench-DeepResearch
        stats = TaskStats(total=self.total_tasks_per_run)
        completed_files = []  # Track completed files for timing analysis

        for json_file in latest_files:
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Extract task ID from filename
                filename = os.path.basename(json_file)
                task_id = self._extract_task_id(filename)

                status = data.get("status", "")

                if status == "running":
                    stats.running += 1
                elif self._is_task_completed(data):
                    stats.completed += 1
                    completed_files.append(json_file)  # Track for timing analysis

                    # Check judge result for completed tasks
                    judge_result = data.get("final_judge_result", None)
                    is_correct = judge_result is not None and self._is_judge_correct(
                        judge_result
                    )
                    if is_correct:
                        stats.judge_correct += 1

                    # Update difficulty level statistics
                    if task_id:
                        difficulty = self.task_difficulty_map.get(task_id, "")
                        if difficulty == "easy":
                            stats.easy_completed += 1
                            if is_correct:
                                stats.easy_correct += 1
                        elif difficulty == "medium":
                            stats.medium_completed += 1
                            if is_correct:
                                stats.medium_correct += 1
                        elif difficulty == "hard":
                            stats.hard_completed += 1
                            if is_correct:
                                stats.hard_correct += 1
                else:
                    stats.failed += 1

            except (json.JSONDecodeError, IOError) as e:
                # Skip files that are being written or corrupted
                if "Expecting value" in str(e) or "line 1 column 1" in str(e):
                    continue  # Skip corrupted/empty files
                print(f"Warning: Could not parse {json_file}: {e}")
                stats.failed += 1
            except Exception as e:
                print(f"Warning: Unexpected error processing {json_file}: {e}")
                stats.failed += 1

        # Store completed files in stats for timing analysis
        stats.completed_files = completed_files
        return stats

    def _get_running_tasks(self, run_dir: str) -> List[str]:
        """Get list of currently running tasks"""
        running_tasks = []
        task_logs = glob.glob(os.path.join(run_dir, "task_*.json"))

        for log_file in task_logs:
            try:
                with open(log_file, "r") as f:
                    log_data = json.load(f)

                # Check if task is still running
                status = log_data.get("status", "")
                end_time = log_data.get("end_time", "")

                if status == "running" or (status == "" and end_time == ""):
                    filename = os.path.basename(log_file)
                    task_id = self._extract_task_id(filename)
                    if task_id:
                        running_tasks.append(task_id)

            except Exception:
                continue

        return running_tasks

    def run_analysis(self) -> SummaryStats:
        """Run the complete analysis and return summary statistics"""
        self.run_dirs = self.find_run_directories()
        summary = SummaryStats()
        run_stats_list = []  # Store statistics for each run
        all_completed_files = []  # Collect all completed files for timing analysis

        print()
        print("=" * 80)
        print(f"Analyzing benchmark progress for: {self.target_path}")
        print(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)

        # Analyze each run directory
        for run_dir in self.run_dirs:
            run_name = os.path.basename(run_dir)
            stats = self.analyze_run_directory(run_dir)

            if stats.total == 0:
                print(f"{run_name}: No task files found")
                print()
                continue

            # Display run statistics with overall accuracy
            if stats.completed > 0:
                accuracy_bar = create_progress_bar(stats.judge_accuracy)
                print(
                    f"{run_name}: Status: {stats.completed} completed, {stats.running} running, {stats.failed} failed"
                )
                print(
                    f"  Overall Accuracy: {stats.judge_correct}/{stats.completed} {accuracy_bar}"
                )
            else:
                print(
                    f"{run_name}: Status: {stats.completed} completed, {stats.running} running, {stats.failed} failed"
                )
                print(
                    f"  Overall Accuracy: {stats.judge_correct}/{stats.completed} (N/A)"
                )

            # Display difficulty level statistics for this run
            if (
                stats.easy_completed > 0
                or stats.medium_completed > 0
                or stats.hard_completed > 0
            ):
                print("  Difficulty Levels:")
                if stats.easy_completed > 0:
                    easy_bar = create_progress_bar(stats.easy_accuracy)
                    print(
                        f"    Easy: {stats.easy_correct}/{stats.easy_completed} {easy_bar}"
                    )
                if stats.medium_completed > 0:
                    medium_bar = create_progress_bar(stats.medium_accuracy)
                    print(
                        f"    Medium: {stats.medium_correct}/{stats.medium_completed} {medium_bar}"
                    )
                if stats.hard_completed > 0:
                    hard_bar = create_progress_bar(stats.hard_accuracy)
                    print(
                        f"    Hard: {stats.hard_correct}/{stats.hard_completed} {hard_bar}"
                    )

            print()

            # Store run statistics for later display
            run_stats_list.append((run_name, stats))

            # Collect completed files for timing analysis
            all_completed_files.extend(stats.completed_files)

            # Update summary
            summary.total_tasks += stats.total
            summary.total_completed += stats.completed
            summary.total_running += stats.running
            summary.total_failed += stats.failed
            summary.total_judge_correct += stats.judge_correct

            # Update difficulty level statistics
            self._update_difficulty_stats(run_dir, summary)

        # Display summary
        self._display_summary(summary, run_stats_list, all_completed_files)

        return summary

    def _update_difficulty_stats(self, run_dir: str, summary: SummaryStats):
        """Update difficulty level statistics for a run directory"""
        # Get the latest task file for each task ID
        latest_files = self._get_latest_task_files(run_dir)

        for log_file in latest_files:
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    log_data = json.load(f)

                # Extract task ID from filename
                filename = os.path.basename(log_file)
                task_id = self._extract_task_id(filename)
                if not task_id:
                    continue

                # Get difficulty level
                difficulty = self.task_difficulty_map.get(task_id, "")
                if not difficulty:
                    continue

                # Check if task is completed and has results
                if self._is_task_completed(log_data):
                    # Try to get LLM judge result from log
                    llm_result = log_data.get("final_judge_result", "")
                    is_correct = self._is_judge_correct(llm_result)

                    # Update difficulty statistics
                    if difficulty == "easy":
                        summary.easy_completed += 1
                        if is_correct:
                            summary.easy_correct += 1
                    elif difficulty == "medium":
                        summary.medium_completed += 1
                        if is_correct:
                            summary.medium_correct += 1
                    elif difficulty == "hard":
                        summary.hard_completed += 1
                        if is_correct:
                            summary.hard_correct += 1

            except Exception:
                continue

    def _display_summary(
        self,
        summary: SummaryStats,
        run_stats_list: List[Tuple[str, TaskStats]],
        completed_files: List[str],
    ):
        """Display summary statistics"""
        print("=" * 80)
        print("SUMMARY STATISTICS")
        print("=" * 80)
        print(
            f"Total Tasks: {summary.total_tasks} ({summary.total_completed} completed, {summary.total_running} running)"
        )

        # Estimate completion time using overall progress rate
        if summary.total_tasks > 0 and summary.total_completed > 0:
            remaining_tasks = summary.total_tasks - summary.total_completed
            earliest_start = find_earliest_start_time(completed_files)
            completion_estimate = estimate_completion_time(
                summary.total_tasks, summary.total_completed, completed_files
            )

            print(f"Remaining Tasks: {remaining_tasks}")
            if earliest_start:
                elapsed_time = datetime.now() - earliest_start
                elapsed_minutes = elapsed_time.total_seconds() / 60
                tasks_per_minute = (
                    summary.total_completed / elapsed_minutes
                    if elapsed_minutes > 0
                    else 0
                )
                print(f"Elapsed Time: {elapsed_minutes:.1f} minutes")
                print(f"Completion Rate: {tasks_per_minute:.1f} tasks/minute")
            print(f"Estimated Time to Complete: {completion_estimate}")

        if summary.total_completed > 0:
            accuracy_bar = create_progress_bar(summary.total_judge_accuracy)
            print(
                f"Judge Accuracy: {summary.total_judge_correct}/{summary.total_completed} {accuracy_bar}"
            )

        # Display overall difficulty level accuracies
        if (
            summary.easy_completed > 0
            or summary.medium_completed > 0
            or summary.hard_completed > 0
        ):
            print()
            print("OVERALL DIFFICULTY LEVEL ACCURACIES:")
            if summary.easy_completed > 0:
                easy_bar = create_progress_bar(summary.easy_accuracy)
                print(
                    f"  Easy: {summary.easy_correct}/{summary.easy_completed} {easy_bar}"
                )
            if summary.medium_completed > 0:
                medium_bar = create_progress_bar(summary.medium_accuracy)
                print(
                    f"  Medium: {summary.medium_correct}/{summary.medium_completed} {medium_bar}"
                )
            if summary.hard_completed > 0:
                hard_bar = create_progress_bar(summary.hard_accuracy)
                print(
                    f"  Hard: {summary.hard_correct}/{summary.hard_completed} {hard_bar}"
                )

        print("=" * 80)
        print()

        # Save analysis results to log file
        self._save_analysis_log(summary, run_stats_list, completed_files)

    def _save_analysis_log(
        self,
        summary: SummaryStats,
        run_stats_list: List[Tuple[str, TaskStats]],
        completed_files: List[str],
    ) -> None:
        """Save analysis results to a log file in the target directory"""
        try:
            # Create log filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_filename = f"progress_analysis_{timestamp}.log"
            log_path = os.path.join(self.target_path, log_filename)

            # Capture the analysis output
            output_buffer = StringIO()

            # Write header
            output_buffer.write("=" * 80 + "\n")
            output_buffer.write("XBench-DeepResearch Progress Analysis\n")
            output_buffer.write(
                f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            )
            output_buffer.write(f"Target Path: {self.target_path}\n")
            output_buffer.write("=" * 80 + "\n\n")

            # Write run statistics
            for run_name, stats in run_stats_list:
                output_buffer.write(
                    f"{run_name}: Status: {stats.completed} completed, {stats.running} running, {stats.failed} failed\n"
                )
                if stats.completed > 0:
                    accuracy = stats.judge_correct / stats.completed * 100
                    output_buffer.write(
                        f"  Overall Accuracy: {stats.judge_correct}/{stats.completed} ({accuracy:.1f}%)\n"
                    )
                else:
                    output_buffer.write(
                        f"  Overall Accuracy: {stats.judge_correct}/{stats.completed} (N/A)\n"
                    )

                # Write difficulty levels
                if (
                    stats.easy_completed > 0
                    or stats.medium_completed > 0
                    or stats.hard_completed > 0
                ):
                    output_buffer.write("  Difficulty Levels:\n")
                    if stats.easy_completed > 0:
                        easy_acc = stats.easy_correct / stats.easy_completed * 100
                        output_buffer.write(
                            f"    Easy: {stats.easy_correct}/{stats.easy_completed} ({easy_acc:.1f}%)\n"
                        )
                    if stats.medium_completed > 0:
                        medium_acc = stats.medium_correct / stats.medium_completed * 100
                        output_buffer.write(
                            f"    Medium: {stats.medium_correct}/{stats.medium_completed} ({medium_acc:.1f}%)\n"
                        )
                    if stats.hard_completed > 0:
                        hard_acc = stats.hard_correct / stats.hard_completed * 100
                        output_buffer.write(
                            f"    Hard: {stats.hard_correct}/{stats.hard_completed} ({hard_acc:.1f}%)\n"
                        )
                output_buffer.write("\n")

            # Write summary statistics
            output_buffer.write("=" * 80 + "\n")
            output_buffer.write("SUMMARY STATISTICS\n")
            output_buffer.write("=" * 80 + "\n")
            output_buffer.write(
                f"Total Tasks: {summary.total_tasks} ({summary.total_completed} completed, {summary.total_running} running)\n"
            )

            # Write timing information
            if summary.total_tasks > 0 and summary.total_completed > 0:
                remaining_tasks = summary.total_tasks - summary.total_completed
                earliest_start = find_earliest_start_time(completed_files)
                completion_estimate = estimate_completion_time(
                    summary.total_tasks, summary.total_completed, completed_files
                )

                output_buffer.write(f"Remaining Tasks: {remaining_tasks}\n")
                if earliest_start:
                    elapsed_time = datetime.now() - earliest_start
                    elapsed_minutes = elapsed_time.total_seconds() / 60
                    tasks_per_minute = (
                        summary.total_completed / elapsed_minutes
                        if elapsed_minutes > 0
                        else 0
                    )
                    output_buffer.write(
                        f"Elapsed Time: {elapsed_minutes:.1f} minutes\n"
                    )
                    output_buffer.write(
                        f"Completion Rate: {tasks_per_minute:.1f} tasks/minute\n"
                    )
                output_buffer.write(
                    f"Estimated Time to Complete: {completion_estimate}\n"
                )

            if summary.total_completed > 0:
                accuracy = summary.total_judge_correct / summary.total_completed * 100
                output_buffer.write(
                    f"Judge Accuracy: {summary.total_judge_correct}/{summary.total_completed} ({accuracy:.1f}%)\n"
                )

            # Write overall difficulty level accuracies
            if (
                summary.easy_completed > 0
                or summary.medium_completed > 0
                or summary.hard_completed > 0
            ):
                output_buffer.write("\nOVERALL DIFFICULTY LEVEL ACCURACIES:\n")
                if summary.easy_completed > 0:
                    easy_acc = summary.easy_correct / summary.easy_completed * 100
                    output_buffer.write(
                        f"  Easy: {summary.easy_correct}/{summary.easy_completed} ({easy_acc:.1f}%)\n"
                    )
                if summary.medium_completed > 0:
                    medium_acc = summary.medium_correct / summary.medium_completed * 100
                    output_buffer.write(
                        f"  Medium: {summary.medium_correct}/{summary.medium_completed} ({medium_acc:.1f}%)\n"
                    )
                if summary.hard_completed > 0:
                    hard_acc = summary.hard_correct / summary.hard_completed * 100
                    output_buffer.write(
                        f"  Hard: {summary.hard_correct}/{summary.hard_completed} ({hard_acc:.1f}%)\n"
                    )

            output_buffer.write("=" * 80 + "\n")

            # Write to file
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(output_buffer.getvalue())

            output_buffer.close()
            print(f"Analysis results saved to: {log_path}")

        except Exception as e:
            print(f"Warning: Could not save analysis log: {e}")


def main() -> None:
    """Main entry point for the XBench-DeepResearch progress checker.

    Analyzes benchmark progress and displays statistics for XBench-DeepResearch evaluation runs.
    """
    # Check for help option
    if len(sys.argv) > 1 and sys.argv[1] in ["-h", "--help"]:
        print(__doc__)
        print("\nUsage:")
        print("  python check_progress_xbench_deepresearch.py <path>")
        print("\nArguments:")
        print("  path    Path to XBench-DeepResearch benchmark directory")
        print("\nExamples:")
        print(
            "  python check_progress_xbench_deepresearch.py logs/xbench_deepresearch/my_evaluation/"
        )
        print(
            "  python check_progress_xbench_deepresearch.py /path/to/xbench_deepresearch/results"
        )
        sys.exit(0)

    # Get target path from command line arguments
    if len(sys.argv) < 2:
        raise ValueError("Please provide a target path")
    target_path = sys.argv[1]

    try:
        # Create progress checker and run analysis
        checker = ProgressChecker(target_path)
        summary = checker.run_analysis()

        # Exit with appropriate code
        if summary.total_tasks == 0:
            print("No task files found in any run directories")
            sys.exit(1)
        elif summary.total_completed == 0:
            print("No tasks completed yet")
            sys.exit(2)
        else:
            sys.exit(0)

    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except PermissionError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
