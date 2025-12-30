# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from mcp.server.fastmcp import FastMCP

# Configure logging
logger = logging.getLogger("miroflow")

# Initialize FastMCP server
mcp = FastMCP("task_planner")

# Configuration
TODO_DATA_DIR = os.environ.get("TODO_DATA_DIR", "../../logs/todo_lists")

# TASK_ID is required for task isolation
# Without TASK_ID, task planner operations will fail
TASK_ID = os.environ.get("TASK_ID")
if not TASK_ID:
    raise ValueError(
        "TASK_ID environment variable is required for task_planner tool. "
        "This tool must have a unique task identifier to prevent data conflicts in concurrent execution."
    )

TODO_DATA_FILE = os.path.join(TODO_DATA_DIR, f"todos_{TASK_ID}.json")

# Ensure data directory exists
Path(TODO_DATA_DIR).mkdir(parents=True, exist_ok=True)


def load_todos() -> List[Dict[str, Any]]:
    """Load task plan from the JSON file."""
    if not os.path.exists(TODO_DATA_FILE):
        return []

    try:
        with open(TODO_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load task plan: {str(e)}")
        return []


def save_todos(todos: List[Dict[str, Any]]) -> bool:
    """Save task plan to the JSON file."""
    try:
        with open(TODO_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(todos, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Failed to save task plan: {str(e)}")
        return False


def format_todos_as_markdown(todos: List[Dict[str, Any]], message: str = "") -> str:
    """
    Format task plan as markdown checklist.

    Args:
        todos: List of task items
        message: Optional message to display at the top

    Returns:
        Markdown formatted string
    """
    # Calculate statistics
    total = len(todos)
    completed = sum(1 for t in todos if t.get("completed", False))
    pending = total - completed

    # Build markdown
    lines = []
    if message:
        lines.append(f"{message}\n")

    lines.append("# Task Plan\n")
    lines.append(f"Total: {total} | Pending: {pending} | Completed: {completed}\n")
    lines.append("")

    if not todos:
        lines.append("No tasks planned yet.")
    else:
        for todo in todos:
            checkbox = "[x]" if todo.get("completed", False) else "[ ]"
            title = todo["title"]
            todo_id = todo["id"][:8]  # Show first 8 chars of ID
            lines.append(f"- {checkbox} {title} ({todo_id})")

    return "\n".join(lines)


@mcp.tool()
async def add_todo(titles: List[str]) -> str:
    """
    Create a task plan by adding one or more task items.

    CRITICAL: Before starting to work on ANY task, you MUST first create a complete task plan.
    This is the foundation of effective task execution:
    - Break down the main goal into clear, actionable steps
    - Identify all necessary subtasks upfront
    - Create a roadmap that guides your work
    - Ensure nothing is overlooked or forgotten

    Good task planning prevents confusion and ensures systematic progress toward your goal.

    Args:
        titles: List of task item titles. For example:
                - Single task: ["Complete project report"]
                - Multiple tasks: ["Complete project report", "Fix bug #123", "Update documentation"]
                - Complex project: ["Research requirements", "Design architecture", "Implement core features", "Write tests", "Document API"]

    Returns:
        Markdown formatted string showing the success message and current task plan.
    """
    if not titles:
        return "❌ Error: Task titles list cannot be empty."

    # Filter out empty titles
    title_list = [t.strip() for t in titles if t and t.strip()]

    if not title_list:
        return "❌ Error: No valid task titles provided."

    todos = load_todos()
    added_todos = []

    # Add all tasks
    for title in title_list:
        new_todo = {
            "id": str(uuid4()),
            "title": title,
            "completed": False,
            "created_at": datetime.now().isoformat(),
        }
        todos.append(new_todo)
        added_todos.append(title)

    if not save_todos(todos):
        return "❌ Error: Failed to save task plan."

    # Build success message
    if len(added_todos) == 1:
        message = f'✅ Task added: "{added_todos[0]}"'
    else:
        message = f"✅ Added {len(added_todos)} tasks:\n" + "\n".join(
            f"  - {t}" for t in added_todos
        )

    return format_todos_as_markdown(todos, message)


@mcp.tool()
async def list_todos() -> str:
    """
    Display the complete task plan with all items and their status.

    Use this to review your overall progress, see what's done and what remains,
    and understand where you are in the execution of your plan.

    Returns:
        Markdown formatted string showing all tasks with their completion status.
    """
    todos = load_todos()
    return format_todos_as_markdown(todos)


@mcp.tool()
async def complete_todo(todo_ids: List[str]) -> str:
    """
    Mark one or more tasks as completed in your plan.

    Use this after finishing a task to track your progress and maintain an
    accurate view of what's done and what's remaining.

    Args:
        todo_ids: List of task IDs to mark as completed (full ID or first 8 characters).
                  For example: ["a7f3b2c1"] or ["a7f3b2c1", "b8e4c3d2"]

    Returns:
        Markdown formatted string showing the success message and updated task plan.
    """
    if not todo_ids:
        return "❌ Error: Task IDs list cannot be empty."

    # Filter out empty IDs
    id_list = [tid.strip() for tid in todo_ids if tid and tid.strip()]

    if not id_list:
        return "❌ Error: No valid task IDs provided."

    todos = load_todos()
    completed_todos = []
    not_found_ids = []

    # Complete all matching tasks
    for todo_id in id_list:
        found = False
        for todo in todos:
            if todo["id"] == todo_id or todo["id"].startswith(todo_id):
                if not todo.get(
                    "completed", False
                ):  # Only mark if not already completed
                    todo["completed"] = True
                    completed_todos.append(todo["title"])
                found = True
                break
        if not found:
            not_found_ids.append(todo_id)

    if not completed_todos and not_found_ids:
        return f"❌ Error: Task IDs not found: {', '.join(not_found_ids)}"

    if not save_todos(todos):
        return "❌ Error: Failed to save changes."

    # Build success message
    if len(completed_todos) == 1:
        message = f'✅ Completed: "{completed_todos[0]}"'
    else:
        message = f"✅ Completed {len(completed_todos)} tasks:\n" + "\n".join(
            f"  - {t}" for t in completed_todos
        )

    if not_found_ids:
        message += f'\n⚠️  Not found: {", ".join(not_found_ids)}'

    return format_todos_as_markdown(todos, message)


@mcp.tool()
async def delete_todo(todo_ids: List[str]) -> str:
    """
    Remove one or more tasks from your plan.

    Use this to adjust your plan when tasks become irrelevant, duplicated,
    or no longer needed. This helps keep your plan focused and accurate.

    Args:
        todo_ids: List of task IDs to remove (full ID or first 8 characters).
                  For example: ["a7f3b2c1"] or ["a7f3b2c1", "b8e4c3d2"]

    Returns:
        Markdown formatted string showing the success message and remaining task plan.
    """
    if not todo_ids:
        return "❌ Error: Task IDs list cannot be empty."

    # Filter out empty IDs
    id_list = [tid.strip() for tid in todo_ids if tid and tid.strip()]

    if not id_list:
        return "❌ Error: No valid task IDs provided."

    todos = load_todos()
    deleted_todos = []
    not_found_ids = []
    ids_to_delete = set()

    # Find all tasks to delete
    for todo_id in id_list:
        found = False
        for todo in todos:
            if todo["id"] == todo_id or todo["id"].startswith(todo_id):
                deleted_todos.append(todo["title"])
                ids_to_delete.add(todo["id"])
                found = True
                break
        if not found:
            not_found_ids.append(todo_id)

    if not deleted_todos and not_found_ids:
        return f"❌ Error: Task IDs not found: {', '.join(not_found_ids)}"

    # Remove the tasks
    todos = [t for t in todos if t["id"] not in ids_to_delete]

    if not save_todos(todos):
        return "❌ Error: Failed to save changes."

    # Build success message
    if len(deleted_todos) == 1:
        message = f'🗑️ Deleted: "{deleted_todos[0]}"'
    else:
        message = f"🗑️ Deleted {len(deleted_todos)} tasks:\n" + "\n".join(
            f"  - {t}" for t in deleted_todos
        )

    if not_found_ids:
        message += f'\n⚠️  Not found: {", ".join(not_found_ids)}'

    return format_todos_as_markdown(todos, message)


if __name__ == "__main__":
    mcp.run(transport="stdio")
