# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

import json
from collections import defaultdict
from pathlib import Path

from .task_logger import logger


def _get_summary_template():
    """Returns a template for the summary data structure."""
    return {
        "total_tasks": 0,
        "total_wall_time": 0.0,
        "primary_breakdown": {
            "main_agent": defaultdict(float),
            "browsing_agent": defaultdict(float),
        },
        "cross_cutting_breakdown": defaultdict(float),
        "tool_workload_breakdown": defaultdict(float),
    }


def _update_summary_data(summary_block, perf_summary, tool_workload):
    """Updates a summary block with data from a single result."""
    summary_block["total_tasks"] += 1
    summary_block["total_wall_time"] += perf_summary.get("total_wall_time", 0.0)

    # Update primary breakdown
    primary_breakdown = perf_summary.get("primary_breakdown", {})
    for agent, data in primary_breakdown.items():
        if agent in summary_block["primary_breakdown"]:
            for key, value in data.items():
                summary_block["primary_breakdown"][agent][key] += value

    # Update cross-cutting breakdown
    cross_cutting_breakdown = perf_summary.get("cross_cutting_breakdown", {})
    for key, value in cross_cutting_breakdown.items():
        summary_block["cross_cutting_breakdown"][key] += value

    # Update tool workload breakdown
    for key, value in tool_workload.items():
        summary_block["tool_workload_breakdown"][key] += value


def _calculate_averages(summary_block):
    """Calculates and adds average values to a summary block."""
    num_tasks = summary_block["total_tasks"]
    if num_tasks == 0:
        return

    summary_block["average_wall_time"] = summary_block["total_wall_time"] / num_tasks

    # Calculate averages for primary breakdown
    for agent, data in summary_block["primary_breakdown"].items():
        summary_block["primary_breakdown"][agent] = dict(data)  # Convert back to dict
        avg_data = {f"avg_{k}": v / num_tasks for k, v in data.items()}
        summary_block["primary_breakdown"][agent].update(avg_data)

    # Calculate averages for cross-cutting breakdown
    summary_block["cross_cutting_breakdown"] = dict(
        summary_block["cross_cutting_breakdown"]
    )
    avg_cross_cutting = {
        f"avg_{k}": v / num_tasks
        for k, v in summary_block["cross_cutting_breakdown"].items()
    }
    summary_block["cross_cutting_breakdown"].update(avg_cross_cutting)

    # Calculate averages for tool workload breakdown
    summary_block["tool_workload_breakdown"] = dict(
        summary_block["tool_workload_breakdown"]
    )
    avg_tool_workload = {
        f"avg_{k}": v / num_tasks
        for k, v in summary_block["tool_workload_breakdown"].items()
    }
    summary_block["tool_workload_breakdown"].update(avg_tool_workload)


def generate_summary(log_dir: Path):
    """
    Generates a summary of benchmark results by reading log files from a directory,
    calculating total and average trace data, both overall and grouped by
    final_judge_result.

    Args:
        log_dir: The directory where the individual result log files are and where
                 the summary file will be saved.
    """
    results = []
    for log_file in log_dir.glob("*.json"):
        if log_file.name == "summary.json":
            continue
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                results.append(json.load(f))
        except json.JSONDecodeError:
            logger.info(f"Warning: Could not decode JSON from {log_file}. Skipping.")
        except Exception as e:
            logger.info(f"Warning: Could not read file {log_file}: {e}. Skipping.")

    overall_summary = _get_summary_template()
    summary_by_judge = defaultdict(_get_summary_template)

    for result in results:
        trace_data = result.get("trace_data")
        if not trace_data or "performance_summary" not in trace_data:
            continue

        perf_summary = trace_data["performance_summary"]
        tool_workload = trace_data.get("tool_workload_breakdown", {})

        # Update overall summary
        _update_summary_data(overall_summary, perf_summary, tool_workload)

        # Update summary by judge result
        judge_result = result.get("final_judge_result", "unknown")
        _update_summary_data(
            summary_by_judge[judge_result], perf_summary, tool_workload
        )

    # Calculate averages for all summary blocks
    _calculate_averages(overall_summary)
    for judge_result in summary_by_judge:
        _calculate_averages(summary_by_judge[judge_result])

    summary_data = {
        "overall_summary": overall_summary,
        "summary_by_final_judge_result": dict(summary_by_judge),
    }

    summary_file = log_dir / "summary_time_cost.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=4, ensure_ascii=False)
