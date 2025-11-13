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
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime
from io import StringIO
from typing import Dict, List, Optional, Tuple

# Time estimation constants
DEFAULT_TASK_TIME_MINUTES = 3.5
MINUTES_PER_HOUR = 60
HOURS_PER_DAY = 24
MINUTES_PER_DAY = MINUTES_PER_HOUR * HOURS_PER_DAY

# Progress bar configuration
PROGRESS_BAR_WIDTH = 20
GREEN_THRESHOLD = 80
YELLOW_THRESHOLD = 60
ORANGE_THRESHOLD = 40

# Judge result patterns for correctness
CORRECT_RESULTS = ["CORRECT", "SUCCESS"]
SUCCESS_PATTERNS = ["PASS_AT_K_SUCCESS"]

# Log file configuration
LOG_FILE_PREFIX = "progress_analysis_"
LOG_FILE_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"


def create_progress_bar(percentage: float, width: int = PROGRESS_BAR_WIDTH) -> str:
    """Create a visual progress bar for percentage display"""
    filled = int(width * percentage / 100)
    bar = "█" * filled + "░" * (width - filled)

    # Add color based on percentage
    if percentage >= GREEN_THRESHOLD:
        color = "\033[92m"  # Green
    elif percentage >= YELLOW_THRESHOLD:
        color = "\033[93m"  # Yellow
    elif percentage >= ORANGE_THRESHOLD:
        color = "\033[33m"  # Orange
    else:
        color = "\033[91m"  # Red

    reset = "\033[0m"
    return f"{color}[{bar}] {percentage:.1f}%{reset}"


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


def find_latest_end_time(completed_files: List[str]) -> Optional[datetime]:
    """Find the latest end time from all completed files"""
    latest_time = None

    for file_path in completed_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if "end_time" in data:
                # Parse UTC time and convert to naive datetime
                end_time_str = data["end_time"]
                if end_time_str.endswith("Z"):
                    end_time_str = end_time_str[:-1] + "+00:00"
                end_time = datetime.fromisoformat(end_time_str)
                # Convert to naive datetime for comparison (UTC-naive)
                end_time = end_time.replace(tzinfo=None)

                if latest_time is None or end_time > latest_time:
                    latest_time = end_time

        except (json.JSONDecodeError, KeyError, ValueError, OSError):
            continue  # Skip files with invalid timing data

    # If no valid end_time found, return current UTC (naive)
    return latest_time or datetime.now().replace(tzinfo=None)


def calculate_mean_and_std(values: List[float]) -> Tuple[float, float]:
    """Calculate mean and standard deviation of a list of values"""
    if not values:
        return 0.0, 0.0

    n = len(values)
    mean = sum(values) / n

    if n == 1:
        return mean, 0.0

    variance = sum((x - mean) ** 2 for x in values) / (n - 1)
    std = math.sqrt(variance)

    return mean, std


def estimate_completion_time(
    total_tasks: int, completed_tasks: int, completed_files: List[str]
) -> str:
    """Estimate completion time based on overall progress rate from all completed tasks"""
    if completed_tasks == 0:
        return "Cannot estimate (no completed tasks)"

    # Check if all tasks are completed
    if completed_tasks >= total_tasks:
        return "All tasks completed"

    remaining_tasks = total_tasks - completed_tasks

    # Use overall completion rate from all successfully completed tasks
    earliest_start = find_earliest_start_time(completed_files)
    latest_end = find_latest_end_time(completed_files)

    if earliest_start is None:
        # Fallback to default estimation if no valid timing data
        estimated_minutes = remaining_tasks * DEFAULT_TASK_TIME_MINUTES
    else:
        # Calculate overall elapsed time
        elapsed_time = latest_end - earliest_start
        elapsed_minutes = elapsed_time.total_seconds() / 60

        if elapsed_minutes <= 0:
            return "Cannot estimate (time interval too short)"

        # Calculate average time per task based on all completed tasks
        avg_minutes_per_task = elapsed_minutes / completed_tasks
        if avg_minutes_per_task <= 0:
            return "Cannot estimate (invalid time per task)"

        estimated_minutes = remaining_tasks * avg_minutes_per_task

    # Format the estimate in minutes
    return f"~{int(estimated_minutes)} minutes"


@dataclass
class TaskStats:
    """Statistics for a single task"""

    completed: int = 0
    running: int = 0
    failed: int = 0
    judge_correct: int = 0
    total: int = 0

    # Completed files for timing analysis
    completed_files: List[str] = None

    # Turn statistics
    total_turns: int = 0
    completed_tasks_with_turns: int = 0

    # No boxed content found statistics
    no_boxed_found: int = 0

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
    def average_turns(self) -> float:
        """Calculate average turns per completed task"""
        return (
            (self.total_turns / self.completed_tasks_with_turns)
            if self.completed_tasks_with_turns > 0
            else 0.0
        )


@dataclass
class GAIATaskStats(TaskStats):
    """Statistics for a single task"""

    # Difficulty level tracking
    level1_completed: int = 0
    level1_correct: int = 0
    level2_completed: int = 0
    level2_correct: int = 0
    level3_completed: int = 0
    level3_correct: int = 0

    @property
    def level1_accuracy(self) -> float:
        """Calculate Level 1 accuracy percentage"""
        return (
            (self.level1_correct / self.level1_completed * 100)
            if self.level1_completed > 0
            else 0.0
        )

    @property
    def level2_accuracy(self) -> float:
        """Calculate Level 2 accuracy percentage"""
        return (
            (self.level2_correct / self.level2_completed * 100)
            if self.level2_completed > 0
            else 0.0
        )

    @property
    def level3_accuracy(self) -> float:
        """Calculate Level 3 accuracy percentage"""
        return (
            (self.level3_correct / self.level3_completed * 100)
            if self.level3_completed > 0
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
    total_no_boxed_found: int = 0

    @property
    def total_judge_accuracy(self) -> float:
        """Calculate overall judge accuracy percentage"""
        return (
            (self.total_judge_correct / self.total_completed * 100)
            if self.total_completed > 0
            else 0.0
        )

    def average_run_accuracy(
        self, run_stats_list: List[Tuple[str, TaskStats]]
    ) -> Tuple[float, float]:
        """Calculate overall accuracy (mean) and standard deviation across individual runs"""
        if not run_stats_list:
            return 0.0, 0.0

        # Mean accuracy is the overall accuracy (weighted average)
        # This matches the OVERALL JUDGE ACCURACY calculation
        mean = self.total_judge_accuracy

        # Standard deviation is calculated from individual run accuracies
        accuracies = [
            stats.judge_accuracy for _, stats in run_stats_list if stats.completed > 0
        ]

        if not accuracies:
            return mean, 0.0

        _, std = calculate_mean_and_std(accuracies)
        return mean, std

    @property
    def total_completion_rate(self) -> float:
        """Calculate overall completion rate percentage"""
        return (
            (self.total_completed / self.total_tasks * 100)
            if self.total_tasks > 0
            else 0.0
        )


@dataclass
class GAIASummaryStats(SummaryStats):
    """Summary statistics across all runs"""

    # Difficulty level summary stats
    level1_completed: int = 0
    level1_correct: int = 0
    level2_completed: int = 0
    level2_correct: int = 0
    level3_completed: int = 0
    level3_correct: int = 0

    @property
    def level1_accuracy(self) -> float:
        """Calculate overall Level 1 accuracy percentage"""
        return (
            (self.level1_correct / self.level1_completed * 100)
            if self.level1_completed > 0
            else 0.0
        )

    @property
    def level2_accuracy(self) -> float:
        """Calculate overall Level 2 accuracy percentage"""
        return (
            (self.level2_correct / self.level2_completed * 100)
            if self.level2_completed > 0
            else 0.0
        )

    @property
    def level3_accuracy(self) -> float:
        """Calculate overall Level 3 accuracy percentage"""
        return (
            (self.level3_correct / self.level3_completed * 100)
            if self.level3_completed > 0
            else 0.0
        )


class ProgressChecker:
    """Main class for checking benchmark progress"""

    def __init__(self, target_path: str, task_per_run: int, data_path: str):
        self.target_path = target_path
        self.run_dirs: List[str] = []
        self.total_tasks_per_run = task_per_run

        # Load benchmark data
        self._load_benchmark_data(data_path)

    def _load_benchmark_data(self, data_path) -> None:
        """Load benchmark data and configuration"""
        try:
            # Load benchmark data if available
            if os.path.exists(data_path):
                with open(data_path) as f:
                    benchmark_data = [json.loads(line) for line in f.readlines()]
                print(f"Loaded {len(benchmark_data)} tasks from {data_path}")
        except Exception as e:
            print(f"Warning: Could not load data: {e}")

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

    def _extract_task_id(self, filename: str, task_id_pattern: str) -> Optional[str]:
        """Extract task ID from filename"""
        match = re.match(task_id_pattern, filename)
        return match.group(1) if match else None

    def _get_latest_task_files(self, run_dir: str, task_id_pattern: str) -> List[str]:
        """Get the latest task file for each task ID in a run directory"""
        json_files = glob.glob(os.path.join(run_dir, "task_*.json"))

        if not json_files:
            return []

        # Group by task ID, keep only the latest file for each task
        task_groups: Dict[str, Dict] = {}

        for json_file in json_files:
            filename = os.path.basename(json_file)
            task_id = self._extract_task_id(filename, task_id_pattern)

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
            result_str = judge_result.upper()
            return (
                result_str in CORRECT_RESULTS
                or any(pattern in result_str for pattern in SUCCESS_PATTERNS)
                or result_str.lower() in ["true", "1", "yes", "pass"]
            )
        elif isinstance(judge_result, (int, float)):
            return judge_result > 0
        elif isinstance(judge_result, dict):
            return judge_result.get("correct", False) or judge_result.get(
                "is_correct", False
            )
        return False

    def _calculate_turns(self, data: Dict) -> int:
        """Calculate number of turns from task data (excluding system prompt)"""
        try:
            main_agent_history = data.get("main_agent_message_history", {})
            message_history = main_agent_history.get("message_history", [])

            if not message_history:
                return 0

            # Filter out system messages and count total messages, then divide by 2
            # Turn count = (total messages excluding system) / 2
            non_system_messages = [
                msg for msg in message_history if msg.get("role") != "system"
            ]

            # Each turn consists of user + assistant, so divide by 2
            turn_count = len(non_system_messages) // 2

            return turn_count
        except (KeyError, TypeError, IndexError):
            return 0

    def analyze_run_directory(self, run_dir: str, task_id_pattern: str) -> TaskStats:
        """Analyze a single run directory and return statistics"""
        latest_files = self._get_latest_task_files(run_dir, task_id_pattern)

        # Use the correct total tasks
        stats = TaskStats(total=self.total_tasks_per_run)
        completed_files = []  # Track completed files for timing analysis

        for json_file in latest_files:
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

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

                    # Check if final_boxed_answer contains "No \\boxed{} content found"
                    final_boxed_answer = data.get("final_boxed_answer", "")
                    if (
                        isinstance(final_boxed_answer, str)
                        and "No \\boxed{} content found" in final_boxed_answer
                    ):
                        stats.no_boxed_found += 1

                    # Calculate turns for completed tasks
                    turns = self._calculate_turns(data)
                    if turns > 0:
                        stats.total_turns += turns
                        stats.completed_tasks_with_turns += 1
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

    def run_analysis(
        self, benchmark_name_std: str, task_id_pattern: str
    ) -> SummaryStats:
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
            stats = self.analyze_run_directory(run_dir, task_id_pattern)

            if stats.total == 0:
                print(f"{run_name}: No task files found")
                print()
                continue

            # Display run statistics in a single line
            run_info = f"[{run_name}] Completed: {stats.completed} | Running: {stats.running} | Failed: {stats.failed}"

            # Add accuracy information
            if stats.completed > 0:
                run_info += f" | Accuracy: {stats.judge_correct}/{stats.completed} ({stats.judge_accuracy:.1f}%)"

                # Add average turns information (show even if some tasks are still running)
                if stats.completed_tasks_with_turns > 0:
                    run_info += f" | Avg Turns: {stats.average_turns:.1f}"

            print(run_info)
            print()

            # Store run statistics for later display
            run_stats_list.append((run_name, stats))

            # Collect completed files for timing analysis
            all_completed_files.extend(stats.completed_files)

            # Update summary statistics
            summary.total_tasks += stats.total
            summary.total_completed += stats.completed
            summary.total_running += stats.running
            summary.total_failed += stats.failed
            summary.total_judge_correct += stats.judge_correct
            summary.total_no_boxed_found += stats.no_boxed_found

        # Display summary after all runs are processed
        self._display_summary(
            summary, run_stats_list, all_completed_files, benchmark_name_std
        )

        return summary

    def _display_summary(
        self,
        summary: SummaryStats,
        run_stats_list: List[Tuple[str, TaskStats]],
        completed_files: List[str],
        benchmark_name_std: str,
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
            latest_end = find_latest_end_time(completed_files)
            completion_estimate = estimate_completion_time(
                summary.total_tasks, summary.total_completed, completed_files
            )

            print(f"Remaining Tasks: {remaining_tasks}")
            if earliest_start:
                elapsed_time = latest_end - earliest_start
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

            # Calculate and display overall average turns
            total_turns = sum(stats.total_turns for _, stats in run_stats_list)
            total_tasks_with_turns = sum(
                stats.completed_tasks_with_turns for _, stats in run_stats_list
            )
            if total_tasks_with_turns > 0:
                overall_avg_turns = total_turns / total_tasks_with_turns
                print(f"Overall Average Turns: {overall_avg_turns:.1f}")

        # Display each run's correct percentage
        if run_stats_list:
            print()
            print("INDIVIDUAL RUN ACCURACIES:")
            for run_name, stats in run_stats_list:
                if stats.completed > 0:
                    accuracy_bar = create_progress_bar(stats.judge_accuracy)
                    print(
                        f"  {run_name}: {stats.judge_correct}/{stats.completed} {accuracy_bar}"
                    )
                else:
                    print(
                        f"  {run_name}: {stats.judge_correct}/{stats.completed} (N/A)"
                    )

            # Display mean accuracy and standard deviation
            mean_acc, std_acc = summary.average_run_accuracy(run_stats_list)
            if mean_acc > 0:
                print()
                print(f"MEAN ACCURACY: {mean_acc:.1f}% ± {std_acc:.1f}%")

            # Display no boxed content found statistics
            if summary.total_completed > 0:
                print(
                    f"No \\boxed{{}} content found: {summary.total_no_boxed_found}/{summary.total_completed} ({summary.total_no_boxed_found / summary.total_completed * 100:.1f}%)"
                )

        print("=" * 80)
        print()

        # Save analysis results to log file
        self._save_analysis_log(
            summary, run_stats_list, completed_files, benchmark_name_std
        )

    def _save_analysis_log(
        self,
        summary: SummaryStats,
        run_stats_list: List[Tuple[str, TaskStats]],
        completed_files: List[str],
        benchmark_name_std: str,
    ) -> None:
        """Save analysis results to a log file in the target directory"""
        try:
            # Create log filename with timestamp
            timestamp = datetime.now().strftime(LOG_FILE_TIMESTAMP_FORMAT)
            log_filename = f"{LOG_FILE_PREFIX}{timestamp}.log"
            log_path = os.path.join(self.target_path, log_filename)

            # Capture the analysis output
            output_buffer = StringIO()

            # Write header
            output_buffer.write("=" * 80 + "\n")
            output_buffer.write(f"{benchmark_name_std} Progress Analysis\n")
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
                latest_end = find_latest_end_time(completed_files)
                completion_estimate = estimate_completion_time(
                    summary.total_tasks, summary.total_completed, completed_files
                )

                output_buffer.write(f"Remaining Tasks: {remaining_tasks}\n")
                if earliest_start:
                    elapsed_time = latest_end - earliest_start
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
                no_boxed_percentage = (
                    summary.total_no_boxed_found / summary.total_completed * 100
                )
                output_buffer.write(
                    f"No \\boxed{{}} content found: {summary.total_no_boxed_found}/{summary.total_completed} ({no_boxed_percentage:.1f}%)\n"
                )

            # Write individual run accuracies
            if run_stats_list:
                output_buffer.write("\nINDIVIDUAL RUN ACCURACIES:\n")
                for run_name, stats in run_stats_list:
                    if stats.completed > 0:
                        accuracy = stats.judge_correct / stats.completed * 100
                        output_buffer.write(
                            f"  {run_name}: {stats.judge_correct}/{stats.completed} ({accuracy:.1f}%)\n"
                        )
                    else:
                        output_buffer.write(
                            f"  {run_name}: {stats.judge_correct}/{stats.completed} (N/A)\n"
                        )

                # Write mean accuracy and standard deviation
                mean_acc, std_acc = summary.average_run_accuracy(run_stats_list)
                if mean_acc > 0:
                    output_buffer.write(
                        f"\nMEAN ACCURACY: {mean_acc:.1f}% ± {std_acc:.1f}%\n"
                    )
                    if summary.total_completed > 0:
                        no_boxed_percentage = (
                            summary.total_no_boxed_found / summary.total_completed * 100
                        )
                        output_buffer.write(
                            f"No \\boxed{{}} content found: {summary.total_no_boxed_found}/{summary.total_completed} ({no_boxed_percentage:.1f}%)\n"
                        )

            output_buffer.write("=" * 80 + "\n")

            # Write to file
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(output_buffer.getvalue())

            output_buffer.close()
            print(f"Analysis results saved to: {log_path}")

        except Exception as e:
            print(f"Warning: Could not save analysis log: {e}")


class GAIAProgressChecker(ProgressChecker):
    """Main class for checking GAIA benchmark progress"""

    DIFFICULTY_LEVELS = [1, 2, 3]

    def __init__(self, target_path: str, task_per_run: int, data_path: str):
        super().__init__(target_path, task_per_run=0, data_path="")  # 调用父类构造函数

        # Difficulty level mapping
        self.task_difficulty_map: Dict[str, int] = {}
        self.total_tasks_per_run = task_per_run

        # Load GAIA data if this is a GAIA validation directory
        self._load_benchmark_data(data_path)

    def _load_benchmark_data(self, data_path) -> None:
        """Load GAIA-specific data and configuration"""
        try:
            if os.path.exists(data_path):
                with open(data_path) as f:
                    benchmark_data = [json.loads(line) for line in f.readlines()]

                print(f"Loaded {len(benchmark_data)} tasks from {data_path}")

                for line in benchmark_data:
                    task_id = line["task_id"]
                    metadata = line.get("metadata", {})
                    difficulty_level = (
                        metadata.get("Level") or metadata.get("level") or 0
                    )
                    if difficulty_level in self.DIFFICULTY_LEVELS:
                        self.task_difficulty_map[task_id] = difficulty_level

                level_counts = {
                    level: sum(
                        1 for v in self.task_difficulty_map.values() if v == level
                    )
                    for level in self.DIFFICULTY_LEVELS
                }
                print(f"Difficulty level distribution: {level_counts}")

        except Exception as e:
            print(f"Warning: Could not load GAIA data: {e}")

    def _update_difficulty_stats(
        self, stats: GAIATaskStats, task_id: str, is_correct: bool
    ) -> None:
        """Update difficulty level statistics for a task"""
        if task_id not in self.task_difficulty_map:
            return
        difficulty_level = self.task_difficulty_map[task_id]
        if difficulty_level == 1:
            stats.level1_completed += 1
            if is_correct:
                stats.level1_correct += 1
        elif difficulty_level == 2:
            stats.level2_completed += 1
            if is_correct:
                stats.level2_correct += 1
        elif difficulty_level == 3:
            stats.level3_completed += 1
            if is_correct:
                stats.level3_correct += 1

    def analyze_run_directory(
        self, run_dir: str, task_id_pattern: str
    ) -> GAIATaskStats:
        """Analyze a single run directory and return statistics (GAIA-specific)"""
        latest_files = self._get_latest_task_files(
            run_dir, task_id_pattern
        )  # 直接用父类的实现
        stats = GAIATaskStats(total=len(latest_files))
        completed_files = []

        for json_file in latest_files:
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                status = data.get("status", "")
                if status == "running":
                    stats.running += 1
                elif self._is_task_completed(data):
                    stats.completed += 1
                    completed_files.append(json_file)

                    judge_result = data.get("final_judge_result", None)
                    is_correct = judge_result is not None and self._is_judge_correct(
                        judge_result
                    )
                    if is_correct:
                        stats.judge_correct += 1

                    # Check if final_boxed_answer contains "No \\boxed{} content found"
                    final_boxed_answer = data.get("final_boxed_answer", "")
                    if (
                        isinstance(final_boxed_answer, str)
                        and "No \\boxed{} content found" in final_boxed_answer
                    ):
                        stats.no_boxed_found += 1

                    task_id = self._extract_task_id(
                        os.path.basename(json_file), task_id_pattern
                    )
                    if task_id:
                        self._update_difficulty_stats(stats, task_id, is_correct)

                    # Calculate turns for completed tasks
                    turns = self._calculate_turns(data)
                    if turns > 0:
                        stats.total_turns += turns
                        stats.completed_tasks_with_turns += 1
                else:
                    stats.failed += 1
            except Exception as e:
                print(f"Warning: Could not process {json_file}: {e}")
                stats.failed += 1

        stats.completed_files = completed_files
        return stats

    def run_analysis(
        self, benchmark_name_std: str, task_id_pattern: str
    ) -> GAIASummaryStats:
        """Run the complete analysis and return summary statistics"""
        self.run_dirs = self.find_run_directories()
        summary = GAIASummaryStats()
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
            stats = self.analyze_run_directory(run_dir, task_id_pattern)

            if stats.total == 0:
                print(f"{run_name}: No task files found")
                print()
                continue

            # Display run statistics in a single line
            run_info = f"[{run_name}] Completed: {stats.completed} | Running: {stats.running} | Failed: {stats.failed}"

            # Add accuracy information
            if stats.completed > 0:
                run_info += f" | Accuracy: {stats.judge_correct}/{stats.completed} ({stats.judge_accuracy:.1f}%)"

                # Add average turns information (show even if some tasks are still running)
                if stats.completed_tasks_with_turns > 0:
                    run_info += f" | Avg Turns: {stats.average_turns:.1f}"

            print(run_info)
            print()

            # Store run statistics for later display
            run_stats_list.append((run_name, stats))

            # Collect completed files for timing analysis
            all_completed_files.extend(stats.completed_files)

            # Update summary statistics
            self._update_summary_stats(summary, stats)

        # Display summary after all runs are processed
        self._display_summary(
            summary, run_stats_list, all_completed_files, benchmark_name_std
        )

        return summary

    def _update_summary_stats(
        self, summary: GAIASummaryStats, stats: GAIATaskStats
    ) -> None:
        """Update summary statistics with data from a single run"""
        summary.total_tasks += stats.total
        summary.total_completed += stats.completed
        summary.total_running += stats.running
        summary.total_failed += stats.failed
        summary.total_judge_correct += stats.judge_correct
        summary.total_no_boxed_found += stats.no_boxed_found

        # Update difficulty level summary stats
        summary.level1_completed += stats.level1_completed
        summary.level1_correct += stats.level1_correct
        summary.level2_completed += stats.level2_completed
        summary.level2_correct += stats.level2_correct
        summary.level3_completed += stats.level3_completed
        summary.level3_correct += stats.level3_correct

    def _display_summary(
        self,
        summary: GAIASummaryStats,
        run_stats_list: List[Tuple[str, GAIATaskStats]],
        completed_files: List[str],
        benchmark_name_std: str,
    ):
        """Display summary statistics"""
        print("=" * 80)
        print("SUMMARY STATISTICS")
        print("=" * 80)

        # Estimate completion time using overall progress rate
        if summary.total_completed > 0:
            num_runs = len(run_stats_list) if run_stats_list else 1
            expected_total_tasks = self.total_tasks_per_run * num_runs
            remaining_tasks = expected_total_tasks - summary.total_completed
            earliest_start = find_earliest_start_time(completed_files)
            last_end = find_latest_end_time(completed_files)
            completion_estimate = estimate_completion_time(
                expected_total_tasks, summary.total_completed, completed_files
            )

            print(
                f"Current Tasks: {summary.total_tasks} ({summary.total_completed} completed, {summary.total_running} running)"
            )
            print(f"Remaining Tasks to Complete: {remaining_tasks}")
            if earliest_start:
                elapsed_time = last_end - earliest_start
                elapsed_minutes = elapsed_time.total_seconds() / 60
                overall_rate = (
                    summary.total_completed / elapsed_minutes
                    if elapsed_minutes > 0
                    else 0
                )
                print(f"Elapsed Time: {elapsed_minutes:.1f} minutes")
                print(f"Completion Rate: {overall_rate:.2f} tasks/minute")

            print(f"Estimated Time to Complete: {completion_estimate}")

        # Display each run's correct percentage
        if run_stats_list:
            print()
            print("INDIVIDUAL RUN ACCURACIES:")
            for run_name, stats in run_stats_list:
                if stats.completed > 0:
                    accuracy_bar = create_progress_bar(stats.judge_accuracy)
                    print(
                        f"  {run_name}: {stats.judge_correct}/{stats.completed} {accuracy_bar}"
                    )

                    # Add difficulty level information for each run
                    if (
                        stats.level1_completed > 0
                        or stats.level2_completed > 0
                        or stats.level3_completed > 0
                    ):
                        # Calculate total expected tasks for each difficulty level
                        total_level1 = sum(
                            1
                            for level in self.task_difficulty_map.values()
                            if level == 1
                        )
                        total_level2 = sum(
                            1
                            for level in self.task_difficulty_map.values()
                            if level == 2
                        )
                        total_level3 = sum(
                            1
                            for level in self.task_difficulty_map.values()
                            if level == 3
                        )

                        difficulty_info = (
                            f"    L1: {stats.level1_correct}/{stats.level1_completed}/{total_level1} ({stats.level1_accuracy:.1f}%) | "
                            f"L2: {stats.level2_correct}/{stats.level2_completed}/{total_level2} ({stats.level2_accuracy:.1f}%) | "
                            f"L3: {stats.level3_correct}/{stats.level3_completed}/{total_level3} ({stats.level3_accuracy:.1f}%)"
                        )
                        print(f"    {difficulty_info}")
                        print()
                else:
                    print(
                        f"  {run_name}: {stats.judge_correct}/{stats.completed} (N/A)"
                    )

            # Display mean accuracy and standard deviation
            mean_acc, std_acc = summary.average_run_accuracy(run_stats_list)
            if mean_acc > 0:
                print()
                print(f"MEAN ACCURACY: {mean_acc:.1f}% ± {std_acc:.1f}%")

            # Display no boxed content found statistics
            if summary.total_completed > 0:
                print(
                    f"No \\boxed{{}} content found: {summary.total_no_boxed_found}/{summary.total_completed} ({summary.total_no_boxed_found / summary.total_completed * 100:.1f}%)"
                )

        # Display overall judge accuracy after individual runs
        if summary.total_completed > 0:
            print()
            accuracy_bar = create_progress_bar(summary.total_judge_accuracy)
            print(
                f"OVERALL JUDGE ACCURACY: {summary.total_judge_correct}/{summary.total_completed} {accuracy_bar}"
            )

            # Calculate and display overall average turns
            total_turns = sum(stats.total_turns for _, stats in run_stats_list)
            total_tasks_with_turns = sum(
                stats.completed_tasks_with_turns for _, stats in run_stats_list
            )
            if total_tasks_with_turns > 0:
                overall_avg_turns = total_turns / total_tasks_with_turns
                print(f"OVERALL AVERAGE TURNS: {overall_avg_turns:.1f}")

        # Display difficulty level summary if available
        if (
            summary.level1_completed > 0
            or summary.level2_completed > 0
            or summary.level3_completed > 0
        ):
            print()
            print("DIFFICULTY LEVEL SUMMARY:")
            # Calculate total expected tasks for each difficulty level
            total_level1 = sum(
                1 for level in self.task_difficulty_map.values() if level == 1
            )
            total_level2 = sum(
                1 for level in self.task_difficulty_map.values() if level == 2
            )
            total_level3 = sum(
                1 for level in self.task_difficulty_map.values() if level == 3
            )

            print(
                f"  L1: {summary.level1_correct}/{summary.level1_completed}/{total_level1} ({summary.level1_accuracy:.1f}%) | L2: {summary.level2_correct}/{summary.level2_completed}/{total_level2} ({summary.level2_accuracy:.1f}%) | L3: {summary.level3_correct}/{summary.level3_completed}/{total_level3} ({summary.level3_accuracy:.1f}%)"
            )

        print("=" * 80)
        print()
