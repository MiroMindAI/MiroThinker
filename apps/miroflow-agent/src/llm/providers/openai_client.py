# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

import asyncio
import dataclasses
import logging
from typing import Any, Dict, List, Tuple, Union

import tiktoken
from openai import AsyncOpenAI, DefaultAsyncHttpxClient, DefaultHttpxClient, OpenAI
from tenacity import retry, stop_after_attempt, wait_fixed

from ...utils.prompt_utils import generate_mcp_system_prompt
from ..base_client import BaseClient

logger = logging.getLogger("miroflow_agent")


@dataclasses.dataclass
class OpenAIClient(BaseClient):
    def _create_client(self) -> Union[AsyncOpenAI, OpenAI]:
        """Create LLM client"""
        http_client_args = {"headers": {"x-upstream-session-id": self.task_id}}
        if self.async_client:
            return AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                http_client=DefaultAsyncHttpxClient(**http_client_args),
            )
        else:
            return OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                http_client=DefaultHttpxClient(**http_client_args),
            )

    def _update_token_usage(self, usage_data: Any) -> None:
        """Update cumulative token usage"""
        if usage_data:
            input_tokens = getattr(usage_data, "prompt_tokens", 0)
            output_tokens = getattr(usage_data, "completion_tokens", 0)
            prompt_tokens_details = getattr(usage_data, "prompt_tokens_details", None)
            if prompt_tokens_details:
                cached_tokens = (
                    getattr(prompt_tokens_details, "cached_tokens", None) or 0
                )
            else:
                cached_tokens = 0

            # Record token usage for the most recent call
            self.last_call_tokens = {
                "prompt_tokens": input_tokens,
                "completion_tokens": output_tokens,
            }

            # OpenAI does not provide cache_creation_input_tokens
            self.token_usage["total_input_tokens"] += input_tokens
            self.token_usage["total_output_tokens"] += output_tokens
            self.token_usage["total_cache_read_input_tokens"] += cached_tokens

            self.task_log.log_step(
                "info",
                "LLM | Token Usage",
                f"Input: {self.token_usage['total_input_tokens']}, "
                f"Output: {self.token_usage['total_output_tokens']}",
            )

    @retry(wait=wait_fixed(30), stop=stop_after_attempt(10))
    async def _create_message(
        self,
        system_prompt: str,
        messages_history: List[Dict[str, Any]],
        tools_definitions,
        keep_tool_result: int = -1,
    ):
        """
        Send message to OpenAI API.
        :param system_prompt: System prompt string.
        :param messages_history: Message history list.
        :return: OpenAI API response object or None (if error occurs).
        """

        # Create a copy for sending to LLM (to avoid modifying the original)
        messages_for_llm = [m.copy() for m in messages_history]

        # put the system prompt in the first message since OpenAI API does not support system prompt in
        if system_prompt:
            # Check if there's already a system or developer message
            if messages_for_llm and messages_for_llm[0]["role"] in [
                "system",
                "developer",
            ]:
                messages_for_llm[0] = {
                    "role": "system",
                    "content": system_prompt,
                }

            else:
                messages_for_llm.insert(
                    0,
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                )

        # Filter tool results to save tokens (only affects messages sent to LLM)
        messages_for_llm = self._remove_tool_result_from_messages(
            messages_for_llm, keep_tool_result
        )

        params = {
            "model": self.model_name,
            "temperature": self.temperature,
            "messages": messages_for_llm,
            "tools": [],
            "stream": False,
            "top_p": self.top_p,
            "extra_body": {},
        }
        # Check if the model is GPT-5, and adjust the parameter accordingly
        if "gpt-5" in self.model_name:
            # Use 'max_completion_tokens' for GPT-5
            params["max_completion_tokens"] = self.max_tokens
        else:
            # Use 'max_tokens' for GPT-4 and other models
            params["max_tokens"] = self.max_tokens

        # Add repetition_penalty if it's not the default value
        if self.repetition_penalty != 1.0:
            params["extra_body"]["repetition_penalty"] = self.repetition_penalty

        if "deepseek-v3-1" in self.model_name:
            params["extra_body"]["thinking"] = {"type": "enabled"}

        try:
            if self.async_client:
                response = await self.client.chat.completions.create(**params)
            else:
                response = self.client.chat.completions.create(**params)
            # Update token count
            self._update_token_usage(getattr(response, "usage", None))
            self.task_log.log_step(
                "info",
                "LLM | Response Status",
                f"{getattr(response.choices[0], 'finish_reason', 'N/A')}",
            )

            # Check if response was truncated due to length limit
            finish_reason = getattr(response.choices[0], "finish_reason", None)
            if finish_reason == "length":
                self.task_log.log_step(
                    "warning",
                    "LLM | Length Limit Reached",
                    "Response was truncated due to length limit, retrying...",
                )
                raise Exception("Response truncated due to length limit, please retry.")

            # Check if the last 100 characters of the response appear more than 5 times in the response content.
            # If so, treat it as a severe repeat and trigger a retry.
            if hasattr(response.choices[0], "message") and hasattr(
                response.choices[0].message, "content"
            ):
                resp_content = response.choices[0].message.content or ""
            else:
                resp_content = getattr(response.choices[0], "text", "")

            if resp_content and len(resp_content) >= 50:
                tail_50 = resp_content[-50:]
                repeat_count = resp_content.count(tail_50)
                if repeat_count > 5:
                    self.task_log.log_step(
                        "warning",
                        "LLM | Repeat Detected",
                        "Severe repeat: the last 50 chars appeared over 5 times, retrying...",
                    )
                    raise Exception("Severe repeat detected in response, please retry.")

            # Return the original messages_history (not the filtered copy)
            # This ensures that the complete conversation history is preserved in logs
            return response, messages_history

        except asyncio.TimeoutError as e:
            self.task_log.log_step(
                "error",
                "LLM | Timeout Error",
                f"Timeout error: {str(e)}",
            )
            raise e
        except asyncio.CancelledError as e:
            self.task_log.log_step(
                "error",
                "LLM | Request Cancelled",
                f"Request was cancelled: {str(e)}",
            )
            raise e
        except Exception as e:
            if "Error code: 400" in str(e) and "longer than the model" in str(e):
                self.task_log.log_step(
                    "error",
                    "LLM | Context Length Error",
                    f"Error: {str(e)}",
                )
                raise e
            else:
                self.task_log.log_step(
                    "error",
                    "LLM | API Error",
                    f"Error: {str(e)}",
                )
                raise e

    def process_llm_response(
        self, llm_response: Any, message_history: List[Dict], agent_type: str = "main"
    ) -> tuple[str, bool, List[Dict]]:
        """Process LLM response"""
        if not llm_response or not llm_response.choices:
            error_msg = "LLM did not return a valid response."
            self.task_log.log_step(
                "error", "LLM | Response Error", f"Error: {error_msg}"
            )
            return "", True, message_history  # Exit loop, return message_history

        # Extract LLM response text
        if llm_response.choices[0].finish_reason == "stop":
            assistant_response_text = llm_response.choices[0].message.content or ""

            message_history.append(
                {"role": "assistant", "content": assistant_response_text}
            )

        elif llm_response.choices[0].finish_reason == "length":
            assistant_response_text = llm_response.choices[0].message.content or ""
            if assistant_response_text == "":
                assistant_response_text = "LLM response is empty."
            elif "Context length exceeded" in assistant_response_text:
                # This is the case where context length is exceeded, needs special handling
                self.task_log.log_step(
                    "warning",
                    "LLM | Context Length",
                    "Detected context length exceeded, returning error status",
                )
                message_history.append(
                    {"role": "assistant", "content": assistant_response_text}
                )
                return (
                    assistant_response_text,
                    True,
                    message_history,
                )  # Return True to indicate need to exit loop

            # Add assistant response to history
            message_history.append(
                {"role": "assistant", "content": assistant_response_text}
            )

        else:
            raise ValueError(
                f"Unsupported finish reason: {llm_response.choices[0].finish_reason}"
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
                "content": merged_text,
            }
        )

        return message_history

    def generate_agent_system_prompt(self, date: Any, mcp_servers: List[Dict]) -> str:
        return generate_mcp_system_prompt(date, mcp_servers)

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
        last_prompt_tokens = self.last_call_tokens.get("prompt_tokens", 0)
        last_completion_tokens = self.last_call_tokens.get("completion_tokens", 0)
        buffer_factor = 2

        # Calculate token count for summary prompt
        summary_tokens = self._estimate_tokens(summary_prompt) * buffer_factor

        # Calculate token count for the last user message in message_history (if exists and not sent)
        last_user_tokens = 0
        if message_history[-1]["role"] == "user":
            content = message_history[-1]["content"]
            last_user_tokens = self._estimate_tokens(content) * buffer_factor

        # Calculate total token count: last prompt + completion + last user message + summary + reserved response space
        estimated_total = (
            last_prompt_tokens
            + last_completion_tokens
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

    def handle_max_turns_reached_summary_prompt(
        self, message_history: List[Dict], summary_prompt: str
    ) -> str:
        """Handle max turns reached summary prompt"""
        if message_history[-1]["role"] == "user":
            message_history.pop()  # Remove the last user message
            # TODO: this part is a temporary fix, we need to find a better way to handle this
            return summary_prompt
        else:
            return summary_prompt

    def format_token_usage_summary(self) -> tuple[List[str], str]:
        """Format token usage statistics, return summary_lines for format_final_summary and log string"""
        token_usage = self.get_token_usage()

        total_input = token_usage.get("total_input_tokens", 0)
        total_output = token_usage.get("total_output_tokens", 0)
        cache_input = token_usage.get("total_cache_input_tokens", 0)

        summary_lines = []
        summary_lines.append("\n" + "-" * 20 + " Token Usage " + "-" * 20)
        summary_lines.append(f"Total Input Tokens: {total_input}")
        summary_lines.append(f"Total Cache Input Tokens: {cache_input}")
        summary_lines.append(f"Total Output Tokens: {total_output}")
        summary_lines.append("-" * (40 + len(" Token Usage ")))
        summary_lines.append("Pricing is disabled - no cost information available")
        summary_lines.append("-" * (40 + len(" Token Usage ")))

        # Generate log string
        log_string = (
            f"[{self.model_name}] Total Input: {total_input}, "
            f"Cache Input: {cache_input}, "
            f"Output: {total_output}"
        )

        return summary_lines, log_string

    def get_token_usage(self):
        return self.token_usage.copy()
