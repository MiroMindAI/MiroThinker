# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

import asyncio
import gc
import json
import logging
import os
import time
import uuid
from collections import defaultdict
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from miroflow_tools.manager import ToolManager
from omegaconf import DictConfig

from ..config.settings import expose_sub_agents_as_tools
from ..io.input_handler import process_input
from ..io.output_formatter import OutputFormatter
from ..llm.factory import ClientFactory
from ..logging.task_logger import (
    TaskLog,
    get_utc_plus_8_time,
)
from ..utils.parsing_utils import extract_llm_response_text
from ..utils.prompt_utils import (
    generate_agent_specific_system_prompt,
    generate_agent_summarize_prompt,
    mcp_tags,
    refusal_keywords,
)
from ..utils.wrapper_utils import ErrorBox, ResponseBox

logger = logging.getLogger(__name__)


def _list_tools(sub_agent_tool_managers: Dict[str, ToolManager]):
    # Use a dictionary to store the cached result
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
    def __init__(
        self,
        main_agent_tool_manager: ToolManager,
        sub_agent_tool_managers: Dict[str, ToolManager],
        llm_client: ClientFactory,
        output_formatter: OutputFormatter,
        cfg: DictConfig,
        task_log: Optional["TaskLog"] = None,
        stream_queue: Optional[Any] = None,
        tool_definitions: Optional[List[Dict[str, Any]]] = None,
        sub_agent_tool_definitions: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ):
        self.main_agent_tool_manager = main_agent_tool_manager
        self.sub_agent_tool_managers = sub_agent_tool_managers
        self.llm_client = llm_client
        self.output_formatter = output_formatter
        self.cfg = cfg
        self.task_log = task_log
        self.stream_queue = stream_queue
        self.tool_definitions = tool_definitions
        self.sub_agent_tool_definitions = sub_agent_tool_definitions
        # call this once, then use cache value
        self._list_sub_agent_tools = None
        if sub_agent_tool_managers:
            self._list_sub_agent_tools = _list_tools(sub_agent_tool_managers)

        # Pass task_log to llm_client
        if self.llm_client and task_log:
            self.llm_client.task_log = task_log

        # Track boxed answers extracted during main loop turns
        self.intermediate_boxed_answers = []
        # Record used subtask / q / Query
        self.used_queries = {}

        # Retry loop protection limits
        self.MAX_CONSECUTIVE_ROLLBACKS = 10
        self.MAX_TOTAL_ATTEMPTS_MULTIPLIER = 3
        self.MAX_FINAL_ANSWER_RETRIES = 3

    async def _stream_update(self, event_type: str, data: dict):
        """Send streaming update in new SSE protocol format"""
        if self.stream_queue:
            try:
                stream_message = {
                    "event": event_type,
                    "data": data,
                }
                await self.stream_queue.put(stream_message)
            except Exception as e:
                logger.warning(f"Failed to send stream update: {e}")

    async def _stream_start_workflow(self, user_input: str) -> str:
        """Send start_of_workflow event"""
        workflow_id = str(uuid.uuid4())
        await self._stream_update(
            "start_of_workflow",
            {
                "workflow_id": workflow_id,
                "input": [
                    {
                        "role": "user",
                        "content": user_input,
                    }
                ],
            },
        )
        return workflow_id

    async def _stream_end_workflow(self, workflow_id: str):
        """Send end_of_workflow event"""
        await self._stream_update(
            "end_of_workflow",
            {
                "workflow_id": workflow_id,
            },
        )

    async def _stream_show_error(self, error: str):
        """Send show_error event"""
        await self._stream_tool_call("show_error", {"error": error})
        if self.stream_queue:
            try:
                await self.stream_queue.put(None)
            except Exception as e:
                logger.warning(f"Failed to send show_error: {e}")

    async def _stream_start_agent(self, agent_name: str, display_name: str = None):
        """Send start_of_agent event"""
        agent_id = str(uuid.uuid4())
        await self._stream_update(
            "start_of_agent",
            {
                "agent_name": agent_name,
                "display_name": display_name,
                "agent_id": agent_id,
            },
        )
        return agent_id

    async def _stream_end_agent(self, agent_name: str, agent_id: str):
        """Send end_of_agent event"""
        await self._stream_update(
            "end_of_agent",
            {
                "agent_name": agent_name,
                "agent_id": agent_id,
            },
        )

    async def _stream_start_llm(self, agent_name: str, display_name: str = None):
        """Send start_of_llm event"""
        await self._stream_update(
            "start_of_llm",
            {
                "agent_name": agent_name,
                "display_name": display_name,
            },
        )

    async def _stream_end_llm(self, agent_name: str):
        """Send end_of_llm event"""
        await self._stream_update(
            "end_of_llm",
            {
                "agent_name": agent_name,
            },
        )

    async def _stream_message(self, message_id: str, delta_content: str):
        """Send message event"""
        await self._stream_update(
            "message",
            {
                "message_id": message_id,
                "delta": {
                    "content": delta_content,
                },
            },
        )

    async def _stream_tool_call(
        self,
        tool_name: str,
        payload: dict,
        streaming: bool = False,
        tool_call_id: str = None,
    ) -> str:
        """Send tool_call event"""
        if not tool_call_id:
            tool_call_id = str(uuid.uuid4())

        if streaming:
            for key, value in payload.items():
                await self._stream_update(
                    "tool_call",
                    {
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "delta_input": {key: value},
                    },
                )
        else:
            # Send complete tool call
            await self._stream_update(
                "tool_call",
                {
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "tool_input": payload,
                },
            )

        return tool_call_id

    def get_scrape_result(self, result: str) -> str:
        """
        Process scrape result and truncate if too long to support more conversation turns.
        """
        SCRAPE_MAX_LENGTH = 20000
        try:
            scrape_result_dict = json.loads(result)
            text = scrape_result_dict.get("text")
            if text and len(text) > SCRAPE_MAX_LENGTH:
                text = text[:SCRAPE_MAX_LENGTH]
            return json.dumps({"text": text}, ensure_ascii=False)
        except json.JSONDecodeError:
            if isinstance(result, str) and len(result) > SCRAPE_MAX_LENGTH:
                result = result[:SCRAPE_MAX_LENGTH]
            return result

    def post_process_tool_call_result(self, tool_name, tool_call_result: dict):
        """Process tool call results"""
        # Only in demo mode: truncate scrape results to 20,000 chars
        # to support more conversation turns. Skipped in perf tests to avoid loss.
        if os.environ.get("DEMO_MODE") == "1":
            if "result" in tool_call_result and tool_name in [
                "scrape",
                "scrape_website",
            ]:
                tool_call_result["result"] = self.get_scrape_result(
                    tool_call_result["result"]
                )
        return tool_call_result

    def _get_query_str_from_tool_call(
        self, tool_name: str, arguments: dict
    ) -> Optional[str]:
        """
        Extracts the query string from tool call arguments based on tool_name.
        Supports search_and_browse, google_search, sougou_search, scrape_website, and scrape_and_extract_info.
        """
        if tool_name == "search_and_browse":
            return arguments.get("subtask")
        elif tool_name == "google_search":
            return arguments.get("q")
        elif tool_name == "sougou_search":
            return arguments.get("Query")
        elif tool_name == "scrape_website":
            return arguments.get("url")
        elif tool_name == "scrape_and_extract_info":
            return arguments.get("url", "") + "_" + arguments.get("info_to_extract", "")
        return None

    async def _handle_llm_call(
        self,
        system_prompt,
        message_history,
        tool_definitions,
        step_id: int,
        purpose: str = "",
        agent_type: str = "main",
    ) -> Tuple[Optional[str], bool, Optional[Any], List[Dict[str, Any]]]:
        """Unified LLM call and logging processing
        Returns:
            Tuple[Optional[str], bool, Optional[Any], List[Dict[str, Any]]]:
                (response_text, should_break, tool_calls_info, message_history)
        """
        original_message_history = message_history
        try:
            response, message_history = await self.llm_client.create_message(
                system_prompt=system_prompt,
                message_history=message_history,
                tool_definitions=tool_definitions,
                keep_tool_result=self.cfg.agent.keep_tool_result,
                step_id=step_id,
                task_log=self.task_log,
                agent_type=agent_type,
            )
            if ErrorBox.is_error_box(response):
                await self._stream_show_error(str(response))
                response = None
            if ResponseBox.is_response_box(response):
                if response.has_extra_info():
                    extra_info = response.get_extra_info()
                    if extra_info.get("warning_msg"):
                        await self._stream_show_error(
                            extra_info.get("warning_msg", "Empty warning message")
                        )

                response = response.get_response()
            # Check if response is None (indicating an error occurred)
            if response is None:
                self.task_log.log_step(
                    "error",
                    f"{purpose} | LLM Call Failed",
                    f"{purpose} failed - no response received",
                )
                return "", False, None, original_message_history

            # Use client's response processing method
            assistant_response_text, should_break, message_history = (
                self.llm_client.process_llm_response(
                    response, message_history, agent_type
                )
            )

            # Use client's tool call information extraction method
            tool_calls_info = self.llm_client.extract_tool_calls_info(
                response, assistant_response_text
            )

            self.task_log.log_step(
                "info",
                f"{purpose} | LLM Call",
                "completed successfully",
            )
            return (
                assistant_response_text,
                should_break,
                tool_calls_info,
                message_history,
            )

        except Exception as e:
            self.task_log.log_step(
                "error",
                f"{purpose} | LLM Call ERROR",
                f"{purpose} error: {str(e)}",
            )
            # Return empty response with should_break=False, need to retry
            return "", False, None, original_message_history

    async def run_sub_agent(
        self,
        sub_agent_name: str,
        task_description: str,
    ):
        """Run sub agent"""
        task_description += "\n\nPlease provide the answer and detailed supporting information of the subtask given to you."
        self.task_log.log_step(
            "info",
            f"{sub_agent_name} | Task Description",
            f"Subtask: {task_description}",
        )

        # Stream sub-agent start
        display_name = sub_agent_name.replace("agent-", "")
        sub_agent_id = await self._stream_start_agent(display_name)
        await self._stream_start_llm(display_name)

        # Start new sub-agent session
        self.task_log.start_sub_agent_session(sub_agent_name, task_description)

        # Simplified initial user content (no file attachments)
        initial_user_content = task_description
        message_history = [{"role": "user", "content": initial_user_content}]

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
        consecutive_rollbacks = 0
        max_total_attempts = max_turns * self.MAX_TOTAL_ATTEMPTS_MULTIPLIER

        while turn_count < max_turns and total_attempts < max_total_attempts:
            turn_count += 1
            total_attempts += 1
            if consecutive_rollbacks >= self.MAX_CONSECUTIVE_ROLLBACKS:
                self.task_log.log_step(
                    "error",
                    f"{sub_agent_name} | Too Many Rollbacks",
                    f"Reached {consecutive_rollbacks} consecutive rollbacks (limit: {self.MAX_CONSECUTIVE_ROLLBACKS}), breaking loop. Total attempts: {total_attempts}/{max_total_attempts}",
                )
                break

            self.task_log.save()

            # Reset 'last_call_tokens'
            self.llm_client.last_call_tokens = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
            }

            # Use unified LLM call processing
            (
                assistant_response_text,
                should_break,
                tool_calls,
                message_history,
            ) = await self._handle_llm_call(
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

            # Process LLM response
            elif assistant_response_text:
                text_response = extract_llm_response_text(assistant_response_text)
                if text_response:
                    await self._stream_tool_call("show_text", {"text": text_response})

            else:
                # LLM call failed, end current turn
                self.task_log.log_step(
                    "info",
                    f"{sub_agent_name} | Turn: {turn_count} | LLM Call",
                    "LLM call failed",
                )
                await asyncio.sleep(5)
                continue

            # Use tool calls parsed from LLM response
            if not tool_calls:
                if any(mcp_tag in assistant_response_text for mcp_tag in mcp_tags):
                    turn_count -= 1
                    consecutive_rollbacks += 1
                    if message_history[-1]["role"] == "assistant":
                        message_history.pop()
                    self.task_log.log_step(
                        "warning",
                        f"{sub_agent_name} | Turn: {turn_count} | Rollback",
                        f"Tool call format incorrect - found MCP tags in response. Consecutive rollbacks: {consecutive_rollbacks}/{self.MAX_CONSECUTIVE_ROLLBACKS}, Total attempts: {total_attempts}/{max_total_attempts}",
                    )
                    continue
                elif any(
                    keyword in assistant_response_text for keyword in refusal_keywords
                ):
                    turn_count -= 1
                    consecutive_rollbacks += 1
                    matched_keywords = [
                        kw for kw in refusal_keywords if kw in assistant_response_text
                    ]
                    if message_history[-1]["role"] == "assistant":
                        message_history.pop()
                    self.task_log.log_step(
                        "warning",
                        f"{sub_agent_name} | Turn: {turn_count} | Rollback",
                        f"LLM refused to answer - found refusal keywords: {matched_keywords}. Consecutive rollbacks: {consecutive_rollbacks}/{self.MAX_CONSECUTIVE_ROLLBACKS}, Total attempts: {total_attempts}/{max_total_attempts}",
                    )
                    continue
                else:
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

                self.task_log.log_step(
                    "info",
                    f"{sub_agent_name} | Turn: {turn_count} | Tool Call",
                    f"Executing {tool_name} on {server_name}",
                )

                call_start_time = time.time()
                try:
                    # Check for duplicate query before sending stream events
                    query_str = self._get_query_str_from_tool_call(tool_name, arguments)
                    if query_str:
                        cache_name = sub_agent_id + "_" + tool_name
                        self.used_queries.setdefault(cache_name, defaultdict(int))
                        count = self.used_queries[cache_name][query_str]
                        if count > 0:
                            message_history.pop()
                            turn_count -= 1
                            should_rollback_turn = True
                            break  # Exit inner for loop, then continue outer while loop

                    # Send stream event only after duplicate check
                    tool_call_id = await self._stream_tool_call(tool_name, arguments)

                    # Execute tool call
                    tool_result = await self.sub_agent_tool_managers[
                        sub_agent_name
                    ].execute_tool_call(server_name, tool_name, arguments)

                    # Update query count if successful
                    if query_str and "error" not in tool_result:
                        self.used_queries[cache_name][query_str] += 1

                    # Only in demo mode: truncate scrape results to 20,000 chars
                    tool_result = self.post_process_tool_call_result(
                        tool_name, tool_result
                    )
                    result = (
                        tool_result.get("result")
                        if tool_result.get("result")
                        else tool_result.get("error")
                    )

                    # Check for "Unknown tool:" error and rollback
                    if str(result).startswith("Unknown tool:"):
                        message_history.pop()
                        turn_count -= 1
                        consecutive_rollbacks += 1
                        should_rollback_turn = True
                        self.task_log.log_step(
                            "warning",
                            f"{sub_agent_name} | Turn: {turn_count} | Rollback",
                            f"Unknown tool error - tool: {tool_name}, error: '{str(result)[:200]}'. Consecutive rollbacks: {consecutive_rollbacks}/{self.MAX_CONSECUTIVE_ROLLBACKS}, Total attempts: {total_attempts}/{max_total_attempts}",
                        )
                        break  # Exit inner for loop, then continue outer while loop

                    await self._stream_tool_call(
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

            # Check if we need to rollback and retry the turn
            if should_rollback_turn:
                continue  # Continue outer while loop

            # Reset consecutive rollbacks on successful execution
            if consecutive_rollbacks > 0:
                self.task_log.log_step(
                    "info",
                    f"{sub_agent_name} | Turn: {turn_count} | Recovery",
                    f"Successfully recovered after {consecutive_rollbacks} consecutive rollbacks",
                )
            consecutive_rollbacks = 0

            # Record tool calls to current sub-agent turn
            message_history = self.llm_client.update_message_history(
                message_history, all_tool_results_content_with_id
            )

            # Generate summary_prompt to check token limits
            temp_summary_prompt = generate_agent_summarize_prompt(
                task_description,
                agent_type=sub_agent_name,
            )

            pass_length_check, message_history = self.llm_client.ensure_summary_context(
                message_history, temp_summary_prompt
            )

            # Check if current context will exceed limits, if so automatically rollback messages and trigger summary
            if not pass_length_check:
                # Context exceeded limits, set turn_count to trigger summary
                turn_count = max_turns
                self.task_log.log_step(
                    "info",
                    f"{sub_agent_name} | Turn: {turn_count} | Context Limit Reached",
                    "Context limit reached, triggering summary",
                )
                break

        # Record browsing agent loop end
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

        # Final summary
        self.task_log.log_step(
            "info",
            f"{sub_agent_name} | Final Summary",
            f"Generating {sub_agent_name} final summary",
        )

        # Generate sub agent summary prompt
        summary_prompt = generate_agent_summarize_prompt(
            task_description,
            agent_type=sub_agent_name,
        )

        if message_history[-1]["role"] == "user":
            message_history.pop()
        message_history.append({"role": "user", "content": summary_prompt})

        await self._stream_tool_call(
            "Partial Summary", {}, tool_call_id=str(uuid.uuid4())
        )

        # Use unified LLM call processing to generate final summary
        (
            final_answer_text,
            should_break,
            tool_calls_info,
            message_history,
        ) = await self._handle_llm_call(
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

        self.task_log.sub_agent_message_history_sessions[
            self.task_log.current_sub_agent_session_id
        ] = {"system_prompt": system_prompt, "message_history": message_history}

        self.task_log.save()
        self.task_log.end_sub_agent_session(sub_agent_name)

        # Remove thinking content in tool response
        # For the return result of a sub-agent, the content within the `<think>` tags is unnecessary in any case.
        final_answer_text = final_answer_text.split("<think>")[-1].strip()
        final_answer_text = final_answer_text.split("</think>")[-1].strip()

        # Stream sub-agent end
        await self._stream_end_llm(display_name)
        await self._stream_end_agent(display_name, sub_agent_id)

        # Return final answer instead of conversation log, so main agent can use it directly
        return final_answer_text

    async def run_main_agent(
        self, task_description, task_file_name=None, task_id="default_task"
    ):
        """Execute the main end-to-end task"""
        workflow_id = await self._stream_start_workflow(task_description)

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

        # Main loop: LLM <-> Tools
        max_turns = self.cfg.agent.main_agent.max_turns
        turn_count = 0
        total_attempts = 0
        consecutive_rollbacks = 0
        max_total_attempts = max_turns * self.MAX_TOTAL_ATTEMPTS_MULTIPLIER

        self.current_agent_id = await self._stream_start_agent("main")
        await self._stream_start_llm("main")
        while turn_count < max_turns and total_attempts < max_total_attempts:
            turn_count += 1
            total_attempts += 1
            if consecutive_rollbacks >= self.MAX_CONSECUTIVE_ROLLBACKS:
                self.task_log.log_step(
                    "error",
                    "Main Agent | Too Many Rollbacks",
                    f"Reached {consecutive_rollbacks} consecutive rollbacks (limit: {self.MAX_CONSECUTIVE_ROLLBACKS}), breaking loop. Total attempts: {total_attempts}/{max_total_attempts}",
                )
                break

            self.task_log.save()

            # Use unified LLM call processing
            (
                assistant_response_text,
                should_break,
                tool_calls,
                message_history,
            ) = await self._handle_llm_call(
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
                    await self._stream_tool_call("show_text", {"text": text_response})

                # Try to extract boxed content from this turn's response
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
                self.task_log.log_step(
                    "info",
                    f"Main Agent | Turn: {turn_count} | LLM Call",
                    "No valid response from LLM, retrying",
                )
                await asyncio.sleep(5)
                continue

            if not tool_calls:
                if any(mcp_tag in assistant_response_text for mcp_tag in mcp_tags):
                    turn_count -= 1
                    consecutive_rollbacks += 1
                    if message_history[-1]["role"] == "assistant":
                        message_history.pop()
                    self.task_log.log_step(
                        "warning",
                        f"Main Agent | Turn: {turn_count} | Rollback",
                        f"Tool call format incorrect - found MCP tags in response. Consecutive rollbacks: {consecutive_rollbacks}/{self.MAX_CONSECUTIVE_ROLLBACKS}, Total attempts: {total_attempts}/{max_total_attempts}",
                    )
                    continue
                elif any(
                    keyword in assistant_response_text for keyword in refusal_keywords
                ):
                    turn_count -= 1
                    consecutive_rollbacks += 1
                    matched_keywords = [
                        kw for kw in refusal_keywords if kw in assistant_response_text
                    ]
                    if message_history[-1]["role"] == "assistant":
                        message_history.pop()
                    self.task_log.log_step(
                        "warning",
                        f"Main Agent | Turn: {turn_count} | Rollback",
                        f"LLM refused to answer - found refusal keywords: {matched_keywords}. Consecutive rollbacks: {consecutive_rollbacks}/{self.MAX_CONSECUTIVE_ROLLBACKS}, Total attempts: {total_attempts}/{max_total_attempts}",
                    )
                    continue
                else:
                    self.task_log.log_step(
                        "info",
                        f"Main Agent | Turn: {turn_count} | LLM Call",
                        "LLM did not request tool usage, ending process.",
                    )
                    break

            # Execute tool calls (execute in order)
            tool_calls_data = []
            all_tool_results_content_with_id = []
            should_rollback_turn = False
            main_agent_last_call_tokens = self.llm_client.last_call_tokens

            for call in tool_calls:
                server_name = call["server_name"]
                tool_name = call["tool_name"]
                arguments = call["arguments"]
                call_id = call["id"]

                call_start_time = time.time()
                try:
                    if server_name.startswith("agent-") and self.cfg.agent.sub_agents:
                        # Check for duplicate query before sending stream events
                        query_str = self._get_query_str_from_tool_call(
                            tool_name, arguments
                        )
                        if query_str:
                            cache_name = "main_" + tool_name
                            self.used_queries.setdefault(cache_name, defaultdict(int))
                            count = self.used_queries[cache_name][query_str]
                            if count > 0:
                                message_history.pop()
                                turn_count -= 1
                                consecutive_rollbacks += 1
                                should_rollback_turn = True
                                self.task_log.log_step(
                                    "warning",
                                    f"Main Agent | Turn: {turn_count} | Rollback",
                                    f"Duplicate sub-agent query detected - agent: {server_name}, query: '{query_str}', previous count: {count}. Consecutive rollbacks: {consecutive_rollbacks}/{self.MAX_CONSECUTIVE_ROLLBACKS}, Total attempts: {total_attempts}/{max_total_attempts}",
                                )
                                break  # Exit inner for loop, then continue outer while loop

                        # Send stream events only after duplicate check
                        await self._stream_end_llm("main")
                        await self._stream_end_agent("main", self.current_agent_id)

                        # Execute sub-agent
                        sub_agent_result = await self.run_sub_agent(
                            server_name,
                            arguments["subtask"],
                        )

                        # Update query count if successful
                        if query_str:
                            self.used_queries[cache_name][query_str] += 1

                        tool_result = {
                            "server_name": server_name,
                            "tool_name": tool_name,
                            "result": sub_agent_result,
                        }
                        self.current_agent_id = await self._stream_start_agent(
                            "main", display_name="Summarizing"
                        )
                        await self._stream_start_llm("main", display_name="Summarizing")
                    else:
                        # Check for duplicate query before sending stream events
                        query_str = self._get_query_str_from_tool_call(
                            tool_name, arguments
                        )
                        if query_str:
                            cache_name = "main_" + tool_name
                            self.used_queries.setdefault(cache_name, defaultdict(int))
                            count = self.used_queries[cache_name][query_str]
                            if count > 0:
                                message_history.pop()
                                turn_count -= 1
                                consecutive_rollbacks += 1
                                should_rollback_turn = True
                                self.task_log.log_step(
                                    "warning",
                                    f"Main Agent | Turn: {turn_count} | Rollback",
                                    f"Duplicate tool query detected - tool: {tool_name}, query: '{query_str}', previous count: {count}. Consecutive rollbacks: {consecutive_rollbacks}/{self.MAX_CONSECUTIVE_ROLLBACKS}, Total attempts: {total_attempts}/{max_total_attempts}",
                                )
                                break  # Exit inner for loop, then continue outer while loop

                        # Send stream event only after duplicate check
                        tool_call_id = await self._stream_tool_call(
                            tool_name, arguments
                        )

                        # Execute tool call
                        tool_result = (
                            await self.main_agent_tool_manager.execute_tool_call(
                                server_name=server_name,
                                tool_name=tool_name,
                                arguments=arguments,
                            )
                        )

                        # Update query count if successful
                        if query_str and "error" not in tool_result:
                            self.used_queries[cache_name][query_str] += 1
                        # Only in demo mode: truncate scrape results to 20,000 chars
                        tool_result = self.post_process_tool_call_result(
                            tool_name, tool_result
                        )
                        result = (
                            tool_result.get("result")
                            if tool_result.get("result")
                            else tool_result.get("error")
                        )

                        # Check for "Unknown tool:" error and rollback
                        if str(result).startswith("Unknown tool:"):
                            message_history.pop()
                            turn_count -= 1
                            consecutive_rollbacks += 1
                            should_rollback_turn = True
                            self.task_log.log_step(
                                "warning",
                                f"Main Agent | Turn: {turn_count} | Rollback",
                                f"Unknown tool error - tool: {tool_name}, error: '{str(result)[:200]}'. Consecutive rollbacks: {consecutive_rollbacks}/{self.MAX_CONSECUTIVE_ROLLBACKS}, Total attempts: {total_attempts}/{max_total_attempts}",
                            )
                            break  # Exit inner for loop, then continue outer while loop

                        await self._stream_tool_call(
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

                # Format results to feedback to LLM (more concise)
                tool_result_for_llm = self.output_formatter.format_tool_result_for_user(
                    tool_result
                )

                all_tool_results_content_with_id.append((call_id, tool_result_for_llm))

            # Check if we need to rollback and retry the turn
            if should_rollback_turn:
                continue  # Continue outer while loop

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

            # Update message history with tool calls data (llm client specific)
            message_history = self.llm_client.update_message_history(
                message_history, all_tool_results_content_with_id
            )

            self.task_log.main_agent_message_history = {
                "system_prompt": system_prompt,
                "message_history": message_history,
            }
            self.task_log.save()

            # Assess current context length, determine if we need to trigger summary
            temp_summary_prompt = generate_agent_summarize_prompt(
                task_description,
                agent_type="main",
            )

            pass_length_check, message_history = self.llm_client.ensure_summary_context(
                message_history, temp_summary_prompt
            )

            # Check if current context will exceed limits, if so automatically rollback messages and trigger summary
            if not pass_length_check:
                turn_count = max_turns
                self.task_log.log_step(
                    "warning",
                    f"Main Agent | Turn: {turn_count} | Context Limit Reached",
                    "Context limit reached, triggering summary",
                )
                break

        await self._stream_end_llm("main")
        await self._stream_end_agent("main", self.current_agent_id)

        # Record main loop end
        if turn_count >= max_turns:
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

        self.current_agent_id = await self._stream_start_agent("Final Summary")
        await self._stream_start_llm("Final Summary")

        # Generate summary prompt (generate only once)
        summary_prompt = generate_agent_summarize_prompt(
            task_description,
            agent_type="main",
        )

        if message_history[-1]["role"] == "user":
            message_history.pop(-1)
        message_history.append({"role": "user", "content": summary_prompt})

        # Retry mechanism for generating boxed answer
        final_answer_text = None
        final_boxed_answer = None
        final_summary = ""
        usage_log = ""

        for retry_idx in range(self.MAX_FINAL_ANSWER_RETRIES):
            # Use unified LLM call processing
            (
                final_answer_text,
                should_break,
                tool_calls_info,
                message_history,
            ) = await self._handle_llm_call(
                system_prompt,
                message_history,
                tool_definitions,
                turn_count + 1 + retry_idx,
                f"Main agent | Final Summary (attempt {retry_idx + 1}/{self.MAX_FINAL_ANSWER_RETRIES})",
                agent_type="main",
            )

            if final_answer_text:
                # Try to extract boxed answer
                final_summary, final_boxed_answer, usage_log = (
                    self.output_formatter.format_final_summary_and_log(
                        final_answer_text, self.llm_client
                    )
                )

                # Check if we got a valid boxed answer
                if (
                    final_boxed_answer
                    != "No \\boxed{} content found in the final answer."
                ):
                    self.task_log.log_step(
                        "info",
                        "Main Agent | Final Answer",
                        f"Boxed answer found on attempt {retry_idx + 1}",
                    )
                    break
                else:
                    self.task_log.log_step(
                        "warning",
                        "Main Agent | Final Answer",
                        f"No boxed answer on attempt {retry_idx + 1}, retrying...",
                    )
                    # Remove the failed assistant response before retry
                    if retry_idx < self.MAX_FINAL_ANSWER_RETRIES - 1:
                        if (
                            message_history
                            and message_history[-1]["role"] == "assistant"
                        ):
                            message_history.pop()
            else:
                self.task_log.log_step(
                    "warning",
                    "Main Agent | Final Answer",
                    f"Failed to generate answer on attempt {retry_idx + 1}",
                )
                # Remove the failed assistant response before retry
                if retry_idx < self.MAX_FINAL_ANSWER_RETRIES - 1:
                    if message_history and message_history[-1]["role"] == "assistant":
                        message_history.pop()

        self.task_log.main_agent_message_history = {
            "system_prompt": system_prompt,
            "message_history": message_history,
        }
        self.task_log.save()

        # Final validation and fallback
        if not final_answer_text:
            final_answer_text = "No final answer generated."
            final_summary = final_answer_text
            final_boxed_answer = "No \\boxed{} content found in the final answer."
            self.task_log.log_step(
                "error",
                "Main Agent | Final Answer",
                "Unable to generate final answer after all retries",
            )
        else:
            self.task_log.log_step(
                "info",
                "Main Agent | Final Answer",
                f"Final answer content:\n\n{final_answer_text}",
            )

        # Fallback to intermediate answer if still no boxed answer
        if (
            final_boxed_answer == "No \\boxed{} content found in the final answer."
            and self.intermediate_boxed_answers
        ):
            final_boxed_answer = self.intermediate_boxed_answers[-1]
            self.task_log.log_step(
                "info",
                "Main Agent | Final Answer",
                f"Using intermediate boxed answer as fallback: {final_boxed_answer}",
            )

        await self._stream_tool_call("show_text", {"text": final_boxed_answer})
        await self._stream_end_llm("Final Summary")
        await self._stream_end_agent("Final Summary", self.current_agent_id)
        await self._stream_end_workflow(workflow_id)

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
        return final_summary, final_boxed_answer
