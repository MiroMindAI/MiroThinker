# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

"""
Orchestrator module for coordinating agent task execution.

This module contains the main Orchestrator class that manages the execution of tasks
by coordinating between the main agent, sub-agents, and various tools.
"""

import asyncio
import gc
import logging
import time
import uuid
from collections import defaultdict
from datetime import date
from typing import Any, Dict, List, Optional

from miroflow_tools.manager import ToolManager
from omegaconf import DictConfig

from ..config.settings import expose_sub_agents_as_tools
from ..io.input_handler import process_input
from ..io.output_formatter import OutputFormatter
from ..llm.base_client import BaseClient
from ..logging.task_logger import TaskLog, get_utc_plus_8_time
from ..utils.parsing_utils import extract_llm_response_text
from ..utils.prompt_utils import (
    generate_agent_specific_system_prompt,
    generate_agent_summarize_prompt,
    mcp_tags,
    refusal_keywords,
)
from .answer_generator import AnswerGenerator
from .stream_handler import StreamHandler
from .tool_executor import ToolExecutor

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

# Default timeout for LLM calls in seconds
DEFAULT_LLM_TIMEOUT = 600

# Safety limits for retry loops
DEFAULT_MAX_CONSECUTIVE_ROLLBACKS = 5

# Additional attempts beyond max_turns for total loop protection
EXTRA_ATTEMPTS_BUFFER = 200


def _list_tools(sub_agent_tool_managers: Dict[str, ToolManager]):
    """
    Create a cached async function for fetching sub-agent tool definitions.

    This factory function returns an async closure that lazily fetches and caches
    tool definitions from all sub-agent tool managers. The cache ensures that
    tool definitions are only fetched once per orchestrator instance.

    Args:
        sub_agent_tool_managers: Dictionary mapping sub-agent names to their ToolManager instances.

    Returns:
        An async function that returns a dictionary of tool definitions for each sub-agent.
    """
    cache = None

    async def wrapped():
        nonlocal cache
        if cache is None:
            # Only fetch tool definitions if not already cached
            result = {
                name: await tool_manager.get_all_tool_definitions()
                for name, tool_manager in sub_agent_tool_managers.items()
            }
            cache = result
        return cache

    return wrapped


class Orchestrator:
    """
    Main orchestrator for coordinating agent task execution.

    Manages the execution loop for main and sub-agents, coordinating
    LLM calls, tool execution, streaming events, and context management.
    """

    def __init__(
        self,
        main_agent_tool_manager: ToolManager,
        sub_agent_tool_managers: Dict[str, ToolManager],
        llm_client: BaseClient,
        output_formatter: OutputFormatter,
        cfg: DictConfig,
        task_log: Optional["TaskLog"] = None,
        stream_queue: Optional[Any] = None,
        tool_definitions: Optional[List[Dict[str, Any]]] = None,
        sub_agent_tool_definitions: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ):
        """
        Initialize the orchestrator.

        Args:
            main_agent_tool_manager: Tool manager for main agent
            sub_agent_tool_managers: Dictionary of tool managers for sub-agents
            llm_client: The LLM client for API calls
            output_formatter: Formatter for output processing
            cfg: Configuration object
            task_log: Logger for task execution
            stream_queue: Optional async queue for streaming events
            tool_definitions: Pre-fetched tool definitions (optional)
            sub_agent_tool_definitions: Pre-fetched sub-agent tool definitions (optional)
        """
        self.main_agent_tool_manager = main_agent_tool_manager
        self.sub_agent_tool_managers = sub_agent_tool_managers
        self.llm_client = llm_client
        self.output_formatter = output_formatter
        self.cfg = cfg
        self.task_log = task_log
        self.stream_queue = stream_queue
        self.tool_definitions = tool_definitions
        self.sub_agent_tool_definitions = sub_agent_tool_definitions

        # Initialize sub-agent tool list function
        self._list_sub_agent_tools = None
        if sub_agent_tool_managers:
            self._list_sub_agent_tools = _list_tools(sub_agent_tool_managers)

        # Pass task_log to llm_client
        if self.llm_client and task_log:
            self.llm_client.task_log = task_log

        # Track boxed answers extracted during main loop turns
        self.intermediate_boxed_answers: List[str] = []

        # Record used subtask / q / Query to detect duplicates
        self.used_queries: Dict[str, Dict[str, int]] = {}

        # Retry loop protection limits
        self.MAX_CONSECUTIVE_ROLLBACKS = DEFAULT_MAX_CONSECUTIVE_ROLLBACKS

        # Context management settings
        self.context_compress_limit = cfg.agent.get("context_compress_limit", 0)

        # Initialize helper components
        self.stream = StreamHandler(stream_queue)
        self.tool_executor = ToolExecutor(
            main_agent_tool_manager=main_agent_tool_manager,
            sub_agent_tool_managers=sub_agent_tool_managers,
            output_formatter=output_formatter,
            task_log=task_log,
            stream_handler=self.stream,
            max_consecutive_rollbacks=DEFAULT_MAX_CONSECUTIVE_ROLLBACKS,
        )
        self.answer_generator = AnswerGenerator(
            llm_client=llm_client,
            output_formatter=output_formatter,
            task_log=task_log,
            stream_handler=self.stream,
            cfg=cfg,
            intermediate_boxed_answers=self.intermediate_boxed_answers,
        )

    def _save_message_history(
        self, system_prompt: str, message_history: List[Dict[str, Any]]
    ):
        """Save message history to task log."""
        self.task_log.main_agent_message_history = {
            "system_prompt": system_prompt,
            "message_history": message_history,
        }
        self.task_log.save()

    async def _handle_response_format_issues(
        self,
        assistant_response_text: str,
        message_history: List[Dict[str, Any]],
        turn_count: int,
        consecutive_rollbacks: int,
        total_attempts: int,
        max_attempts: int,
        agent_name: str,
    ) -> tuple:
        """
        Handle MCP tag format errors and refusal keywords.

        Args:
            assistant_response_text: The LLM response text
            message_history: Current message history
            turn_count: Current turn count
            consecutive_rollbacks: Current consecutive rollback count
            total_attempts: Total attempts made
            max_attempts: Maximum allowed attempts
            agent_name: Name of the agent for logging

        Returns:
            Tuple of (should_continue, should_break, turn_count, consecutive_rollbacks, message_history)
        """
        # Check for MCP tags in response (format error)
        if any(mcp_tag in assistant_response_text for mcp_tag in mcp_tags):
            if consecutive_rollbacks < self.MAX_CONSECUTIVE_ROLLBACKS - 1:
                turn_count -= 1
                consecutive_rollbacks += 1
                if message_history[-1]["role"] == "assistant":
                    message_history.pop()
                self.task_log.log_step(
                    "warning",
                    f"{agent_name} | Turn: {turn_count} | Rollback",
                    f"Tool call format incorrect - found MCP tags in response. "
                    f"Consecutive rollbacks: {consecutive_rollbacks}/{self.MAX_CONSECUTIVE_ROLLBACKS}, "
                    f"Total attempts: {total_attempts}/{max_attempts}",
                )
                return True, False, turn_count, consecutive_rollbacks, message_history
            else:
                self.task_log.log_step(
                    "warning",
                    f"{agent_name} | Turn: {turn_count} | End After Max Rollbacks",
                    f"Ending agent loop after {consecutive_rollbacks} consecutive MCP format errors",
                )
                return False, True, turn_count, consecutive_rollbacks, message_history

        # Check for refusal keywords
        if any(keyword in assistant_response_text for keyword in refusal_keywords):
            matched_keywords = [
                kw for kw in refusal_keywords if kw in assistant_response_text
            ]
            if consecutive_rollbacks < self.MAX_CONSECUTIVE_ROLLBACKS - 1:
                turn_count -= 1
                consecutive_rollbacks += 1
                if message_history[-1]["role"] == "assistant":
                    message_history.pop()
                self.task_log.log_step(
                    "warning",
                    f"{agent_name} | Turn: {turn_count} | Rollback",
                    f"LLM refused to answer - found refusal keywords: {matched_keywords}. "
                    f"Consecutive rollbacks: {consecutive_rollbacks}/{self.MAX_CONSECUTIVE_ROLLBACKS}, "
                    f"Total attempts: {total_attempts}/{max_attempts}",
                )
                return True, False, turn_count, consecutive_rollbacks, message_history
            else:
                self.task_log.log_step(
                    "warning",
                    f"{agent_name} | Turn: {turn_count} | End After Max Rollbacks",
                    f"Ending agent loop after {consecutive_rollbacks} consecutive refusals with keywords: {matched_keywords}",
                )
                return False, True, turn_count, consecutive_rollbacks, message_history

        # No format issues - normal end without tool calls
        return False, True, turn_count, consecutive_rollbacks, message_history

    async def _check_duplicate_query(
        self,
        tool_name: str,
        arguments: dict,
        cache_name: str,
        consecutive_rollbacks: int,
        turn_count: int,
        total_attempts: int,
        max_attempts: int,
        message_history: List[Dict[str, Any]],
        agent_name: str,
    ) -> tuple:
        """
        Check for duplicate queries and handle rollback if needed.

        Args:
            tool_name: Name of the tool being called
            arguments: Tool arguments
            cache_name: Name of the query cache to use
            consecutive_rollbacks: Current consecutive rollback count
            turn_count: Current turn count
            total_attempts: Total attempts made
            max_attempts: Maximum allowed attempts
            message_history: Current message history
            agent_name: Name of the agent for logging

        Returns:
            Tuple of (is_duplicate, should_rollback, turn_count, consecutive_rollbacks, message_history)
        """
        query_str = self.tool_executor.get_query_str_from_tool_call(
            tool_name, arguments
        )
        if not query_str:
            return False, False, turn_count, consecutive_rollbacks, message_history

        self.used_queries.setdefault(cache_name, defaultdict(int))
        count = self.used_queries[cache_name][query_str]

        if count > 0:
            if consecutive_rollbacks < self.MAX_CONSECUTIVE_ROLLBACKS - 1:
                message_history.pop()
                turn_count -= 1
                consecutive_rollbacks += 1
                self.task_log.log_step(
                    "warning",
                    f"{agent_name} | Turn: {turn_count} | Rollback",
                    f"Duplicate query detected - tool: {tool_name}, query: '{query_str}', "
                    f"previous count: {count}. Consecutive rollbacks: {consecutive_rollbacks}/"
                    f"{self.MAX_CONSECUTIVE_ROLLBACKS}, Total attempts: {total_attempts}/{max_attempts}",
                )
                return True, True, turn_count, consecutive_rollbacks, message_history
            else:
                self.task_log.log_step(
                    "warning",
                    f"{agent_name} | Turn: {turn_count} | Allow Duplicate",
                    f"Allowing duplicate query after {consecutive_rollbacks} rollbacks - "
                    f"tool: {tool_name}, query: '{query_str}', previous count: {count}",
                )

        return False, False, turn_count, consecutive_rollbacks, message_history

    async def _record_query(self, cache_name: str, tool_name: str, arguments: dict):
        """Record a successful query execution."""
        query_str = self.tool_executor.get_query_str_from_tool_call(
            tool_name, arguments
        )
        if query_str:
            self.used_queries.setdefault(cache_name, defaultdict(int))
            self.used_queries[cache_name][query_str] += 1

    async def run_sub_agent(
        self,
        sub_agent_name: str,
        task_description: str,
    ):
        """
        Run a sub-agent to handle a subtask.

        Args:
            sub_agent_name: Name of the sub-agent to run
            task_description: Description of the subtask

        Returns:
            The final answer text from the sub-agent
        """
        task_description += "\n\nPlease provide the answer and detailed supporting information of the subtask given to you."
        self.task_log.log_step(
            "info",
            f"{sub_agent_name} | Task Description",
            f"Subtask: {task_description}",
        )

        # Stream sub-agent start
        display_name = sub_agent_name.replace("agent-", "")
        sub_agent_id = await self.stream.start_agent(display_name)
        await self.stream.start_llm(display_name)

        # Start new sub-agent session
        self.task_log.start_sub_agent_session(sub_agent_name, task_description)

        # Initialize message history
        message_history = [{"role": "user", "content": task_description}]

        # Get sub-agent tool definitions
        if not self.sub_agent_tool_definitions:
            tool_definitions = await self._list_sub_agent_tools()
            tool_definitions = tool_definitions.get(sub_agent_name, {})
        else:
            tool_definitions = self.sub_agent_tool_definitions[sub_agent_name]

        if not tool_definitions:
            self.task_log.log_step(
                "warning",
                f"{sub_agent_name} | No Tools",
                "No tool definitions available.",
            )

        # Generate sub-agent system prompt
        system_prompt = self.llm_client.generate_agent_system_prompt(
            date=date.today(),
            mcp_servers=tool_definitions,
        ) + generate_agent_specific_system_prompt(agent_type=sub_agent_name)

        # Limit sub-agent turns
        if self.cfg.agent.sub_agents:
            max_turns = self.cfg.agent.sub_agents[sub_agent_name].max_turns
        else:
            max_turns = 0
        turn_count = 0
        total_attempts = 0
        max_attempts = max_turns + EXTRA_ATTEMPTS_BUFFER
        consecutive_rollbacks = 0

        while turn_count < max_turns and total_attempts < max_attempts:
            turn_count += 1
            total_attempts += 1

            if consecutive_rollbacks >= self.MAX_CONSECUTIVE_ROLLBACKS:
                self.task_log.log_step(
                    "error",
                    f"{sub_agent_name} | Too Many Rollbacks",
                    f"Reached {consecutive_rollbacks} consecutive rollbacks, breaking loop.",
                )
                break

            self.task_log.save()

            # Reset 'last_call_tokens'
            self.llm_client.last_call_tokens = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
            }

            # LLM call using answer generator
            (
                assistant_response_text,
                should_break,
                tool_calls,
                message_history,
            ) = await self.answer_generator.handle_llm_call(
                system_prompt,
                message_history,
                tool_definitions,
                turn_count,
                f"{sub_agent_name} | Turn: {turn_count}",
                agent_type=sub_agent_name,
            )

            if should_break:
                self.task_log.log_step(
                    "info",
                    f"{sub_agent_name} | Turn: {turn_count} | LLM Call",
                    "should break is True, breaking the loop",
                )
                break

            if assistant_response_text:
                text_response = extract_llm_response_text(assistant_response_text)
                if text_response:
                    await self.stream.tool_call("show_text", {"text": text_response})
            else:
                self.task_log.log_step(
                    "info",
                    f"{sub_agent_name} | Turn: {turn_count} | LLM Call",
                    "LLM call failed",
                )
                await asyncio.sleep(5)
                continue

            # Handle no tool calls case
            if not tool_calls:
                (
                    should_continue,
                    should_break_loop,
                    turn_count,
                    consecutive_rollbacks,
                    message_history,
                ) = await self._handle_response_format_issues(
                    assistant_response_text,
                    message_history,
                    turn_count,
                    consecutive_rollbacks,
                    total_attempts,
                    max_attempts,
                    sub_agent_name,
                )
                if should_continue:
                    continue
                if should_break_loop:
                    if not any(
                        mcp_tag in assistant_response_text for mcp_tag in mcp_tags
                    ) and not any(
                        keyword in assistant_response_text
                        for keyword in refusal_keywords
                    ):
                        self.task_log.log_step(
                            "info",
                            f"{sub_agent_name} | Turn: {turn_count} | LLM Call",
                            f"No tool calls found in {sub_agent_name}, ending on turn {turn_count}",
                        )
                    break

            # Execute tool calls
            tool_calls_data = []
            all_tool_results_content_with_id = []
            should_rollback_turn = False

            for call in tool_calls:
                server_name = call["server_name"]
                tool_name = call["tool_name"]
                arguments = call["arguments"]
                call_id = call["id"]

                # Fix common parameter name mistakes
                arguments = self.tool_executor.fix_tool_call_arguments(
                    tool_name, arguments
                )

                self.task_log.log_step(
                    "info",
                    f"{sub_agent_name} | Turn: {turn_count} | Tool Call",
                    f"Executing {tool_name} on {server_name}",
                )

                call_start_time = time.time()
                try:
                    # Check for duplicate query
                    cache_name = sub_agent_id + "_" + tool_name
                    (
                        is_duplicate,
                        should_rollback,
                        turn_count,
                        consecutive_rollbacks,
                        message_history,
                    ) = await self._check_duplicate_query(
                        tool_name,
                        arguments,
                        cache_name,
                        consecutive_rollbacks,
                        turn_count,
                        total_attempts,
                        max_attempts,
                        message_history,
                        sub_agent_name,
                    )
                    if should_rollback:
                        should_rollback_turn = True
                        break

                    # Send stream event
                    tool_call_id = await self.stream.tool_call(tool_name, arguments)

                    # Execute tool call
                    tool_result = await self.sub_agent_tool_managers[
                        sub_agent_name
                    ].execute_tool_call(server_name, tool_name, arguments)

                    # Update query count if successful
                    if "error" not in tool_result:
                        await self._record_query(cache_name, tool_name, arguments)

                    # Post-process result
                    tool_result = self.tool_executor.post_process_tool_call_result(
                        tool_name, tool_result
                    )
                    result = (
                        tool_result.get("result")
                        if tool_result.get("result")
                        else tool_result.get("error")
                    )

                    # Check for errors that should trigger rollback
                    if self.tool_executor.should_rollback_result(
                        tool_name, result, tool_result
                    ):
                        if consecutive_rollbacks < self.MAX_CONSECUTIVE_ROLLBACKS - 1:
                            message_history.pop()
                            turn_count -= 1
                            consecutive_rollbacks += 1
                            should_rollback_turn = True
                            self.task_log.log_step(
                                "warning",
                                f"{sub_agent_name} | Turn: {turn_count} | Rollback",
                                f"Tool result error - tool: {tool_name}, result: '{str(result)[:200]}'",
                            )
                            break

                    await self.stream.tool_call(
                        tool_name, {"result": result}, tool_call_id=tool_call_id
                    )
                    call_end_time = time.time()
                    call_duration_ms = int((call_end_time - call_start_time) * 1000)

                    self.task_log.log_step(
                        "info",
                        f"{sub_agent_name} | Turn: {turn_count} | Tool Call",
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
                        f"{sub_agent_name} | Turn: {turn_count} | Tool Call",
                        f"Tool {tool_name} failed to execute: {str(e)}",
                    )

                tool_result_for_llm = self.output_formatter.format_tool_result_for_user(
                    tool_result
                )
                all_tool_results_content_with_id.append((call_id, tool_result_for_llm))

            if should_rollback_turn:
                continue

            # Reset consecutive rollbacks on successful execution
            if consecutive_rollbacks > 0:
                self.task_log.log_step(
                    "info",
                    f"{sub_agent_name} | Turn: {turn_count} | Recovery",
                    f"Successfully recovered after {consecutive_rollbacks} consecutive rollbacks",
                )
            consecutive_rollbacks = 0

            # Update message history
            message_history = self.llm_client.update_message_history(
                message_history, all_tool_results_content_with_id
            )

            # Check context length
            temp_summary_prompt = generate_agent_summarize_prompt(
                task_description,
                agent_type=sub_agent_name,
            )

            pass_length_check, message_history = self.llm_client.ensure_summary_context(
                message_history, temp_summary_prompt
            )

            if not pass_length_check:
                turn_count = max_turns
                self.task_log.log_step(
                    "info",
                    f"{sub_agent_name} | Turn: {turn_count} | Context Limit Reached",
                    "Context limit reached, triggering summary",
                )
                break

        # Log loop end
        if turn_count >= max_turns:
            self.task_log.log_step(
                "info",
                f"{sub_agent_name} | Max Turns Reached / Context Limit Reached",
                f"Reached maximum turns ({max_turns}) or context limit reached",
            )
        else:
            self.task_log.log_step(
                "info",
                f"{sub_agent_name} | Main Loop Completed",
                f"Main loop completed after {turn_count} turns",
            )

        # Generate final summary
        self.task_log.log_step(
            "info",
            f"{sub_agent_name} | Final Summary",
            f"Generating {sub_agent_name} final summary",
        )

        summary_prompt = generate_agent_summarize_prompt(
            task_description,
            agent_type=sub_agent_name,
        )

        if message_history[-1]["role"] == "user":
            message_history.pop()
        message_history.append({"role": "user", "content": summary_prompt})

        await self.stream.tool_call(
            "Partial Summary", {}, tool_call_id=str(uuid.uuid4())
        )

        # Generate final answer
        (
            final_answer_text,
            should_break,
            tool_calls_info,
            message_history,
        ) = await self.answer_generator.handle_llm_call(
            system_prompt,
            message_history,
            tool_definitions,
            turn_count + 1,
            f"{sub_agent_name} | Final summary",
            agent_type=sub_agent_name,
        )

        if final_answer_text:
            self.task_log.log_step(
                "info",
                f"{sub_agent_name} | Final Answer",
                "Final answer generated successfully",
            )
        else:
            final_answer_text = (
                f"No final answer generated by sub agent {sub_agent_name}."
            )
            self.task_log.log_step(
                "error",
                f"{sub_agent_name} | Final Answer",
                "Unable to generate final answer",
            )

        # Save session history
        self.task_log.sub_agent_message_history_sessions[
            self.task_log.current_sub_agent_session_id
        ] = {"system_prompt": system_prompt, "message_history": message_history}

        self.task_log.save()
        self.task_log.end_sub_agent_session(sub_agent_name)

        # Remove thinking content
        final_answer_text = final_answer_text.split("<think>")[-1].strip()
        final_answer_text = final_answer_text.split("</think>")[-1].strip()

        # Stream sub-agent end
        await self.stream.end_llm(display_name)
        await self.stream.end_agent(display_name, sub_agent_id)

        return final_answer_text

    async def run_main_agent(
        self,
        task_description,
        task_file_name=None,
        task_id="default_task",
        is_final_retry=False,
    ):
        """
        Execute the main end-to-end task.

        Args:
            task_description: Description of the task to execute
            task_file_name: Optional file associated with the task
            task_id: Unique identifier for the task

        Returns:
            Tuple of (final_summary, final_boxed_answer, failure_experience_summary)
        """
        workflow_id = await self.stream.start_workflow(task_description)

        self.task_log.log_step("info", "Main Agent", f"Start task with id: {task_id}")
        self.task_log.log_step(
            "info", "Main Agent", f"Task description: {task_description}"
        )
        if task_file_name:
            self.task_log.log_step(
                "info", "Main Agent", f"Associated file: {task_file_name}"
            )

        # Process input
        initial_user_content, processed_task_desc = process_input(
            task_description, task_file_name
        )
        message_history = [{"role": "user", "content": initial_user_content}]

        # Record initial user input
        user_input = processed_task_desc
        if task_file_name:
            user_input += f"\n[Attached file: {task_file_name}]"

        # Get tool definitions
        if not self.tool_definitions:
            tool_definitions = (
                await self.main_agent_tool_manager.get_all_tool_definitions()
            )
            if self.cfg.agent.sub_agents is not None:
                tool_definitions += expose_sub_agents_as_tools(
                    self.cfg.agent.sub_agents
                )
        else:
            tool_definitions = self.tool_definitions

        if not tool_definitions:
            self.task_log.log_step(
                "warning",
                "Main Agent | Tool Definitions",
                "Warning: No tool definitions found. LLM cannot use any tools.",
            )

        # Generate system prompt
        system_prompt = self.llm_client.generate_agent_system_prompt(
            date=date.today(),
            mcp_servers=tool_definitions,
        ) + generate_agent_specific_system_prompt(agent_type="main")
        system_prompt = system_prompt.strip()

        # Main loop configuration
        max_turns = self.cfg.agent.main_agent.max_turns
        turn_count = 0
        total_attempts = 0
        max_attempts = max_turns + EXTRA_ATTEMPTS_BUFFER
        consecutive_rollbacks = 0

        self.current_agent_id = await self.stream.start_agent("main")
        await self.stream.start_llm("main")

        while turn_count < max_turns and total_attempts < max_attempts:
            turn_count += 1
            total_attempts += 1

            if consecutive_rollbacks >= self.MAX_CONSECUTIVE_ROLLBACKS:
                self.task_log.log_step(
                    "error",
                    "Main Agent | Too Many Rollbacks",
                    f"Reached {consecutive_rollbacks} consecutive rollbacks, breaking loop.",
                )
                break

            self.task_log.save()

            # LLM call
            (
                assistant_response_text,
                should_break,
                tool_calls,
                message_history,
            ) = await self.answer_generator.handle_llm_call(
                system_prompt,
                message_history,
                tool_definitions,
                turn_count,
                f"Main agent | Turn: {turn_count}",
                agent_type="main",
            )

            # Process LLM response
            if assistant_response_text:
                text_response = extract_llm_response_text(assistant_response_text)
                if text_response:
                    await self.stream.tool_call("show_text", {"text": text_response})

                # Extract boxed content
                boxed_content = self.output_formatter._extract_boxed_content(
                    assistant_response_text
                )
                if boxed_content:
                    self.intermediate_boxed_answers.append(boxed_content)

                if should_break:
                    self.task_log.log_step(
                        "info",
                        f"Main Agent | Turn: {turn_count} | LLM Call",
                        "should break is True, breaking the loop",
                    )
                    break
            else:
                turn_count -= 1
                self.task_log.log_step(
                    "warning",
                    f"Main Agent | Turn: {turn_count} | LLM Call",
                    "No valid response from LLM, retrying",
                )
                await asyncio.sleep(5)
                continue

            # Handle no tool calls case
            if not tool_calls:
                (
                    should_continue,
                    should_break_loop,
                    turn_count,
                    consecutive_rollbacks,
                    message_history,
                ) = await self._handle_response_format_issues(
                    assistant_response_text,
                    message_history,
                    turn_count,
                    consecutive_rollbacks,
                    total_attempts,
                    max_attempts,
                    "Main Agent",
                )
                if should_continue:
                    continue
                if should_break_loop:
                    if not any(
                        mcp_tag in assistant_response_text for mcp_tag in mcp_tags
                    ) and not any(
                        keyword in assistant_response_text
                        for keyword in refusal_keywords
                    ):
                        self.task_log.log_step(
                            "info",
                            f"Main Agent | Turn: {turn_count} | LLM Call",
                            "LLM did not request tool usage, ending process.",
                        )
                    break

            # Execute tool calls
            tool_calls_data = []
            all_tool_results_content_with_id = []
            should_rollback_turn = False
            main_agent_last_call_tokens = self.llm_client.last_call_tokens

            for call in tool_calls:
                server_name = call["server_name"]
                tool_name = call["tool_name"]
                arguments = call["arguments"]
                call_id = call["id"]

                # Fix common parameter name mistakes
                arguments = self.tool_executor.fix_tool_call_arguments(
                    tool_name, arguments
                )

                call_start_time = time.time()
                try:
                    if server_name.startswith("agent-") and self.cfg.agent.sub_agents:
                        # Sub-agent execution
                        cache_name = "main_" + tool_name
                        (
                            is_duplicate,
                            should_rollback,
                            turn_count,
                            consecutive_rollbacks,
                            message_history,
                        ) = await self._check_duplicate_query(
                            tool_name,
                            arguments,
                            cache_name,
                            consecutive_rollbacks,
                            turn_count,
                            total_attempts,
                            max_attempts,
                            message_history,
                            "Main Agent",
                        )
                        if should_rollback:
                            should_rollback_turn = True
                            break

                        # Stream events
                        await self.stream.end_llm("main")
                        await self.stream.end_agent("main", self.current_agent_id)

                        # Execute sub-agent
                        sub_agent_result = await self.run_sub_agent(
                            server_name,
                            arguments["subtask"],
                        )

                        # Update query count
                        await self._record_query(cache_name, tool_name, arguments)

                        tool_result = {
                            "server_name": server_name,
                            "tool_name": tool_name,
                            "result": sub_agent_result,
                        }
                        self.current_agent_id = await self.stream.start_agent(
                            "main", display_name="Summarizing"
                        )
                        await self.stream.start_llm("main", display_name="Summarizing")
                    else:
                        # Regular tool execution
                        cache_name = "main_" + tool_name
                        (
                            is_duplicate,
                            should_rollback,
                            turn_count,
                            consecutive_rollbacks,
                            message_history,
                        ) = await self._check_duplicate_query(
                            tool_name,
                            arguments,
                            cache_name,
                            consecutive_rollbacks,
                            turn_count,
                            total_attempts,
                            max_attempts,
                            message_history,
                            "Main Agent",
                        )
                        if should_rollback:
                            should_rollback_turn = True
                            break

                        # Send stream event
                        tool_call_id = await self.stream.tool_call(tool_name, arguments)

                        # Execute tool call
                        tool_result = (
                            await self.main_agent_tool_manager.execute_tool_call(
                                server_name=server_name,
                                tool_name=tool_name,
                                arguments=arguments,
                            )
                        )

                        # Update query count if successful
                        if "error" not in tool_result:
                            await self._record_query(cache_name, tool_name, arguments)

                        # Post-process result
                        tool_result = self.tool_executor.post_process_tool_call_result(
                            tool_name, tool_result
                        )
                        result = (
                            tool_result.get("result")
                            if tool_result.get("result")
                            else tool_result.get("error")
                        )

                        # Check for errors that should trigger rollback
                        if self.tool_executor.should_rollback_result(
                            tool_name, result, tool_result
                        ):
                            if (
                                consecutive_rollbacks
                                < self.MAX_CONSECUTIVE_ROLLBACKS - 1
                            ):
                                message_history.pop()
                                turn_count -= 1
                                consecutive_rollbacks += 1
                                should_rollback_turn = True
                                self.task_log.log_step(
                                    "warning",
                                    f"Main Agent | Turn: {turn_count} | Rollback",
                                    f"Tool result error - tool: {tool_name}, result: '{str(result)[:200]}'",
                                )
                                break

                        await self.stream.tool_call(
                            tool_name, {"result": result}, tool_call_id=tool_call_id
                        )

                    call_end_time = time.time()
                    call_duration_ms = int((call_end_time - call_start_time) * 1000)

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
                    self.task_log.log_step(
                        "info",
                        f"Main Agent | Turn: {turn_count} | Tool Call",
                        f"Tool {tool_name} completed in {call_duration_ms}ms",
                    )

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
                        "server_name": server_name,
                        "tool_name": tool_name,
                        "error": str(e),
                    }
                    self.task_log.log_step(
                        "error",
                        f"Main Agent | Turn: {turn_count} | Tool Call",
                        f"Tool {tool_name} failed to execute: {str(e)}",
                    )

                # Format results for LLM
                tool_result_for_llm = self.output_formatter.format_tool_result_for_user(
                    tool_result
                )
                all_tool_results_content_with_id.append((call_id, tool_result_for_llm))

            if should_rollback_turn:
                continue

            # Reset consecutive rollbacks on successful execution
            if consecutive_rollbacks > 0:
                self.task_log.log_step(
                    "info",
                    f"Main Agent | Turn: {turn_count} | Recovery",
                    f"Successfully recovered after {consecutive_rollbacks} consecutive rollbacks",
                )
            consecutive_rollbacks = 0

            # Update 'last_call_tokens'
            self.llm_client.last_call_tokens = main_agent_last_call_tokens

            # Update message history
            message_history = self.llm_client.update_message_history(
                message_history, all_tool_results_content_with_id
            )

            self.task_log.main_agent_message_history = {
                "system_prompt": system_prompt,
                "message_history": message_history,
            }
            self.task_log.save()

            # Check context length
            temp_summary_prompt = generate_agent_summarize_prompt(
                task_description,
                agent_type="main",
            )

            pass_length_check, message_history = self.llm_client.ensure_summary_context(
                message_history, temp_summary_prompt
            )

            if not pass_length_check:
                turn_count = max_turns
                self.task_log.log_step(
                    "warning",
                    f"Main Agent | Turn: {turn_count} | Context Limit Reached",
                    "Context limit reached, triggering summary",
                )
                break

        await self.stream.end_llm("main")
        await self.stream.end_agent("main", self.current_agent_id)

        # Determine if max turns was reached
        reached_max_turns = turn_count >= max_turns
        if reached_max_turns:
            self.task_log.log_step(
                "warning",
                "Main Agent | Max Turns Reached / Context Limit Reached",
                f"Reached maximum turns ({max_turns}) or context limit reached",
            )
        else:
            self.task_log.log_step(
                "info",
                "Main Agent | Main Loop Completed",
                f"Main loop completed after {turn_count} turns",
            )

        # Final summary
        self.task_log.log_step(
            "info", "Main Agent | Final Summary", "Generating final summary"
        )

        self.current_agent_id = await self.stream.start_agent("Final Summary")
        await self.stream.start_llm("Final Summary")

        # Generate final answer using answer generator
        (
            final_summary,
            final_boxed_answer,
            failure_experience_summary,
            usage_log,
            message_history,
        ) = await self.answer_generator.generate_and_finalize_answer(
            system_prompt=system_prompt,
            message_history=message_history,
            tool_definitions=tool_definitions,
            turn_count=turn_count,
            task_description=task_description,
            reached_max_turns=reached_max_turns,
            is_final_retry=is_final_retry,
            save_callback=self._save_message_history,
        )

        await self.stream.tool_call("show_text", {"text": final_boxed_answer})
        await self.stream.end_llm("Final Summary")
        await self.stream.end_agent("Final Summary", self.current_agent_id)
        await self.stream.end_workflow(workflow_id)

        self.task_log.log_step(
            "info", "Main Agent | Usage Calculation", f"Usage log: {usage_log}"
        )

        self.task_log.log_step(
            "info",
            "Main Agent | Final boxed answer",
            f"Final boxed answer:\n\n{final_boxed_answer}",
        )

        self.task_log.log_step(
            "info",
            "Main Agent | Task Completed",
            f"Main agent task {task_id} completed successfully",
        )
        gc.collect()
        return final_summary, final_boxed_answer, failure_experience_summary
