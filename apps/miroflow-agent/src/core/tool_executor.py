# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

"""
Tool executor module for handling tool call execution.

This module provides the ToolExecutor class that manages tool call execution,
including argument fixing, duplicate detection, result processing, and error handling.
"""

import json
import logging
import os
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from miroflow_tools.manager import ToolManager

from ..io.output_formatter import OutputFormatter
from ..logging.task_logger import TaskLog, get_utc_plus_8_time
from .stream_handler import StreamHandler

logger = logging.getLogger(__name__)

# Maximum length for scrape results in demo mode (to support more conversation turns)
DEMO_SCRAPE_MAX_LENGTH = 20_000


class ToolExecutor:
    """
    Executor for tool calls with support for duplicate detection and result processing.

    Handles the execution of tool calls, including parameter fixing, duplicate query
    detection, result truncation in demo mode, and error handling.
    """

    def __init__(
        self,
        main_agent_tool_manager: ToolManager,
        sub_agent_tool_managers: Dict[str, ToolManager],
        output_formatter: OutputFormatter,
        task_log: TaskLog,
        stream_handler: StreamHandler,
        max_consecutive_rollbacks: int = 5,
    ):
        """
        Initialize the tool executor.

        Args:
            main_agent_tool_manager: Tool manager for main agent
            sub_agent_tool_managers: Dictionary of tool managers for sub-agents
            output_formatter: Formatter for tool results
            task_log: Logger for task execution
            stream_handler: Handler for streaming events
            max_consecutive_rollbacks: Maximum allowed consecutive rollbacks
        """
        self.main_agent_tool_manager = main_agent_tool_manager
        self.sub_agent_tool_managers = sub_agent_tool_managers
        self.output_formatter = output_formatter
        self.task_log = task_log
        self.stream = stream_handler
        self.max_consecutive_rollbacks = max_consecutive_rollbacks

        # Track used queries to detect duplicates
        self.used_queries: Dict[str, Dict[str, int]] = {}

    def fix_tool_call_arguments(self, tool_name: str, arguments: dict) -> dict:
        """
        Fix common parameter name mistakes made by LLM.

        Args:
            tool_name: Name of the tool being called
            arguments: Original arguments dictionary

        Returns:
            Fixed arguments dictionary
        """
        # Create a copy to avoid modifying the original
        fixed_args = arguments.copy()

        # Fix scrape_and_extract_info parameter names
        if tool_name == "scrape_and_extract_info":
            # Map common mistakes to the correct parameter name
            mistake_names = ["description", "introduction"]
            if "info_to_extract" not in fixed_args:
                for mistake_name in mistake_names:
                    if mistake_name in fixed_args:
                        fixed_args["info_to_extract"] = fixed_args.pop(mistake_name)
                        break

        # Fix run_python_code parameter names: 'code' -> 'code_block'
        # Also add default sandbox_id if missing (will trigger stateless fallback)
        if tool_name == "run_python_code":
            if "code_block" not in fixed_args and "code" in fixed_args:
                fixed_args["code_block"] = fixed_args.pop("code")
            if "sandbox_id" not in fixed_args:
                fixed_args["sandbox_id"] = "default"

        return fixed_args

    def get_query_str_from_tool_call(
        self, tool_name: str, arguments: dict
    ) -> Optional[str]:
        """
        Extract the query string from tool call arguments based on tool_name.

        Supports search_and_browse, google_search, sogou_search, scrape_website,
        and scrape_and_extract_info.

        Args:
            tool_name: Name of the tool
            arguments: Tool arguments dictionary

        Returns:
            Query string for duplicate detection, or None if not applicable
        """
        if tool_name == "search_and_browse":
            return tool_name + "_" + arguments.get("subtask", "")
        elif tool_name == "google_search":
            return tool_name + "_" + arguments.get("q", "")
        elif tool_name == "sogou_search":
            return tool_name + "_" + arguments.get("Query", "")
        elif tool_name == "scrape_website":
            return tool_name + "_" + arguments.get("url", "")
        elif tool_name == "scrape_and_extract_info":
            return (
                tool_name
                + "_"
                + arguments.get("url", "")
                + "_"
                + arguments.get("info_to_extract", "")
            )
        return None

    def is_duplicate_query(self, cache_name: str, query_str: str) -> Tuple[bool, int]:
        """
        Check if a query has been executed before.

        Args:
            cache_name: Name of the cache (e.g., "main_google_search")
            query_str: The query string to check

        Returns:
            Tuple of (is_duplicate, previous_count)
        """
        self.used_queries.setdefault(cache_name, defaultdict(int))
        count = self.used_queries[cache_name][query_str]
        return count > 0, count

    def record_query(self, cache_name: str, query_str: str):
        """
        Record that a query has been executed.

        Args:
            cache_name: Name of the cache
            query_str: The query string to record
        """
        self.used_queries.setdefault(cache_name, defaultdict(int))
        self.used_queries[cache_name][query_str] += 1

    def is_google_search_empty_result(self, tool_name: str, tool_result: dict) -> bool:
        """
        Check if google_search result has empty organic results.

        This indicates a poor search query that should be retried.

        Args:
            tool_name: Name of the tool
            tool_result: The tool execution result

        Returns:
            True if the result is empty and should trigger retry
        """
        if tool_name != "google_search":
            return False

        result = tool_result.get("result")
        if not result:
            return False

        try:
            if isinstance(result, str):
                result_dict = json.loads(result)
            else:
                result_dict = result

            organic = result_dict.get("organic", [])
            return len(organic) == 0
        except (json.JSONDecodeError, TypeError, AttributeError):
            return False

    def get_scrape_result(self, result: str) -> str:
        """
        Process scrape result and truncate if too long.

        Args:
            result: Raw scrape result string (JSON or plain text)

        Returns:
            Processed result, truncated to DEMO_SCRAPE_MAX_LENGTH if necessary
        """
        try:
            scrape_result_dict = json.loads(result)
            text = scrape_result_dict.get("text")
            if text and len(text) > DEMO_SCRAPE_MAX_LENGTH:
                text = text[:DEMO_SCRAPE_MAX_LENGTH]
            return json.dumps({"text": text}, ensure_ascii=False)
        except json.JSONDecodeError:
            if isinstance(result, str) and len(result) > DEMO_SCRAPE_MAX_LENGTH:
                result = result[:DEMO_SCRAPE_MAX_LENGTH]
            return result

    def post_process_tool_call_result(
        self, tool_name: str, tool_call_result: dict
    ) -> dict:
        """
        Process tool call results.

        Only in demo mode: truncate scrape results to 20,000 chars
        to support more conversation turns.

        Args:
            tool_name: Name of the tool
            tool_call_result: The tool execution result

        Returns:
            Processed tool result
        """
        if os.environ.get("DEMO_MODE") == "1":
            if "result" in tool_call_result and tool_name in [
                "scrape",
                "scrape_website",
            ]:
                tool_call_result["result"] = self.get_scrape_result(
                    tool_call_result["result"]
                )
        return tool_call_result

    def should_rollback_result(
        self, tool_name: str, result: Any, tool_result: dict
    ) -> bool:
        """
        Check if a tool result should trigger a rollback.

        Args:
            tool_name: Name of the tool
            result: The result value
            tool_result: Full tool result dictionary

        Returns:
            True if the result indicates an error that should trigger rollback
        """
        return (
            str(result).startswith("Unknown tool:")
            or str(result).startswith("Error executing tool")
            or self.is_google_search_empty_result(tool_name, tool_result)
        )

    async def execute_single_tool_call(
        self,
        tool_manager: ToolManager,
        server_name: str,
        tool_name: str,
        arguments: dict,
        agent_name: str,
        turn_count: int,
    ) -> Tuple[dict, int, List[dict]]:
        """
        Execute a single tool call.

        Args:
            tool_manager: The tool manager to use
            server_name: Name of the MCP server
            tool_name: Name of the tool
            arguments: Tool arguments
            agent_name: Name of the agent making the call
            turn_count: Current turn count

        Returns:
            Tuple of (tool_result, duration_ms, tool_calls_data)
        """
        call_start_time = time.time()
        tool_calls_data = []

        try:
            # Execute tool call
            tool_result = await tool_manager.execute_tool_call(
                server_name, tool_name, arguments
            )

            # Post-process result
            tool_result = self.post_process_tool_call_result(tool_name, tool_result)

            call_end_time = time.time()
            call_duration_ms = int((call_end_time - call_start_time) * 1000)

            self.task_log.log_step(
                "info",
                f"{agent_name} | Turn: {turn_count} | Tool Call",
                f"Tool {tool_name} completed in {call_duration_ms}ms",
            )

            tool_calls_data.append(
                {
                    "server_name": server_name,
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "result": tool_result,
                    "duration_ms": call_duration_ms,
                    "call_time": get_utc_plus_8_time(),
                }
            )

            return tool_result, call_duration_ms, tool_calls_data

        except Exception as e:
            call_end_time = time.time()
            call_duration_ms = int((call_end_time - call_start_time) * 1000)

            tool_calls_data.append(
                {
                    "server_name": server_name,
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "error": str(e),
                    "duration_ms": call_duration_ms,
                    "call_time": get_utc_plus_8_time(),
                }
            )

            tool_result = {
                "error": f"Tool call failed: {str(e)}",
                "server_name": server_name,
                "tool_name": tool_name,
            }

            self.task_log.log_step(
                "error",
                f"{agent_name} | Turn: {turn_count} | Tool Call",
                f"Tool {tool_name} failed to execute: {str(e)}",
            )

            return tool_result, call_duration_ms, tool_calls_data

    def format_tool_result_for_llm(self, tool_result: dict) -> dict:
        """
        Format tool result for feeding back to LLM.

        Args:
            tool_result: The tool execution result

        Returns:
            Formatted result suitable for LLM message
        """
        return self.output_formatter.format_tool_result_for_user(tool_result)
