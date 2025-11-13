# Copyright (c) 2025 Miromind.ai
# This source code is licensed under the MIT License.

"""
GAIA-Text-103 Task Grader

This script:
1. Loads extracted GAIA-Text-103 tasks from the extraction directory
2. Grades each task using the GAIA-Text-103 evaluator (LLM judgement)
3. Updates the original task files with grading results

Usage:
    uv run benchmarks/subset_extraction/gaia-text-103-grader.py /path/to/extraction/directory
"""

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

# Add the benchmarks directory to the path to import evaluators
sys.path.append(str(Path(__file__).parent.parent))
from evaluators.eval_utils import verify_answer_gaia_validation_text_103


@dataclass
class GradingResult:
    """Result of grading a single task"""

    task_id: str
    run_name: str
    file_path: str
    question: str
    ground_truth: str
    predicted_answer: str
    judge_result: str
    judge_type: str = "gaia_validation_text_103_scorer"
    grading_time: float = 0.0
    error_message: str = ""


class GAIAText103Grader:
    """Grader for GAIA-Text-103 tasks using LLM judgement"""

    def __init__(self, extraction_dir: str):
        """
        Initialize the grader

        Args:
            extraction_dir: Directory containing extracted GAIA-Text-103 tasks
        """
        self.extraction_dir = Path(extraction_dir)
        self.results: List[GradingResult] = []
        self.stats = {
            "total_tasks": 0,
            "graded_tasks": 0,
            "errors": 0,
            "total_grading_time": 0.0,
        }

    def find_task_files(self) -> List[Path]:
        """Find all task JSON files in the extraction directory"""
        task_files = []

        # Recursively search for task files
        for root, dirs, files in os.walk(self.extraction_dir):
            for file in files:
                if file.startswith("task_") and file.endswith(".json"):
                    task_files.append(Path(root) / file)

        return sorted(task_files)

    def extract_task_info(self, task_file: Path) -> Optional[Dict]:
        """Extract task information from a task file"""
        try:
            with open(task_file, "r", encoding="utf-8") as f:
                task_data = json.load(f)

            # Check if task has already been graded with our specific scorer
            if task_data.get("judge_type") == "gaia_validation_text_103_scorer":
                print(f"Skipping already graded task: {task_file.name}")
                return None

            # Extract basic information
            task_info = {
                "task_id": task_data.get("task_id", ""),
                "run_name": task_data.get("run_name", ""),
                "file_path": str(task_file),
                "question": task_data.get("input", {}).get("task_description", ""),
                "ground_truth": task_data.get("ground_truth", ""),
                "predicted_answer": task_data.get("final_boxed_answer", ""),
            }

            # Validate required fields
            if not all(
                [
                    task_info["question"],
                    task_info["ground_truth"],
                    task_info["predicted_answer"],
                ]
            ):
                print(f"Warning: Missing required fields in {task_file}")
                print(f"  question: {task_info['question']}")
                print(f"  ground_truth: {task_info['ground_truth']}")
                print(f"  predicted_answer: {task_info['predicted_answer']}")
                return None

            return task_info

        except Exception as e:
            print(f"Error reading task file {task_file}: {e}")
            return None

    async def grade_single_task(self, task_info: Dict) -> GradingResult:
        """Grade a single task using GAIA-Text-103 evaluator"""
        start_time = time.time()

        result = GradingResult(
            task_id=task_info["task_id"],
            run_name=task_info["run_name"],
            file_path=task_info["file_path"],
            question=task_info["question"],
            ground_truth=task_info["ground_truth"],
            predicted_answer=task_info["predicted_answer"],
            judge_result="",
            judge_type="gaia_validation_text_103_scorer",
        )

        try:
            # Use the GAIA-Text-103 evaluator
            judge_result = await verify_answer_gaia_validation_text_103(
                question=task_info["question"],
                target=task_info["ground_truth"],
                predicted_answer=task_info["predicted_answer"],
            )

            result.judge_result = judge_result
            result.grading_time = time.time() - start_time

            print(
                f"Task {task_info['task_id']} ({task_info['run_name']}): {judge_result}"
            )

        except Exception as e:
            result.error_message = str(e)
            result.judge_result = "ERROR"
            result.grading_time = time.time() - start_time
            self.stats["errors"] += 1
            print(f"Error grading task {task_info['task_id']}: {e}")

        return result

    async def grade_all_tasks(self, max_concurrent: int = 5) -> List[GradingResult]:
        """Grade all tasks with concurrent processing"""
        task_files = self.find_task_files()
        print(f"Found {len(task_files)} task files to grade")

        # Extract task information
        task_infos = []
        for task_file in task_files:
            task_info = self.extract_task_info(task_file)
            if task_info:
                task_infos.append(task_info)

        self.stats["total_tasks"] = len(task_infos)
        print(f"Extracted {len(task_infos)} valid tasks for grading")

        if not task_infos:
            print("No valid tasks found for grading")
            return []

        # Grade tasks with concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)

        async def grade_with_semaphore(task_info):
            async with semaphore:
                return await self.grade_single_task(task_info)

        # Create tasks for concurrent execution
        tasks = [grade_with_semaphore(task_info) for task_info in task_infos]

        # Execute all grading tasks
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions and collect valid results
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"Exception in task {i}: {result}")
                self.stats["errors"] += 1
            else:
                valid_results.append(result)
                self.stats["graded_tasks"] += 1
                self.stats["total_grading_time"] += result.grading_time

        self.results = valid_results
        return valid_results

    def update_original_files(self):
        """Update original task files with grading results"""
        updated_count = 0

        for result in self.results:
            try:
                # Read original file
                with open(result.file_path, "r", encoding="utf-8") as f:
                    task_data = json.load(f)

                # Add grading information
                task_data["final_judge_result"] = result.judge_result
                task_data["judge_type"] = result.judge_type
                task_data["grading_time"] = result.grading_time

                if result.error_message:
                    task_data["grading_error"] = result.error_message

                # Write back to file
                with open(result.file_path, "w", encoding="utf-8") as f:
                    json.dump(task_data, f, indent=2, ensure_ascii=False)

                updated_count += 1

            except Exception as e:
                print(f"Error updating file {result.file_path}: {e}")

        print(f"Updated {updated_count} original task files with grading results")

    def print_summary(self):
        """Print grading summary"""
        print("\n" + "=" * 60)
        print("GAIA-Text-103 Grading Summary")
        print("=" * 60)

        print(f"Total tasks found: {self.stats['total_tasks']}")
        print(f"Successfully graded: {self.stats['graded_tasks']}")
        print(f"Errors: {self.stats['errors']}")
        print("=" * 60)


async def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description="Grade GAIA-Text-103 tasks using LLM judgement"
    )
    parser.add_argument(
        "extraction_dir", help="Directory containing extracted GAIA-Text-103 tasks"
    )
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=5,
        help="Maximum number of concurrent grading tasks (default: 5)",
    )
    args = parser.parse_args()

    # Validate input directory
    if not os.path.exists(args.extraction_dir):
        print(f"Error: Extraction directory not found: {args.extraction_dir}")
        return 1

    print(f"Extraction directory: {args.extraction_dir}")
    print(f"Max concurrent tasks: {args.max_concurrent}")
    print()

    # Create grader and run grading
    grader = GAIAText103Grader(args.extraction_dir)

    try:
        print("Starting grading process...")
        results = await grader.grade_all_tasks(max_concurrent=args.max_concurrent)

        if results:
            # Update original files only
            grader.update_original_files()

            # Print summary
            grader.print_summary()

            print("\n✅ Grading completed successfully!")
            print("📝 Original task files updated with grading results")
        else:
            print("❌ No tasks were graded successfully")
            return 1

    except KeyboardInterrupt:
        print("\nGrading interrupted by user")
        return 1
    except Exception as e:
        print(f"Error during grading: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
