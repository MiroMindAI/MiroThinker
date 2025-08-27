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

import os
import json
import glob
import sys
from datetime import datetime
import re
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

# ============================================================================
# CONFIGURATION CONSTANTS - Edit these values as needed
# ============================================================================

# File paths for GAIA data
GAIA_VAL_DATA_PATH = "../../data/gaia-2023-validation/standardized_data.jsonl"

# Time estimation constants
DEFAULT_TASK_TIME_MINUTES = 3.5
MINUTES_PER_HOUR = 60
HOURS_PER_DAY = 24
MINUTES_PER_DAY = MINUTES_PER_HOUR * HOURS_PER_DAY

# GAIA validation expected total tasks - will be loaded from data file
GAIA_EXPECTED_TOTAL_TASKS: Optional[int] = None  # Will be dynamically loaded

# Progress bar configuration
PROGRESS_BAR_WIDTH = 20
GREEN_THRESHOLD = 80
YELLOW_THRESHOLD = 60
ORANGE_THRESHOLD = 40

# Task ID extraction patterns
TASK_ID_PATTERN = r"task_([^_]+(?:-[^_]+)*)"

# Difficulty level mapping (from GAIA metadata)
DIFFICULTY_LEVELS = [1, 2, 3]

# GAIA validation directory patterns
GAIA_VALIDATION_DIR_PATTERN = "gaia-validation"

# Judge result patterns for correctness
CORRECT_RESULTS = ["CORRECT", "SUCCESS"]
SUCCESS_PATTERNS = ["PASS_AT_K_SUCCESS"]


# ============================================================================


def validate_gaia_data_file() -> bool:
    """Validate that the GAIA data file is properly formatted"""
    try:
        if not os.path.exists(GAIA_VAL_DATA_PATH):
            print(f"Error: GAIA validation data file not found at {GAIA_VAL_DATA_PATH}")
            return False

        with open(GAIA_VAL_DATA_PATH, "r") as f:
            lines = f.readlines()

        if not lines:
            print(f"Error: GAIA validation data file is empty at {GAIA_VAL_DATA_PATH}")
            return False

        # Check first few lines for valid JSON
        for i, line in enumerate(lines[:5]):
            line = line.strip()
            if not line:
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError as e:
                print(f"Error: Invalid JSON in line {i + 1} of GAIA data file: {e}")
                return False

        return True
    except Exception as e:
        print(f"Error validating GAIA data file: {e}")
        return False


def load_gaia_expected_total_tasks() -> Optional[int]:
    """Load the expected total number of tasks from GAIA validation data file"""
    global GAIA_EXPECTED_TOTAL_TASKS

    if GAIA_EXPECTED_TOTAL_TASKS is not None:
        return GAIA_EXPECTED_TOTAL_TASKS

    try:
        if os.path.exists(GAIA_VAL_DATA_PATH):
            # Validate the file format first
            if not validate_gaia_data_file():
                print(
                    f"Error: GAIA validation data file format is invalid at {GAIA_VAL_DATA_PATH}"
                )
                return None

            with open(GAIA_VAL_DATA_PATH, "r") as f:
                # Count the number of lines in the JSONL file
                task_count = sum(1 for line in f if line.strip())

            if task_count == 0:
                print(
                    f"Error: GAIA validation data file is empty at {GAIA_VAL_DATA_PATH}"
                )
                return None

            print(f"Loaded {task_count} tasks from GAIA validation data file")
            GAIA_EXPECTED_TOTAL_TASKS = task_count
            return task_count
        else:
            print(f"Error: GAIA validation data file not found at {GAIA_VAL_DATA_PATH}")
            print(
                "Please ensure the GAIA validation data file exists and the path is correct."
            )
            return None
    except PermissionError as e:
        print(f"Error: Permission denied reading GAIA validation data file: {e}")
        return None
    except UnicodeDecodeError as e:
        print(f"Error: GAIA validation data file contains invalid characters: {e}")
        return None
    except Exception as e:
        print(f"Error: Could not load GAIA expected total tasks: {e}")
        return None


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

    # Difficulty level tracking
    level1_completed: int = 0
    level1_correct: int = 0
    level2_completed: int = 0
    level2_correct: int = 0
    level3_completed: int = 0
    level3_correct: int = 0

    def __post_init__(self):
        if self.completed_files is None:
            self.completed_files = []

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


@dataclass
class SummaryStats:
    """Summary statistics across all runs"""

    total_tasks: int = 0
    total_completed: int = 0
    total_running: int = 0
    total_failed: int = 0
    total_judge_correct: int = 0

    # Difficulty level summary stats
    level1_completed: int = 0
    level1_correct: int = 0
    level2_completed: int = 0
    level2_correct: int = 0
    level3_completed: int = 0
    level3_correct: int = 0

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
    ) -> float:
        """Calculate average accuracy across individual runs"""
        if not run_stats_list:
            return 0.0

        total_accuracy = 0.0
        valid_runs = 0

        for run_name, stats in run_stats_list:
            if stats.completed > 0:
                total_accuracy += stats.judge_accuracy
                valid_runs += 1

        return total_accuracy / valid_runs if valid_runs > 0 else 0.0

    @property
    def total_completion_rate(self) -> float:
        """Calculate overall completion rate percentage"""
        return (
            (self.total_completed / self.total_tasks * 100)
            if self.total_tasks > 0
            else 0.0
        )

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
    """Estimate completion time based on overall progress rate from all completed tasks"""
    if completed_tasks == 0:
        return "Cannot estimate (no completed tasks)"

    # Check if all tasks are completed
    if completed_tasks >= total_tasks:
        return "All tasks completed"

    remaining_tasks = total_tasks - completed_tasks

    # Use overall completion rate from all successfully completed tasks
    earliest_start = find_earliest_start_time(completed_files)
    current_time = datetime.now()

    if earliest_start is None:
        # Fallback to default estimation if no valid timing data
        estimated_minutes = remaining_tasks * DEFAULT_TASK_TIME_MINUTES
    else:
        # Calculate overall elapsed time
        elapsed_time = current_time - earliest_start
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


class ProgressChecker:
    """Main class for checking GAIA benchmark progress"""

    def __init__(self, target_path: str, verbose: bool = False):
        self.target_path = target_path
        self.verbose = verbose
        self.run_dirs: List[str] = []

        # GAIA-specific data
        self.is_gaia_validation = False

        # Difficulty level mapping
        self.task_difficulty_map: Dict[str, int] = {}

        # Load GAIA data if this is a GAIA validation directory
        self._load_gaia_data()

    def _load_gaia_data(self) -> None:
        """Load GAIA-specific data and configuration"""
        try:
            # Check if this looks like a GAIA validation directory
            if GAIA_VALIDATION_DIR_PATTERN in self.target_path.lower():
                self.is_gaia_validation = True

                if self.verbose:
                    print(f"Detected GAIA validation directory: {self.target_path}")

                # Load GAIA-Val data
                if os.path.exists(GAIA_VAL_DATA_PATH):
                    with open(GAIA_VAL_DATA_PATH) as f:
                        gaia_val_data = [json.loads(line) for line in f.readlines()]

                    if self.verbose:
                        print(
                            f"Loaded {len(gaia_val_data)} tasks from GAIA validation data"
                        )

                    # Categorize by difficulty level
                    for line in gaia_val_data:
                        task_id = line["task_id"]
                        difficulty_level = line.get("metadata", {}).get("Level", 0)

                        # Store difficulty level mapping for ALL tasks
                        if difficulty_level in DIFFICULTY_LEVELS:
                            self.task_difficulty_map[task_id] = difficulty_level

                    if self.verbose:
                        level_counts = {}
                        for level in DIFFICULTY_LEVELS:
                            level_counts[level] = sum(
                                1
                                for level_value in self.task_difficulty_map.values()
                                if level_value == level
                            )
                        print(f"Difficulty level distribution: {level_counts}")

                    # Load expected total tasks from the data file
                    load_gaia_expected_total_tasks()

        except Exception as e:
            print(f"Warning: Could not load GAIA data: {e}")
            self.is_gaia_validation = False

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
        match = re.match(TASK_ID_PATTERN, filename)
        return match.group(1) if match else None

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
                    if self.verbose:
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

    def _update_difficulty_stats(
        self, stats: TaskStats, task_id: str, is_correct: bool
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

    def analyze_run_directory(self, run_dir: str) -> TaskStats:
        """Analyze a single run directory and return statistics"""
        latest_files = self._get_latest_task_files(run_dir)

        stats = TaskStats(total=len(latest_files))
        completed_files = []  # Track completed files for timing analysis

        # Show progress for large directories
        show_progress = len(latest_files) > 50
        if show_progress:
            print(f"  Processing {len(latest_files)} files...", end="", flush=True)

        for i, json_file in enumerate(latest_files):
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

                    # Track difficulty level statistics
                    task_id = self._extract_task_id(os.path.basename(json_file))
                    if task_id:
                        self._update_difficulty_stats(stats, task_id, is_correct)
                else:
                    stats.failed += 1

            except json.JSONDecodeError as e:
                # Skip files that are being written or corrupted
                if "Expecting value" in str(e) or "line 1 column 1" in str(e):
                    continue  # Skip corrupted/empty files
                print(f"Warning: Invalid JSON in {os.path.basename(json_file)}: {e}")
                stats.failed += 1
            except IOError as e:
                print(f"Warning: Could not read {os.path.basename(json_file)}: {e}")
                stats.failed += 1
            except Exception as e:
                print(
                    f"Warning: Unexpected error processing {os.path.basename(json_file)}: {e}"
                )
                stats.failed += 1

            # Update progress for large directories
            if show_progress and (i + 1) % 10 == 0:
                print(".", end="", flush=True)

        # Complete progress display
        if show_progress:
            print(" done")

        # Store completed files in stats for timing analysis
        stats.completed_files = completed_files
        return stats

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

            # Store run statistics for later display
            run_stats_list.append((run_name, stats))

            # Collect completed files for timing analysis
            all_completed_files.extend(stats.completed_files)

            # Update summary statistics
            self._update_summary_stats(summary, stats, run_dir)

        # Display summary after all runs are processed
        self._display_summary(summary, run_stats_list, all_completed_files)

        return summary

    def _update_summary_stats(
        self, summary: SummaryStats, stats: TaskStats, run_dir: str
    ) -> None:
        """Update summary statistics with data from a single run"""
        summary.total_tasks += stats.total
        summary.total_completed += stats.completed
        summary.total_running += stats.running
        summary.total_failed += stats.failed
        summary.total_judge_correct += stats.judge_correct

        # Update difficulty level summary stats
        summary.level1_completed += stats.level1_completed
        summary.level1_correct += stats.level1_correct
        summary.level2_completed += stats.level2_completed
        summary.level2_correct += stats.level2_correct
        summary.level3_completed += stats.level3_completed
        summary.level3_correct += stats.level3_correct

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

        # Estimate completion time using overall progress rate
        if summary.total_completed > 0:
            # Use expected total tasks for GAIA validation (loaded from data file)
            if self.is_gaia_validation:
                base_expected_tasks = load_gaia_expected_total_tasks()
                if base_expected_tasks is None:
                    print(
                        "Cannot calculate completion estimates: GAIA validation data file not found or invalid"
                    )
                    print(
                        f"Current Tasks: {summary.total_tasks} ({summary.total_completed} completed, {summary.total_running} running)"
                    )
                    return
                num_runs = len(run_stats_list) if run_stats_list else 1
                expected_total_tasks = base_expected_tasks * num_runs
            else:
                expected_total_tasks = summary.total_tasks

            remaining_tasks = expected_total_tasks - summary.total_completed
            earliest_start = find_earliest_start_time(completed_files)
            completion_estimate = estimate_completion_time(
                expected_total_tasks, summary.total_completed, completed_files
            )

            if self.is_gaia_validation:
                base_expected_tasks = load_gaia_expected_total_tasks()
                num_runs = len(run_stats_list) if run_stats_list else 1
                print(
                    f"Total Expected Tasks: {expected_total_tasks} ({base_expected_tasks} tasks × {num_runs} runs)"
                )
            else:
                print(f"Total Expected Tasks: {expected_total_tasks}")
            print(
                f"Current Tasks: {summary.total_tasks} ({summary.total_completed} completed, {summary.total_running} running)"
            )
            print(f"Remaining Tasks to Complete: {remaining_tasks}")
            if earliest_start:
                elapsed_time = datetime.now() - earliest_start
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

        # Display overall judge accuracy after individual runs
        if summary.total_completed > 0:
            print()
            accuracy_bar = create_progress_bar(summary.total_judge_accuracy)
            print(
                f"OVERALL JUDGE ACCURACY: {summary.total_judge_correct}/{summary.total_completed} {accuracy_bar}"
            )

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


def main():
    """Main entry point"""
    # Check for help option
    if len(sys.argv) > 1 and sys.argv[1] in ["-h", "--help"]:
        print(__doc__)
        print("\nUsage:")
        print("  python check_progress_gaia-validation.py [path]")
        print("\nArguments:")
        print("  path    Path to GAIA benchmark directory")
        print("\nOptions:")
        print("  -v, --verbose    Enable verbose output")
        print("\nExamples:")
        print("  python check_progress_gaia-validation.py ./gaia-validation/run_1")
        print("  python check_progress_gaia-validation.py /path/to/gaia/benchmark/runs")
        print("  python check_progress_gaia-validation.py -v ./gaia-validation/run_1")
        sys.exit(0)

    # Parse command line arguments
    verbose = False
    target_path = None

    for arg in sys.argv[1:]:
        if arg in ["-v", "--verbose"]:
            verbose = True
        elif not arg.startswith("-"):
            target_path = arg
            break

    if not target_path:
        print("Error: Please provide a target path")
        print("Use -h or --help for usage information")
        sys.exit(1)

    try:
        # Create progress checker and run analysis
        checker = ProgressChecker(target_path, verbose=verbose)
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
