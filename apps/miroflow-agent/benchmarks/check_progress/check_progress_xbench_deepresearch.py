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
import os

from common import ProgressChecker

# Benchmark configuration
FILENAME = os.path.basename(__file__)
BENCHMARK_NAME = "xbench_deepresearch"
BENCHMARK_NAME_STD = "XBench-DeepResearch"
TASKS_PER_RUN = 100
DATA_PATH = f"../../data/{BENCHMARK_NAME}/standardized_data.jsonl"
TASK_ID_PATTERN = r"task_([a-f0-9]+)"


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
