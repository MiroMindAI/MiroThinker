# Copyright (c) 2025 Miromind.ai
# This source code is licensed under the MIT License.

"""
GAIA to Text-103 Task Copier

This script:
1. Loads GAIA validation logs from a specified directory
2. Identifies tasks that belong to GAIA-Text-103 dataset
3. Copies those tasks to a new directory structure maintaining the original layout
"""

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Set


class GAIAtoText103Copier:
    """Copy GAIA-Text-103 tasks from GAIA validation logs"""

    def __init__(self, gaia_text_103_data_path: str, output_dir: str):
        """
        Initialize the copier

        Args:
            gaia_text_103_data_path: Path to GAIA-Text-103 standardized data file
            output_dir: Directory to save copied tasks
        """
        self.gaia_text_103_data_path = gaia_text_103_data_path
        self.output_dir = Path(output_dir)
        self.gaia_text_103_task_ids: Set[str] = set()
        self.copied_count = 0

        # Load GAIA-Text-103 task IDs
        self._load_gaia_text_103_tasks()

    def _load_gaia_text_103_tasks(self):
        """Load task IDs from GAIA-Text-103 dataset"""
        print(f"Loading GAIA-Text-103 task IDs from {self.gaia_text_103_data_path}")

        if not os.path.exists(self.gaia_text_103_data_path):
            raise FileNotFoundError(
                f"GAIA-Text-103 data file not found: {self.gaia_text_103_data_path}"
            )

        with open(self.gaia_text_103_data_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    task_data = json.loads(line)
                    task_id = task_data.get("task_id")
                    if task_id:
                        self.gaia_text_103_task_ids.add(task_id)

        print(f"Loaded {len(self.gaia_text_103_task_ids)} GAIA-Text-103 task IDs")

    def copy_gaia_text_103_tasks(self, gaia_logs_dir: str) -> int:
        """
        Copy GAIA-Text-103 tasks from GAIA validation logs

        Args:
            gaia_logs_dir: Directory containing GAIA validation logs

        Returns:
            Number of copied tasks
        """
        print(f"Copying GAIA-Text-103 tasks from {gaia_logs_dir}")

        # Find all task JSON files in the logs directory (including in run subdirectories)
        task_files = []
        for root, dirs, files in os.walk(gaia_logs_dir):
            for file in files:
                if file.startswith("task_") and file.endswith(".json"):
                    task_files.append(os.path.join(root, file))

        print(f"Found {len(task_files)} task files to process")

        copied_count = 0

        for task_file in task_files:
            try:
                filename = os.path.basename(task_file)
                # Extract task ID from filename like: task_5188369a-3bbe-43d8-8b94-11558f909a08_attempt_1_format_retry_0_2025-08-06T21-14-23-770872Z.json
                task_id = (
                    filename.split("_")[1]
                    if filename.startswith("task_") and "_" in filename
                    else ""
                )

                if task_id and task_id in self.gaia_text_103_task_ids:
                    # This is a GAIA-Text-103 task, copy it
                    copied_count += 1

                    # Preserve the original directory structure
                    # Get the relative path from the original directory
                    original_dir = os.path.dirname(gaia_logs_dir)
                    relative_path = os.path.relpath(task_file, original_dir)

                    # Create the same directory structure in the output
                    output_file = self.output_dir / relative_path
                    output_file.parent.mkdir(parents=True, exist_ok=True)

                    # Copy the file
                    shutil.copy2(task_file, output_file)

                    if copied_count % 50 == 0:
                        print(f"Copied {copied_count} tasks...")

            except Exception as e:
                print(f"Error processing {task_file}: {e}")
                continue

        print(f"Successfully copied {copied_count} GAIA-Text-103 tasks")
        self.copied_count = copied_count
        return copied_count

    def print_summary(self):
        """Print copying summary to console"""
        print("\n" + "=" * 60)
        print("GAIA-Text-103 Task Copying Summary")
        print("=" * 60)
        print(f"Total Tasks Copied: {self.copied_count}")
        print(f"Output Directory: {self.output_dir}")
        print("=" * 60)


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description="Copy GAIA-Text-103 tasks from GAIA validation logs"
    )
    parser.add_argument(
        "gaia_logs_dir", help="Directory containing GAIA validation logs"
    )
    parser.add_argument(
        "--gaia_text_103_data",
        default="../../data/gaia-2023-validation-text-103/standardized_data.jsonl",
        help="Path to GAIA-Text-103 standardized data file",
    )
    parser.add_argument(
        "--output-dir",
        help="Output directory for copied tasks (default: side by side with gaia-validation)",
    )

    args = parser.parse_args()

    # Set default output directory side by side with gaia-validation
    if not args.output_dir:
        gaia_logs_path = Path(args.gaia_logs_dir)
        # If the input is a gaia-validation directory, create gaia-text-103-extraction next to it
        if gaia_logs_path.name == "gaia-validation":
            args.output_dir = str(gaia_logs_path.parent / "gaia-text-103-extraction")
        else:
            # Otherwise, create in the same directory as the input
            args.output_dir = str(gaia_logs_path.parent / "gaia-text-103-extraction")

    # Validate inputs
    if not os.path.exists(args.gaia_logs_dir):
        print(f"Error: GAIA logs directory not found: {args.gaia_logs_dir}")
        return 1

    if not os.path.exists(args.gaia_text_103_data):
        print(f"Error: GAIA-Text-103 data file not found: {args.gaia_text_103_data}")
        return 1

    print(f"Input GAIA logs directory: {args.gaia_logs_dir}")
    print(f"Output directory: {args.output_dir}")
    print(f"GAIA-Text-103 data file: {args.gaia_text_103_data}")
    print()

    try:
        # Initialize copier
        copier = GAIAtoText103Copier(args.gaia_text_103_data, args.output_dir)

        # Copy tasks
        copied_count = copier.copy_gaia_text_103_tasks(args.gaia_logs_dir)

        if copied_count == 0:
            print("No GAIA-Text-103 tasks found in the logs directory")
            return 0

        # Print summary
        copier.print_summary()

        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)
