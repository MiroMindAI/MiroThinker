# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

"""
Stream handler module for SSE (Server-Sent Events) protocol.

This module provides the StreamHandler class that manages all streaming events
for real-time communication with clients during agent task execution.
"""

import logging
import uuid
from typing import Any, Optional

logger = logging.getLogger(__name__)


class StreamHandler:
    """
    Handler for streaming events in SSE protocol format.

    Manages the sending of various event types including workflow lifecycle,
    agent lifecycle, LLM interactions, and tool calls.
    """

    def __init__(self, stream_queue: Optional[Any] = None):
        """
        Initialize the stream handler.

        Args:
            stream_queue: Optional async queue for sending stream messages.
                         If None, streaming is disabled.
        """
        self.stream_queue = stream_queue

    async def update(self, event_type: str, data: dict):
        """
        Send a streaming update in SSE protocol format.

        Args:
            event_type: The type of event (e.g., 'start_of_workflow', 'tool_call')
            data: The event payload data
        """
        if self.stream_queue:
            try:
                stream_message = {
                    "event": event_type,
                    "data": data,
                }
                await self.stream_queue.put(stream_message)
            except Exception as e:
                logger.warning(f"Failed to send stream update: {e}")

    async def start_workflow(self, user_input: str) -> str:
        """
        Send start_of_workflow event.

        Args:
            user_input: The initial user input for the workflow

        Returns:
            The generated workflow ID
        """
        workflow_id = str(uuid.uuid4())
        await self.update(
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

    async def end_workflow(self, workflow_id: str):
        """
        Send end_of_workflow event.

        Args:
            workflow_id: The workflow ID to end
        """
        await self.update(
            "end_of_workflow",
            {
                "workflow_id": workflow_id,
            },
        )

    async def show_error(self, error: str):
        """
        Send show_error event and signal stream end.

        Args:
            error: The error message to display
        """
        await self.tool_call("show_error", {"error": error})
        if self.stream_queue:
            try:
                await self.stream_queue.put(None)
            except Exception as e:
                logger.warning(f"Failed to send show_error: {e}")

    async def start_agent(self, agent_name: str, display_name: str = None) -> str:
        """
        Send start_of_agent event.

        Args:
            agent_name: Internal name of the agent
            display_name: Optional display name for UI

        Returns:
            The generated agent ID
        """
        agent_id = str(uuid.uuid4())
        await self.update(
            "start_of_agent",
            {
                "agent_name": agent_name,
                "display_name": display_name,
                "agent_id": agent_id,
            },
        )
        return agent_id

    async def end_agent(self, agent_name: str, agent_id: str):
        """
        Send end_of_agent event.

        Args:
            agent_name: Internal name of the agent
            agent_id: The agent ID to end
        """
        await self.update(
            "end_of_agent",
            {
                "agent_name": agent_name,
                "agent_id": agent_id,
            },
        )

    async def start_llm(self, agent_name: str, display_name: str = None):
        """
        Send start_of_llm event.

        Args:
            agent_name: Name of the agent making the LLM call
            display_name: Optional display name for UI
        """
        await self.update(
            "start_of_llm",
            {
                "agent_name": agent_name,
                "display_name": display_name,
            },
        )

    async def end_llm(self, agent_name: str):
        """
        Send end_of_llm event.

        Args:
            agent_name: Name of the agent that finished LLM call
        """
        await self.update(
            "end_of_llm",
            {
                "agent_name": agent_name,
            },
        )

    async def message(self, message_id: str, delta_content: str):
        """
        Send message event with streaming content.

        Args:
            message_id: Unique identifier for the message
            delta_content: The content delta to send
        """
        await self.update(
            "message",
            {
                "message_id": message_id,
                "delta": {
                    "content": delta_content,
                },
            },
        )

    async def tool_call(
        self,
        tool_name: str,
        payload: dict,
        streaming: bool = False,
        tool_call_id: str = None,
    ) -> str:
        """
        Send tool_call event.

        Args:
            tool_name: Name of the tool being called
            payload: Tool call arguments or results
            streaming: If True, send payload keys as deltas
            tool_call_id: Optional existing tool call ID

        Returns:
            The tool call ID (generated if not provided)
        """
        if not tool_call_id:
            tool_call_id = str(uuid.uuid4())

        if streaming:
            for key, value in payload.items():
                await self.update(
                    "tool_call",
                    {
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                        "delta_input": {key: value},
                    },
                )
        else:
            # Send complete tool call
            await self.update(
                "tool_call",
                {
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "tool_input": payload,
                },
            )

        return tool_call_id
