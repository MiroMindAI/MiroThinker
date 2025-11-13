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
from abc import ABC
from typing import (
    Any,
    Dict,
    List,
    Optional,
    TypedDict,
)

from omegaconf import DictConfig

from ..logging.task_logger import TaskLog
from .util import with_timeout


class TokenUsage(TypedDict, total=True):
    """
    we unify openai and anthropic format. there are four usage types:
    - input/output tokens
    - cache write/read tokens
    openai:
    - cache write is free. cache read is cheaper.
    anthropic:
    - cache write costs a bit, cache read is cheaper.
    """

    total_input_tokens: int
    total_output_tokens: int
    total_cache_read_input_tokens: int
    total_cache_write_input_tokens: int


@dataclasses.dataclass
class BaseClient(ABC):
    # Required arguments (no default value)
    task_id: str
    cfg: DictConfig

    # Optional arguments (with default value)
    task_log: Optional["TaskLog"] = None

    # post_init
    client: Any = dataclasses.field(init=False)
    token_usage: TokenUsage = dataclasses.field(init=False)

    def __post_init__(self):
        # Explicitly assign from cfg object
        self.provider: str = self.cfg.llm.provider
        self.model_name: str = self.cfg.llm.model_name
        self.temperature: float = self.cfg.llm.temperature
        self.top_p: float = self.cfg.llm.top_p
        self.min_p: float = self.cfg.llm.min_p
        self.top_k: int = self.cfg.llm.top_k
        self.max_context_length: int = self.cfg.llm.max_context_length
        self.max_tokens: int = self.cfg.llm.max_tokens
        self.async_client: bool = self.cfg.llm.async_client
        self.keep_tool_result: int = self.cfg.llm.keep_tool_result
        self.api_key: Optional[str] = self.cfg.llm.get("api_key")
        self.base_url: Optional[str] = self.cfg.llm.get("base_url")
        self.use_tool_calls: Optional[bool] = self.cfg.llm.get("use_tool_calls")
        self.repetition_penalty: float = self.cfg.llm.get("repetition_penalty", 1.0)

        self.token_usage = self._reset_token_usage()
        self.client = self._create_client()

        self.task_log.log_step(
            "info",
            "LLM | Initialization",
            f"LLMClient {self.provider} {self.model_name} initialization completed.",
        )

    def _reset_token_usage(self) -> TokenUsage:
        """Reset token usage counter - implemented by concrete classes"""
        return TokenUsage(
            total_input_tokens=0,
            total_output_tokens=0,
            total_cache_write_input_tokens=0,
            total_cache_read_input_tokens=0,
        )

    def _remove_tool_result_from_messages(
        self, messages, keep_tool_result
    ) -> List[Dict]:
        """Remove tool results from messages

        Args:
            messages: List of message dictionaries
            keep_tool_result: Number of tool results to keep. -1 means keep all.

        Returns:
            List of messages with tool results filtered according to keep_tool_result
        """
        messages_copy = [m.copy() for m in messages]

        if keep_tool_result == -1:
            # No processing needed, keep all messages
            return messages_copy

        # Find indices of all user/tool messages (these are tool results)
        user_indices = [
            i
            for i, msg in enumerate(messages_copy)
            if msg.get("role") == "user" or msg.get("role") == "tool"
        ]

        if len(user_indices) == 0:
            # No user/tool messages found
            self.task_log.log_step(
                "info",
                "LLM | Message Retention",
                "No user/tool messages found in the history.",
            )
            return messages_copy

        # The first user message is the initial task, not a tool result
        # Tool results start from the second user message onwards
        if len(user_indices) == 1:
            # Only one user message (the initial task), no tool results to filter
            self.task_log.log_step(
                "info",
                "LLM | Message Retention",
                "Only 1 user message found (initial task). Keeping it as is.",
            )
            return messages_copy

        # Tool result indices (excluding the first user message which is the initial task)
        tool_result_indices = user_indices[1:]
        first_user_idx = user_indices[
            0
        ]  # Always keep the first user message (initial task)

        # Calculate how many tool results to keep from the end
        if keep_tool_result == 0:
            # Keep 0 tool results, only keep the initial task
            num_tool_results_to_keep = 0
        else:
            # Keep the last keep_tool_result tool results
            num_tool_results_to_keep = min(keep_tool_result, len(tool_result_indices))

        # Get indices of tool results to keep from the end
        tool_result_indices_to_keep = (
            tool_result_indices[-num_tool_results_to_keep:]
            if num_tool_results_to_keep > 0
            else []
        )

        # Combine first message (initial task) and tool results to keep
        indices_to_keep = [first_user_idx] + tool_result_indices_to_keep

        self.task_log.log_step(
            "info",
            "LLM | Message Retention",
            f"Message retention summary: Total user/tool messages: {len(user_indices)}, "
            f"Initial task at index: {first_user_idx}, "
            f"Keeping last {num_tool_results_to_keep} tool results at indices: {tool_result_indices_to_keep}, "
            f"Total messages to keep: {len(indices_to_keep)}",
        )

        # Replace content of tool results that should be omitted
        for i, msg in enumerate(messages_copy):
            if (
                msg.get("role") == "user" or msg.get("role") == "tool"
            ) and i not in indices_to_keep:
                # Preserve the message structure but replace content
                if isinstance(msg.get("content"), list):
                    # For Anthropic format
                    msg["content"] = [
                        {
                            "type": "text",
                            "text": "Tool result is omitted to save tokens.",
                        }
                    ]
                else:
                    # For OpenAI format
                    msg["content"] = "Tool result is omitted to save tokens."

        return messages_copy

    @with_timeout(600)
    async def create_message(
        self,
        system_prompt: str,
        message_history: List[Dict],
        tool_definitions: List[Dict],
        keep_tool_result: int = -1,
        step_id: int = 1,
        task_log: Optional["TaskLog"] = None,
        agent_type: str = "main",
    ):
        """
        Call LLM to generate response, supports tool calls - unified implementation
        """
        # Unified LLM call processing
        try:
            response, message_history = await self._create_message(
                system_prompt,
                message_history,
                tool_definitions,
                keep_tool_result=keep_tool_result,
            )

        except Exception as e:
            self.task_log.log_step(
                "error",
                f"FATAL ERROR | {agent_type} | LLM Call ERROR",
                f"{agent_type} failed: {str(e)}",
            )
            response = None

        return response, message_history

    @staticmethod
    async def convert_tool_definition_to_tool_call(tools_definitions):
        tool_list = []
        for server in tools_definitions:
            if "tools" in server and len(server["tools"]) > 0:
                for tool in server["tools"]:
                    tool_def = dict(
                        type="function",
                        function=dict(
                            name=f"{server['name']}-{tool['name']}",
                            description=tool["description"],
                            parameters=tool["schema"],
                        ),
                    )
                    tool_list.append(tool_def)
        return tool_list

    def close(self):
        """Close client connection"""
        if hasattr(self.client, "close"):
            if asyncio.iscoroutinefunction(self.client.close):
                # For async clients, we cannot call close directly here
                # Need to call in async function
                pass
            else:
                self.client.close()
        elif hasattr(self.client, "_client") and hasattr(self.client._client, "close"):
            # Some clients may have internal _client attribute
            self.client._client.close()
        else:
            # If client has no close method, or is async, we skip
            pass

    def _format_response_for_log(self, response) -> Dict:
        """Format response for logging"""
        if not response:
            return {}

        # Basic response information
        formatted = {
            "response_type": type(response).__name__,
        }

        # Anthropic response
        if hasattr(response, "content"):
            formatted["content"] = []
            for block in response.content:
                if hasattr(block, "type"):
                    if block.type == "text":
                        formatted["content"].append(
                            {
                                "type": "text",
                                "text": block.text[:500] + "..."
                                if len(block.text) > 500
                                else block.text,
                            }
                        )
                    elif block.type == "tool_use":
                        formatted["content"].append(
                            {
                                "type": "tool_use",
                                "id": block.id,
                                "name": block.name,
                                "input": str(block.input)[:200] + "..."
                                if len(str(block.input)) > 200
                                else str(block.input),
                            }
                        )

        # OpenAI response
        if hasattr(response, "choices"):
            formatted["choices"] = []
            for choice in response.choices:
                choice_data = {"finish_reason": choice.finish_reason}
                if hasattr(choice, "message"):
                    message = choice.message
                    choice_data["message"] = {
                        "role": message.role,
                        "content": message.content[:500] + "..."
                        if message.content and len(message.content) > 500
                        else message.content,
                    }
                    if hasattr(message, "tool_calls") and message.tool_calls:
                        choice_data["message"]["tool_calls_count"] = len(
                            message.tool_calls
                        )
                formatted["choices"].append(choice_data)

        return formatted
