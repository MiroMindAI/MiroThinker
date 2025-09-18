#!/usr/bin/env python3
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
import os
import re
import statistics
import sys


def detect_pass_at_k(results_dir: str) -> tuple:
    """Detect the pass_at_k value used in the results directory"""

    # Find all possible pass_at_k files
    pattern = os.path.join(
        results_dir, "run_*", "benchmark_results_pass_at_*_accuracy.txt"
    )
    all_files = glob.glob(pattern)

    if not all_files:
        print(f"No accuracy files found in {results_dir}")
        print(f"Expected pattern: {pattern}")
        return None, []

    # Extract pass_at_k value from the first file
    filename = os.path.basename(all_files[0])
    match = re.search(r"pass_at_(\d+)_accuracy\.txt", filename)

    if not match:
        print(f"Cannot extract pass_at_k from filename: {filename}")
        return None, []

    k = int(match.group(1))

    # Get all files with this k value
    accuracy_files = glob.glob(
        os.path.join(
            results_dir, "run_*", f"benchmark_results_pass_at_{k}_accuracy.txt"
        )
    )

    return k, accuracy_files


def calculate_average_scores(results_dir: str) -> dict:
    """Calculate average scores from multiple runs - automatically detect pass_at_k value"""

    # Detect pass_at_k value and corresponding files
    pass_at_k, accuracy_files = detect_pass_at_k(results_dir)

    if pass_at_k is None:
        return None

    print(f"Detected pass_at_{pass_at_k} files")
    print(f"Found {len(accuracy_files)} accuracy files")

    scores = []

    # Read each accuracy file
    for i, file_path in enumerate(sorted(accuracy_files), 1):
        try:
            with open(file_path, "r") as f:
                content = f.read().strip()
                # Remove percentage sign and convert to float
                score = float(content.replace("%", ""))
                scores.append(score)
                print(f"Run {i}: {score:.2f}%")
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            continue

    if not scores:
        print("No valid scores found")
        return None

    # Calculate statistics
    stats = {
        "pass_at_k": pass_at_k,
        "num_runs": len(scores),
        "individual_scores": scores,
        "average_score": statistics.mean(scores),
        "std_dev": statistics.stdev(scores) if len(scores) > 1 else 0,
        "min_score": min(scores),
        "max_score": max(scores),
    }

    return stats


def print_results(stats: dict):
    """Print results"""
    print("\n" + "=" * 50)
    print("EVALUATION RESULTS")
    print("=" * 50)

    print(f"Pass@{stats['pass_at_k']} Results:")
    print(f"Number of runs: {stats['num_runs']}")
    print(f"Individual scores: {[f'{s:.2f}%' for s in stats['individual_scores']]}")
    print()
    print(f"Standard deviation: {stats['std_dev']:.2f}%")
    print(f"Min score: {stats['min_score']:.2f}%")
    print(f"Max score: {stats['max_score']:.2f}%")
    print(f"Average score: {stats['average_score']:.2f}%")
    print("=" * 50)


def main():
    if len(sys.argv) < 2:
        print("Usage: python calculate_average_score.py <results_directory>")
        print("Example: python calculate_average_score.py logs/gaia-validation/mytest")
        sys.exit(1)

    results_dir = sys.argv[1]

    if not os.path.exists(results_dir):
        print(f"Results directory does not exist: {results_dir}")
        sys.exit(1)

    print(f"Analyzing results from: {results_dir}")

    stats = calculate_average_scores(results_dir)

    if stats:
        print_results(stats)

        # Save simple statistics results
        output_file = os.path.join(
            results_dir, f"average_scores_pass_at_{stats['pass_at_k']}.txt"
        )
        with open(output_file, "w") as f:
            f.write("EVALUATION RESULTS\n")
            f.write("=" * 50 + "\n")
            f.write(f"Pass@{stats['pass_at_k']} Results:\n")
            f.write(f"Number of runs: {stats['num_runs']}\n")
            f.write(
                f"Individual scores: {[f'{s:.2f}%' for s in stats['individual_scores']]}\n"
            )
            f.write(f"Standard deviation: {stats['std_dev']:.2f}%\n")
            f.write(f"Min score: {stats['min_score']:.2f}%\n")
            f.write(f"Max score: {stats['max_score']:.2f}%\n")
            f.write(f"Average score: {stats['average_score']:.2f}%\n")
            f.write("=" * 50 + "\n")

        print(f"\nResults saved to: {output_file}")
    else:
        print("Failed to calculate statistics")
        sys.exit(1)


if __name__ == "__main__":
    main()
