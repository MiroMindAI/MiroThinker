# Copyright (c) 2025 Miromind.ai
# This source code is licensed under the MIT License.

import asyncio
import dataclasses
import logging
from typing import Any, Dict, List, Tuple, Union

import tiktoken
from anthropic import (
    NOT_GIVEN,
    Anthropic,
    AsyncAnthropic,
    DefaultAsyncHttpxClient,
    DefaultHttpxClient,
)
from tenacity import retry, stop_after_attempt, wait_fixed

from ...utils.prompt_utils import generate_mcp_system_prompt
from ..base_client import BaseClient

logger = logging.getLogger("miroflow_agent")


@dataclasses.dataclass
class AnthropicClient(BaseClient):
    def __post_init__(self):
        super().__post_init__()

        # Anthropic-specific token counters
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.cache_creation_tokens: int = 0
        self.cache_read_tokens: int = 0

    def _create_client(self) -> Union[AsyncAnthropic, Anthropic]:
        """Create LLM client"""
        http_client_args = {}

        if self.async_client:
            return AsyncAnthropic(
                api_key=self.api_key,
                base_url=self.base_url,
                http_client=DefaultAsyncHttpxClient(**http_client_args),
            )
        else:
            return Anthropic(
                api_key=self.api_key,
                base_url=self.base_url,
                http_client=DefaultHttpxClient(**http_client_args),
            )

    def _update_token_usage(self, usage_data: Any) -> None:
        """Update cumulative token usage"""
        if usage_data:
            # Update based on actual field names returned by Anthropic API
            self.token_usage["total_cache_write_input_tokens"] += (
                getattr(usage_data, "cache_creation_input_tokens", 0) or 0
            )
            self.token_usage["total_cache_read_input_tokens"] += (
                getattr(usage_data, "cache_read_input_tokens", 0) or 0
            )
            self.token_usage["total_input_tokens"] += (
                getattr(usage_data, "input_tokens", 0) or 0
            )
            self.token_usage["total_output_tokens"] += (
                getattr(usage_data, "output_tokens", 0) or 0
            )
            self.task_log.log_step(
                "info",
                "LLM | Token Usage",
                f"Input: {getattr(usage_data, 'input_tokens', 0)}, "
                f"Cache: {getattr(usage_data, 'cache_creation_input_tokens', 0)}+{getattr(usage_data, 'cache_read_input_tokens', 0)}, "
                f"Output: {getattr(usage_data, 'output_tokens', 0)}",
            )

            self.last_call_tokens = {
                "input_tokens": getattr(usage_data, "input_tokens", 0)
                + getattr(usage_data, "cache_creation_input_tokens", 0)
                + getattr(usage_data, "cache_read_input_tokens", 0),
                "output_tokens": getattr(usage_data, "output_tokens", 0),
            }
        else:
            self.task_log.log_step(
                "warning", "LLM | Token Usage", "Warning: No valid usage_data received."
            )

    @retry(wait=wait_fixed(10), stop=stop_after_attempt(5))
    async def _create_message(
        self,
        system_prompt: str,
        messages_history: List[Dict[str, Any]],
        tools_definitions,
        keep_tool_result: int = -1,
    ):
        """
        Send message to Anthropic API.
        :param system_prompt: System prompt string.
        :param messages_history: Message history list.
        :return: Anthropic API response object or None (if error occurs).
        """
        self.task_log.log_step(
            "info",
            "LLM | Call Start",
            f"Calling LLM ({'async' if self.async_client else 'sync'})",
        )

        messages_copy = self._remove_tool_result_from_messages(
            messages_history, keep_tool_result
        )

        # Apply cache control
        processed_messages = self._apply_cache_control(messages_copy)

        try:
            if self.async_client:
                response = await self.client.messages.create(
                    model=self.model_name,
                    temperature=self.temperature,
                    top_p=self.top_p if self.top_p != 1.0 else NOT_GIVEN,
                    top_k=self.top_k if self.top_k != -1 else NOT_GIVEN,
                    max_tokens=self.max_tokens,
                    repetition_penalty=self.repetition_penalty
                    if self.repetition_penalty != 1.0
                    else NOT_GIVEN,
                    system=[
                        {
                            "type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    messages=processed_messages,
                    stream=False,
                )
            else:
                response = self.client.messages.create(
                    model=self.model_name,
                    temperature=self.temperature,
                    top_p=self.top_p if self.top_p != 1.0 else NOT_GIVEN,
                    top_k=self.top_k if self.top_k != -1 else NOT_GIVEN,
                    max_tokens=self.max_tokens,
                    repetition_penalty=self.repetition_penalty
                    if self.repetition_penalty != 1.0
                    else NOT_GIVEN,
                    system=[
                        {
                            "type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    messages=processed_messages,
                    stream=False,
                )
            self._update_token_usage(getattr(response, "usage", None))
            self.task_log.log_step(
                "info",
                "LLM | Call Status",
                f"LLM call status: {getattr(response, 'stop_reason', 'N/A')}",
            )
            return response, messages_copy
        except asyncio.CancelledError:
            self.task_log.log_step(
                "warning",
                "LLM | Call Cancelled",
                "⚠️ LLM API call was cancelled during execution",
            )
            raise  # Re-raise to allow decorator to log it
        except Exception as e:
            self.task_log.log_step(
                "error", "LLM | Call Failed", f"Anthropic LLM call failed: {str(e)}"
            )
            raise e

    def process_llm_response(
        self, llm_response: Any, message_history: List[Dict], agent_type: str = "main"
    ) -> tuple[str, bool, List[Dict]]:
        """Process LLM response"""
        if not llm_response:
            self.task_log.log_step(
                "error",
                "LLM | Response Processing",
                "❌ LLM call failed, skipping this response.",
            )
            return "", True, message_history

        if not hasattr(llm_response, "content") or not llm_response.content:
            self.task_log.log_step(
                "error",
                "LLM | Response Processing",
                "❌ LLM response is empty or contains no content.",
            )
            return "", True, message_history

        # Extract response content
        assistant_response_text = ""
        assistant_response_content = []

        for block in llm_response.content:
            if block.type == "text":
                assistant_response_text += block.text + "\n"
                assistant_response_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                assistant_response_content.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                )

        # Add assistant response to history
        message_history.append(
            {"role": "assistant", "content": assistant_response_content}
        )

        self.task_log.log_step(
            "info", "LLM | Response", f"LLM Response: {assistant_response_text}"
        )

        return assistant_response_text, False, message_history

    def extract_tool_calls_info(
        self, llm_response: Any, assistant_response_text: str
    ) -> List[Dict]:
        """Extract tool call information from LLM response"""
        from ...utils.parsing_utils import parse_llm_response_for_tool_calls

        return parse_llm_response_for_tool_calls(assistant_response_text)

    def update_message_history(
        self, message_history: List[Dict], all_tool_results_content_with_id: List[Tuple]
    ) -> List[Dict]:
        """Update message history with tool calls data (llm client specific)"""

        merged_text = "\n".join(
            [
                item[1]["text"]
                for item in all_tool_results_content_with_id
                if item[1]["type"] == "text"
            ]
        )

        message_history.append(
            {
                "role": "user",
                "content": [{"type": "text", "text": merged_text}],
            }
        )

        return message_history

    def generate_agent_system_prompt(self, date: Any, mcp_servers: List[Dict]) -> str:
        return generate_mcp_system_prompt(date, mcp_servers)

    def handle_max_turns_reached_summary_prompt(
        self, message_history: List[Dict], summary_prompt: str
    ) -> str:
        """Handle max turns reached summary prompt"""
        if message_history[-1]["role"] == "user":
            last_user_message = message_history.pop()
            return (
                last_user_message["content"][0]["text"]
                + "\n*************\n"
                + summary_prompt
            )
        else:
            return summary_prompt

    def _estimate_tokens(self, text: str) -> int:
        """Use tiktoken to estimate the number of tokens in text"""
        if not hasattr(self, "encoding"):
            # Initialize tiktoken encoder
            try:
                self.encoding = tiktoken.get_encoding("o200k_base")
            except Exception:
                # If o200k_base is not available, use cl100k_base as fallback
                self.encoding = tiktoken.get_encoding("cl100k_base")

        try:
            return len(self.encoding.encode(text))
        except Exception as e:
            # If encoding fails, use simple estimation: approximately 1 token per 4 characters
            self.task_log.log_step(
                "error",
                "LLM | Token Estimation Error",
                f"Error: {str(e)}",
            )
            return len(text) // 4

    def ensure_summary_context(
        self, message_history: list, summary_prompt: str
    ) -> tuple[bool, list]:
        """
        Check if current message_history + summary_prompt will exceed context
        If it will exceed, remove the last assistant-user pair and return False
        Return True to continue, False if messages have been rolled back
        """
        # Get token usage from the last LLM call
        last_input_tokens = self.last_call_tokens.get("input_tokens", 0)
        last_output_tokens = self.last_call_tokens.get("output_tokens", 0)
        buffer_factor = 2

        # Calculate token count for summary prompt
        summary_tokens = self._estimate_tokens(str(summary_prompt)) * buffer_factor

        # Calculate token count for the last user message in message_history (if exists and not sent)
        last_user_tokens = 0
        if message_history[-1]["role"] == "user":
            content = message_history[-1]["content"]
            last_user_tokens = self._estimate_tokens(str(content)) * buffer_factor

        # Calculate total token count: last input + output + last user message + summary + reserved response space
        estimated_total = (
            last_input_tokens
            + last_output_tokens
            + last_user_tokens
            + summary_tokens
            + self.max_tokens
            + 1000  # Add 1000 tokens as buffer
        )

        if estimated_total >= self.max_context_length:
            self.task_log.log_step(
                "info",
                "LLM | Context Limit Reached",
                "Context limit reached, proceeding to step back and summarize the conversation",
            )

            # Remove the last user message (tool call results)
            if message_history[-1]["role"] == "user":
                message_history.pop()

            # Remove the second-to-last assistant message (tool call request)
            if message_history[-1]["role"] == "assistant":
                message_history.pop()

            self.task_log.log_step(
                "info",
                "LLM | Context Limit Reached",
                f"Removed the last assistant-user pair, current message_history length: {len(message_history)}",
            )

            return False, message_history

        self.task_log.log_step(
            "info",
            "LLM | Context Limit Not Reached",
            f"{estimated_total}/{self.max_context_length}",
        )
        return True, message_history

    def format_token_usage_summary(self) -> tuple[List[str], str]:
        """Format token usage statistics, return summary_lines for format_final_summary and log string"""
        token_usage = self.get_token_usage()

        total_input = token_usage.get("total_input_tokens", 0)
        total_output = token_usage.get("total_output_tokens", 0)
        total_cache_creation = token_usage.get("total_cache_write_input_tokens", 0)
        total_cache_read = token_usage.get("total_cache_read_input_tokens", 0)

        summary_lines = []
        summary_lines.append("\n" + "-" * 20 + " Token Usage " + "-" * 20)
        summary_lines.append(f"Total Input Tokens (non-cache): {total_input}")
        summary_lines.append(
            f"Total Cache Creation Input Tokens: {total_cache_creation}"
        )
        summary_lines.append(f"Total Cache Read Input Tokens: {total_cache_read}")
        summary_lines.append(f"Total Output Tokens: {total_output}")
        summary_lines.append("-" * (40 + len(" Token Usage ")))
        summary_lines.append("Pricing is disabled - no cost information available")
        summary_lines.append("-" * (40 + len(" Token Usage ")))

        # Generate log string
        log_string = (
            f"[{self.model_name}] Total Input: {total_input}, "
            f"Cache Creation: {total_cache_creation}, "
            f"Cache Read: {total_cache_read}, "
            f"Output: {total_output}"
        )

        return summary_lines, log_string

    def get_token_usage(self):
        return self.token_usage.copy()

    def _apply_cache_control(self, messages: List[Dict]) -> List[Dict]:
        """Apply cache control to the last user message and system message (if applicable)"""
        cached_messages = []
        user_turns_processed = 0
        for turn in reversed(messages):
            if turn["role"] == "user" and user_turns_processed < 1:
                # Add ephemeral cache control to the text part of the last user message
                new_content = []
                processed_text = False
                # Check if content is a list
                if isinstance(turn["content"], str):
                    turn["content"] = [{"type": "text", "text": turn["content"]}]
                if isinstance(turn.get("content"), list):
                    # see example here
                    # https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
                    for item in turn["content"]:
                        if (
                            item.get("type") == "text"
                            and len(item.get("text")) > 0
                            and not processed_text
                        ):
                            # Copy and add cache control
                            text_item = item.copy()
                            text_item["cache_control"] = {"type": "ephemeral"}
                            new_content.append(text_item)
                            processed_text = True
                        else:
                            # Other types of content (like image) copied directly
                            new_content.append(item.copy())
                    cached_messages.append({"role": "user", "content": new_content})
                else:
                    # If content is not a list (e.g., plain text), add as is without cache control
                    # Or adjust logic as needed
                    self.task_log.log_step(
                        "warning",
                        "LLM | Cache Control",
                        "Warning: User message content is not in expected list format, cache control not applied.",
                    )
                    cached_messages.append(turn)

                user_turns_processed += 1
            else:
                # Add other messages directly
                cached_messages.append(turn)
        return list(reversed(cached_messages))
