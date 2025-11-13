# Copyright (c) 2025 Miromind.ai
# This source code is licensed under the MIT License.

import argparse
import json
import os
from collections import Counter, defaultdict
from typing import Dict, List, Tuple


def majority_vote(
    preds: List[str], first_seen_order: Dict[str, int]
) -> Tuple[str, Dict[str, int]]:
    """
    Compute the majority-vote prediction for a list of candidate predictions.

    Tie-breaking rules (deterministic):
      1) Highest frequency wins.
      2) If there is a tie on frequency, choose the candidate that appeared earliest
         across all runs (based on the provided first_seen_order index).
      3) As a final guard (shouldn't be needed if first_seen_order is complete),
         fall back to lexicographic order.

    Returns:
      (chosen_prediction, counts_dict)
    """
    counter = Counter(preds)
    # Get the max vote count
    max_count = max(counter.values())
    # All candidates that share the max vote count
    tied = [c for c, cnt in counter.items() if cnt == max_count]

    if len(tied) == 1:
        chosen = tied[0]
    else:
        # Prefer the one seen earliest globally
        tied.sort(key=lambda x: (first_seen_order.get(x, float("inf")), x))
        chosen = tied[0]

    # Expose counts for optional debugging/inspection
    return chosen, dict(counter)


def discover_runs(results_dir: str) -> List[str]:
    """
    Discover subdirectories inside results_dir that potentially contain a
    'benchmark_results.jsonl'. We don't strictly require the subdir name to
    start with 'run_', but we sort the list to keep processing deterministic.
    """
    runs = []
    for name in sorted(os.listdir(results_dir)):
        path = os.path.join(results_dir, name)
        if os.path.isdir(path):
            fpath = os.path.join(path, "benchmark_results.jsonl")
            if os.path.isfile(fpath):
                runs.append(path)
    return runs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate multiple run_*/benchmark_results.jsonl files and produce a FutureX submission with majority voting."
    )
    parser.add_argument(
        "results_dir",
        help="Path to results dir containing run_*/benchmark_results.jsonl",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output JSONL file path (default: <results_dir>/futurex_submission.jsonl)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    results_dir = os.path.abspath(args.results_dir)
    if not os.path.isdir(results_dir):
        raise FileNotFoundError(f"Results dir not found: {results_dir}")

    output_file = (
        os.path.abspath(args.output)
        if args.output
        else os.path.join(results_dir, "futurex_submission.jsonl")
    )

    # Maps task_id -> list of predictions collected across runs
    preds_by_task: Dict[str, List[str]] = defaultdict(list)

    # Track first-seen order index for each distinct prediction string across all runs.
    # This enables deterministic tie-breaking.
    first_seen_order: Dict[str, int] = {}
    next_order_idx = 0

    runs = discover_runs(results_dir)
    if not runs:
        raise FileNotFoundError(
            f"No run directories with 'benchmark_results.jsonl' found under: {results_dir}"
        )

    total_lines = 0
    used_lines = 0

    # Read and aggregate predictions
    for run_dir in runs:
        fpath = os.path.join(run_dir, "benchmark_results.jsonl")
        print(f"Reading: {fpath}")
        with open(fpath, "r", encoding="utf-8") as fin:
            for line in fin:
                total_lines += 1
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    # Skip malformed JSON lines, but keep going
                    continue

                task_id = rec.get("task_id")
                pred = rec.get("model_boxed_answer")

                # Only accept non-empty strings; coerce to str for safety
                if task_id and pred is not None and str(pred).strip():
                    pred_str = str(pred).strip()
                    preds_by_task[task_id].append(pred_str)
                    if pred_str not in first_seen_order:
                        first_seen_order[pred_str] = next_order_idx
                        next_order_idx += 1
                    used_lines += 1

    # Write submission JSONL
    # We sort task_ids to keep output reproducible.
    num_tasks = 0
    with open(output_file, "w", encoding="utf-8") as out:
        for task_id in sorted(preds_by_task.keys()):
            voted_pred, _counts = majority_vote(
                preds_by_task[task_id], first_seen_order
            )
            out.write(
                json.dumps(
                    {"id": task_id, "prediction": voted_pred}, ensure_ascii=False
                )
                + "\n"
            )
            num_tasks += 1

    # Optional: small summary to stdout
    print(f"Collected from {len(runs)} run(s).")
    print(f"Read {total_lines} line(s), accepted {used_lines} record(s).")
    print(f"Aggregated {num_tasks} unique task_id(s).")
    print(f"✅ Submission saved to {output_file}")


if __name__ == "__main__":
    main()
