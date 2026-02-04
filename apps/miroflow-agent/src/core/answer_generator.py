# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

"""
Answer generator module for final answer generation and context management.

This module provides the AnswerGenerator class that handles:
- LLM call processing
- Failure summary generation for context compression
- Final answer generation with retries
- Context management fallback strategies
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from omegaconf import DictConfig

from ..io.output_formatter import OutputFormatter
from ..llm.base_client import BaseClient
from ..logging.task_logger import TaskLog
from ..utils.parsing_utils import extract_failure_experience_summary
from ..utils.prompt_utils import (
    FAILURE_SUMMARY_ASSISTANT_PREFIX,
    FAILURE_SUMMARY_PROMPT,
    FORMAT_ERROR_MESSAGE,
    generate_agent_summarize_prompt,
)
from ..utils.wrapper_utils import ErrorBox, ResponseBox
from .stream_handler import StreamHandler

logger = logging.getLogger(__name__)

# Safety limits for retry loops
DEFAULT_MAX_FINAL_ANSWER_RETRIES = 3


class AnswerGenerator:
    """
    Generator for final answers with context management support.

    Handles the generation of final answers, failure summaries for retry,
    and various fallback strategies based on context management settings.
    """

    def __init__(
        self,
        llm_client: BaseClient,
        output_formatter: OutputFormatter,
        task_log: TaskLog,
        stream_handler: StreamHandler,
        cfg: DictConfig,
        intermediate_boxed_answers: List[str],
    ):
        """
        Initialize the answer generator.

        Args:
            llm_client: The LLM client for API calls
            output_formatter: Formatter for output processing
            task_log: Logger for task execution
            stream_handler: Handler for streaming events
            cfg: Configuration object
            intermediate_boxed_answers: List to track intermediate answers
        """
        self.llm_client = llm_client
        self.output_formatter = output_formatter
        self.task_log = task_log
        self.stream = stream_handler
        self.cfg = cfg
        self.intermediate_boxed_answers = intermediate_boxed_answers

        # Context management settings
        self.context_compress_limit = cfg.agent.get("context_compress_limit", 0)
        self.max_final_answer_retries = (
            DEFAULT_MAX_FINAL_ANSWER_RETRIES if cfg.agent.keep_tool_result == -1 else 1
        )

    async def handle_llm_call(
        self,
        system_prompt: str,
        message_history: List[Dict[str, Any]],
        tool_definitions: List[Dict],
        step_id: int,
        purpose: str = "",
        agent_type: str = "main",
    ) -> Tuple[Optional[str], bool, Optional[Any], List[Dict[str, Any]]]:
        """
        Unified LLM call and logging processing.

        Args:
            system_prompt: System prompt for the LLM
            message_history: Conversation history
            tool_definitions: Available tool definitions
            step_id: Current step ID for logging
            purpose: Description of the call purpose
            agent_type: Type of agent making the call

        Returns:
            Tuple of (response_text, should_break, tool_calls_info, message_history)
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
                await self.stream.show_error(str(response))
                response = None

            if ResponseBox.is_response_box(response):
                if response.has_extra_info():
                    extra_info = response.get_extra_info()
                    if extra_info.get("warning_msg"):
                        await self.stream.show_error(
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

    async def generate_failure_summary(
        self,
        system_prompt: str,
        message_history: List[Dict[str, Any]],
        tool_definitions: List[Dict],
        turn_count: int,
    ) -> Optional[str]:
        """
        Generate a failure experience summary for context compression.

        This is the core of the context management mechanism. When a task attempt fails
        (i.e., the task is not completed within the given turns and context window),
        we compress the entire conversation history into a structured summary containing:
        - Failure type: incomplete / blocked / misdirected / format_missed
        - What happened: the approach taken and why a final answer was not reached
        - Useful findings: facts, intermediate results, or conclusions to be reused

        Args:
            system_prompt: The system prompt used in the conversation
            message_history: The full conversation history to be compressed
            tool_definitions: Available tool definitions
            turn_count: Current turn count for step ID

        Returns:
            The compressed failure experience summary, or None if generation failed
        """
        self.task_log.log_step(
            "info",
            "Main Agent | Failure Summary",
            "Generating failure experience summary for potential retry...",
        )

        # Build failure summary history
        failure_summary_history = message_history.copy()
        if failure_summary_history and failure_summary_history[-1]["role"] == "user":
            failure_summary_history.pop()

        # Add failure summary prompt and assistant prefix for structured output
        failure_summary_history.append(
            {"role": "user", "content": FAILURE_SUMMARY_PROMPT}
        )
        failure_summary_history.append(
            {"role": "assistant", "content": FAILURE_SUMMARY_ASSISTANT_PREFIX}
        )

        # Call LLM to generate failure summary
        (
            failure_summary_text,
            _,
            _,
            _,
        ) = await self.handle_llm_call(
            system_prompt,
            failure_summary_history,
            tool_definitions,
            turn_count + 10,  # Use a different step id
            "Main Agent | Failure Experience Summary",
            agent_type="main",
        )

        # Prepend the assistant prefix to the response for complete output
        if failure_summary_text:
            failure_summary_text = (
                FAILURE_SUMMARY_ASSISTANT_PREFIX + failure_summary_text
            )
            failure_experience_summary = extract_failure_experience_summary(
                failure_summary_text
            )
            # Truncate for logging, but only add "..." if actually truncated
            log_preview = failure_experience_summary[:500]
            if len(failure_experience_summary) > 500:
                log_preview += "..."
            self.task_log.log_step(
                "info",
                "Main Agent | Failure Summary",
                f"Generated failure experience summary:\n{log_preview}",
            )
            return failure_experience_summary
        else:
            self.task_log.log_step(
                "warning",
                "Main Agent | Failure Summary",
                "Failed to generate failure experience summary",
            )
            return None

    async def generate_final_answer_with_retries(
        self,
        system_prompt: str,
        message_history: List[Dict[str, Any]],
        tool_definitions: List[Dict],
        turn_count: int,
        task_description: str,
    ) -> Tuple[Optional[str], str, Optional[str], str, List[Dict[str, Any]]]:
        """
        Generate final answer with retry mechanism.

        Args:
            system_prompt: System prompt for the LLM
            message_history: Conversation history
            tool_definitions: Available tool definitions
            turn_count: Current turn count
            task_description: Original task description

        Returns:
            Tuple of (final_answer_text, final_summary, final_boxed_answer, usage_log, message_history)
        """
        # Generate summary prompt
        summary_prompt = generate_agent_summarize_prompt(
            task_description,
            agent_type="main",
        )

        if message_history[-1]["role"] == "user":
            message_history.pop(-1)
        message_history.append({"role": "user", "content": summary_prompt})

        final_answer_text = None
        final_boxed_answer = None
        final_summary = ""
        usage_log = ""

        for retry_idx in range(self.max_final_answer_retries):
            (
                final_answer_text,
                should_break,
                tool_calls_info,
                message_history,
            ) = await self.handle_llm_call(
                system_prompt,
                message_history,
                tool_definitions,
                turn_count + 1 + retry_idx,
                f"Main agent | Final Summary (attempt {retry_idx + 1}/{self.max_final_answer_retries})",
                agent_type="main",
            )

            if final_answer_text:
                final_summary, final_boxed_answer, usage_log = (
                    self.output_formatter.format_final_summary_and_log(
                        final_answer_text, self.llm_client
                    )
                )

                if final_boxed_answer != FORMAT_ERROR_MESSAGE:
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
                    if retry_idx < self.max_final_answer_retries - 1:
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
                if retry_idx < self.max_final_answer_retries - 1:
                    if message_history and message_history[-1]["role"] == "assistant":
                        message_history.pop()

        # Ensure final_boxed_answer is never None
        if final_boxed_answer is None:
            final_boxed_answer = FORMAT_ERROR_MESSAGE

        return (
            final_answer_text,
            final_summary,
            final_boxed_answer,
            usage_log,
            message_history,
        )

    def handle_no_context_management_fallback(
        self,
        final_answer_text: Optional[str],
        final_summary: str,
        final_boxed_answer: Optional[str],
    ) -> Tuple[str, str, str]:
        """
        Handle fallback when context_compress_limit == 0 (no context management).

        In this mode, the model has only one chance to answer.
        We should try to use intermediate answers as fallback to maximize accuracy.

        Args:
            final_answer_text: The generated final answer text
            final_summary: The final summary
            final_boxed_answer: The extracted boxed answer

        Returns:
            Tuple of (final_answer_text, final_summary, final_boxed_answer)
        """
        # Validate final_answer_text
        if not final_answer_text:
            final_answer_text = "No final answer generated."
            final_summary = final_answer_text
            final_boxed_answer = FORMAT_ERROR_MESSAGE
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

        # Fallback to intermediate answer if no valid boxed answer
        if (
            final_boxed_answer == FORMAT_ERROR_MESSAGE or final_boxed_answer is None
        ) and self.intermediate_boxed_answers:
            final_boxed_answer = self.intermediate_boxed_answers[-1]
            self.task_log.log_step(
                "info",
                "Main Agent | Final Answer (No Context Management)",
                f"Using intermediate boxed answer as fallback: {final_boxed_answer}",
            )

        # Ensure final_boxed_answer is never None
        if final_boxed_answer is None:
            final_boxed_answer = FORMAT_ERROR_MESSAGE

        return final_answer_text, final_summary, final_boxed_answer

    def handle_context_management_no_fallback(
        self,
        final_answer_text: Optional[str],
        final_summary: str,
        final_boxed_answer: Optional[str],
    ) -> Tuple[str, str, str]:
        """
        Handle failure when context_compress_limit > 0 (context management enabled).

        In this mode, the model has multiple chances to retry with context management.
        We should NOT guess or use intermediate answers, because:
        - A wrong guess can reduce accuracy
        - The model will have another chance to answer with failure experience

        Args:
            final_answer_text: The generated final answer text
            final_summary: The final summary
            final_boxed_answer: The extracted boxed answer

        Returns:
            Tuple of (final_answer_text, final_summary, final_boxed_answer)
        """
        # Validate final_answer_text
        if not final_answer_text:
            final_answer_text = "No final answer generated."
            final_summary = final_answer_text
            final_boxed_answer = FORMAT_ERROR_MESSAGE
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

        # Ensure final_boxed_answer is never None
        if final_boxed_answer is None:
            final_boxed_answer = FORMAT_ERROR_MESSAGE

        # With context management, do NOT fallback to intermediate answers
        if final_boxed_answer == FORMAT_ERROR_MESSAGE:
            self.task_log.log_step(
                "info",
                "Main Agent | Final Answer (Context Management Mode)",
                "No valid boxed answer found. Not using intermediate fallback - will generate failure summary for retry.",
            )

        return final_answer_text, final_summary, final_boxed_answer

    async def generate_and_finalize_answer(
        self,
        system_prompt: str,
        message_history: List[Dict[str, Any]],
        tool_definitions: List[Dict],
        turn_count: int,
        task_description: str,
        reached_max_turns: bool = False,
        is_final_retry: bool = False,
        save_callback=None,
    ) -> Tuple[str, str, Optional[str], str, List[Dict[str, Any]]]:
        """
        Generate final answer and handle fallback based on context management settings.

        Context Management (context_compress_limit > 0) is essentially a context compression
        mechanism that enables multi-attempt problem solving.

        Decision table based on (context_management, reached_max_turns):

        | Context Management | Reached Max Turns | Behavior                                    |
        |--------------------|-------------------|---------------------------------------------|
        | OFF (limit=0)      | No                | Generate answer → fallback to intermediate  |
        | OFF (limit=0)      | Yes               | Generate answer → fallback to intermediate  |
        | ON  (limit>0)      | No                | Generate answer → no fallback, fail summary |
        | ON  (limit>0)      | Yes               | SKIP generation → fail summary directly     |

        Args:
            system_prompt: System prompt for the LLM
            message_history: Conversation history
            tool_definitions: Available tool definitions
            turn_count: Current turn count
            task_description: Original task description
            reached_max_turns: Whether the main loop ended due to reaching max turns
            save_callback: Optional callback to save message history

        Returns:
            Tuple of (final_summary, final_boxed_answer, failure_experience_summary, usage_log, message_history)
        """
        context_management_enabled = self.context_compress_limit > 0
        failure_experience_summary = None
        usage_log = ""

        # CASE: Context management ON + reached max turns + NOT final retry
        # Skip answer generation entirely - any answer would be a blind guess
        # But if this is the final retry, we still try to generate an answer (last chance)
        if context_management_enabled and reached_max_turns and not is_final_retry:
            self.task_log.log_step(
                "info",
                "Main Agent | Final Answer (Context Management Mode)",
                "Reached max turns. Skipping answer generation to avoid blind guessing.",
            )

            if save_callback:
                save_callback(system_prompt, message_history)

            failure_experience_summary = await self.generate_failure_summary(
                system_prompt, message_history, tool_definitions, turn_count
            )

            return (
                "Task incomplete - reached maximum turns. Will retry with failure experience.",
                FORMAT_ERROR_MESSAGE,
                failure_experience_summary,
                usage_log,
                message_history,
            )

        # ALL OTHER CASES: Generate final answer first
        # (including final retry with reached_max_turns - last chance to get an answer)
        (
            final_answer_text,
            final_summary,
            final_boxed_answer,
            usage_log,
            message_history,
        ) = await self.generate_final_answer_with_retries(
            system_prompt=system_prompt,
            message_history=message_history,
            tool_definitions=tool_definitions,
            turn_count=turn_count,
            task_description=task_description,
        )

        if save_callback:
            save_callback(system_prompt, message_history)

        # CASE: Context management OFF or final retry
        # Try to use intermediate answers as fallback to maximize accuracy
        # For final retry, there's no more retry opportunity, so we use fallback
        if not context_management_enabled or is_final_retry:
            final_answer_text, final_summary, final_boxed_answer = (
                self.handle_no_context_management_fallback(
                    final_answer_text, final_summary, final_boxed_answer
                )
            )
            if is_final_retry:
                self.task_log.log_step(
                    "info",
                    "Main Agent | Final Answer (Final Retry)",
                    "This is the final retry. Using intermediate fallback if available.",
                )
            return (
                final_summary,
                final_boxed_answer,
                None,
                usage_log,
                message_history,
            )

        # CASE: Context management ON + normal completion (not reached max turns, not final retry)
        # Don't use fallback - wrong guess would reduce accuracy
        final_answer_text, final_summary, final_boxed_answer = (
            self.handle_context_management_no_fallback(
                final_answer_text, final_summary, final_boxed_answer
            )
        )

        if final_boxed_answer == FORMAT_ERROR_MESSAGE:
            failure_experience_summary = await self.generate_failure_summary(
                system_prompt, message_history, tool_definitions, turn_count
            )

        return (
            final_summary,
            final_boxed_answer,
            failure_experience_summary,
            usage_log,
            message_history,
        )
