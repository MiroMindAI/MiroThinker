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

import asyncio
import dataclasses
import logging
import os

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
from ..provider_client_base import LLMProviderClientBase

logger = logging.getLogger("miroflow_agent")


@dataclasses.dataclass
class AnthropicLLMClient(LLMProviderClientBase):
    def __post_init__(self):
        super().__post_init__()

        # Anthropic-specific token counters
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.cache_creation_tokens: int = 0
        self.cache_read_tokens: int = 0

    def _create_client(self):
        """Create Anthropic client"""
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        http_client_args = {}

        if self.async_client:
            return AsyncAnthropic(
                api_key=api_key,
                base_url=self.anthropic_base_url,
                http_client=DefaultAsyncHttpxClient(**http_client_args),
            )
        else:
            return Anthropic(
                api_key=api_key,
                base_url=self.anthropic_base_url,
                http_client=DefaultHttpxClient(**http_client_args),
            )

    def _update_token_usage(self, usage_data):
        """Update cumulative token usage - Anthropic implementation"""
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
                + getattr(usage_data, "cache_creation_input_tokens")
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
        system_prompt,
        messages,
        tools_definitions,
        keep_tool_result: int = -1,
    ):
        """
        Send message to Anthropic API.
        :param system_prompt: System prompt string.
        :param messages: Message history list.
        :return: Anthropic API response object or None (if error).
        """
        self.task_log.log_step(
            "info",
            "LLM | Call Start",
            f"Calling LLM ({'async' if self.async_client else 'sync'})",
        )

        messages_copy = self._remove_tool_result_from_messages(
            messages, keep_tool_result
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
                    system=[
                        {
                            "type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],  # System prompt also uses ephemeral
                    messages=processed_messages,
                    stream=False,  # Current implementation based on non-streaming
                )
            else:
                response = self.client.messages.create(
                    model=self.model_name,
                    temperature=self.temperature,
                    top_p=self.top_p if self.top_p != 1.0 else NOT_GIVEN,
                    top_k=self.top_k if self.top_k != -1 else NOT_GIVEN,
                    max_tokens=self.max_tokens,
                    system=[
                        {
                            "type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],  # System prompt also uses ephemeral
                    messages=processed_messages,
                    stream=False,  # Current implementation based on non-streaming
                )
            # Update token count

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
        self, llm_response, message_history, agent_type="main"
    ) -> tuple[str, bool, list]:
        """Process Anthropic LLM response"""
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
                # Include tool calls
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

    def extract_tool_calls_info(self, llm_response, assistant_response_text) -> list:
        """Extract tool call information from Anthropic LLM response"""
        from ...utils.parsing_utils import parse_llm_response_for_tool_calls

        # For Anthropic, parse tool calls from response text
        return parse_llm_response_for_tool_calls(assistant_response_text)

    def update_message_history(self, message_history, all_tool_results_content_with_id):
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

    def generate_agent_system_prompt(self, date, mcp_servers) -> str:
        return generate_mcp_system_prompt(date, mcp_servers)

    def handle_max_turns_reached_summary_prompt(self, message_history, summary_prompt):
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
        """This is just an estimate for anthropic"""

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
                f"Error: {str(e)} text: {text} type: {type(text)}",
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
        last_output_tokens = self.last_call_tokens.get("ouput_tokens", 0)
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

    def format_token_usage_summary(self):
        """Format token usage statistics, return summary_lines for format_final_summary and log string - Anthropic implementation"""
        token_usage = self.get_token_usage()

        total_input = token_usage.get("total_input_tokens", 0)
        total_output = token_usage.get("total_output_tokens", 0)
        total_cache_creation = token_usage.get("total_cache_creation_input_tokens", 0)
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
        log_string = f"[Anthropic/{self.model_name}] Total Input: {total_input}, Cache Creation: {total_cache_creation}, Cache Read: {total_cache_read}, Output: {total_output}"

        return summary_lines, log_string

    def get_token_usage(self):
        """Get current cumulative token usage - Anthropic implementation"""
        return self.token_usage.copy()

    def _apply_cache_control(self, messages):
        """Apply cache control to the last user message and system message (if applicable)"""
        cached_messages = []
        user_turns_processed = 0
        for turn in reversed(messages):
            if turn["role"] == "user" and user_turns_processed < 1:
                # Add ephemeral cache control to text part of the last user message
                new_content = []
                processed_text = False
                # Check if content is a list
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
                            # Other content types (like image) copy directly
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
                # Other messages add directly
                cached_messages.append(turn)
        return list(reversed(cached_messages))
