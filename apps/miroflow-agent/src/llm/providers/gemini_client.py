# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

"""
Gemini LLM client implementation.

This module provides the GeminiClient class for interacting with Google's Gemini API
via the google-genai SDK.

Features:
- Support for Gemini 1.5 Pro/Flash
- Native Multimodal support
- Google Search Grounding integration
- Tool calling support (translating between Agent format and Gemini format)
"""

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional, Union

from google import genai
from google.genai import types

from ..base_client import BaseClient
from ...utils.parsing_utils import extract_llm_response_text, parse_llm_response_for_tool_calls

logger = logging.getLogger("miroflow_agent")


class GeminiClient(BaseClient):
    """
    Client for Google's Gemini models using google-genai SDK.
    """

    def _create_client(self) -> genai.Client:
        """Create Gemini client"""
        # Authentication is handled automatically by the SDK via
        # GOOGLE_APPLICATION_CREDENTIALS environment variable or default credentials.
        # We can also explicitly pass api_key if available in config, but user
        # requested GCP project credits (Vertex AI/ADC) which usually relies on creds file.

        # If api_key is provided in config, use it (likely AI Studio).
        # Otherwise, rely on ADC (Vertex AI).
        kwargs = {}
        if self.api_key:
            kwargs["api_key"] = self.api_key

        # Initialize client
        # The google-genai SDK unifies Vertex AI and AI Studio.
        # If using Vertex AI, location/project might be needed if not in env.
        # We assume GOOGLE_APPLICATION_CREDENTIALS is set as per user request.

        if self.cfg.llm.get("vertex_ai_location"):
             kwargs["location"] = self.cfg.llm.get("vertex_ai_location")

        if self.cfg.llm.get("project_id"):
             kwargs["project"] = self.cfg.llm.get("project_id")

        return genai.Client(**kwargs)

    def _update_token_usage(self, usage_metadata: Any) -> None:
        """Update cumulative token usage from Gemini response"""
        if not usage_metadata:
            return

        input_tokens = getattr(usage_metadata, "prompt_token_count", 0)
        output_tokens = getattr(usage_metadata, "candidates_token_count", 0)

        # Gemini doesn't always break down cache tokens in the same way,
        # but check if available in future versions or specific response fields.
        # For now, map basic counts.

        self.last_call_tokens = {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
        }

        self.token_usage["total_input_tokens"] += input_tokens
        self.token_usage["total_output_tokens"] += output_tokens

        # Log usage
        self.task_log.log_step(
            "info",
            "LLM | Token Usage",
            f"Input: {self.token_usage['total_input_tokens']}, "
            f"Output: {self.token_usage['total_output_tokens']}",
        )

    def _convert_messages_to_gemini_format(self, messages: List[Dict]) -> List[types.Content]:
        """
        Convert internal message format to Gemini's Content format.
        """
        gemini_messages = []

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")

            # Map roles
            if role == "system":
                # System instructions are passed separately in Gemini config,
                # but if they appear in history, we might treat them as user or model depending on context.
                # However, usually system prompt is handled in _create_message logic.
                # If we see system messages in history, we'll treat them as 'user' instructions
                # effectively, or ignore if they are duplicates of the main system prompt.
                # For simplicity, let's map to user, but typically system prompt is separate.
                pass
            elif role == "user":
                parts = []
                if isinstance(content, str):
                    parts.append(types.Part.from_text(text=content))
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict):
                            if item.get("type") == "text":
                                parts.append(types.Part.from_text(text=item.get("text")))
                            elif item.get("type") == "image_url":
                                # Handle image URLs or base64
                                # This client might receive base64 in data URLs
                                # We need to handle this if the agent passes previous image history.
                                # For now, assume text history mostly.
                                parts.append(types.Part.from_text(text="[Image Content]"))

                if parts:
                    gemini_messages.append(types.Content(role="user", parts=parts))

            elif role == "assistant":
                parts = []
                if content:
                    parts.append(types.Part.from_text(text=str(content)))

                # Check for tool calls in the message (if stored in a specific way)
                # The agent framework stores tool calls often in the text content (XML/JSON)
                # or separate fields. We rely on text content here.
                if parts:
                    gemini_messages.append(types.Content(role="model", parts=parts))

            # Note: The agent framework seems to store tool results as 'user' messages
            # or uses a specific flow. We map standard roles.

        return gemini_messages

    async def _create_message(
        self,
        system_prompt: str,
        messages_history: List[Dict[str, Any]],
        tools_definitions: List[Dict],
        keep_tool_result: int = -1,
    ):
        """
        Send message to Gemini API.
        """
        # Filter tool results
        messages_for_llm = self._remove_tool_result_from_messages(
            messages_history, keep_tool_result
        )

        # Config setup
        config = types.GenerateContentConfig(
            temperature=self.temperature,
            top_p=self.top_p,
            top_k=self.top_k,
            max_output_tokens=self.max_tokens,
            candidate_count=1,
        )

        # Handle System Prompt
        if system_prompt:
            config.system_instruction = system_prompt

        # Handle Tools and Grounding
        gemini_tools = []
        enable_grounding = False

        # Check for Google Search tool
        filtered_tool_definitions = []
        if tools_definitions:
            for tool_def in tools_definitions:
                # If tool-google-search is requested, enable Grounding instead
                if "tool-google-search" in tool_def.get("name", "") or \
                   any(t.get("name") == "google_search" for t in tool_def.get("tools", [])):
                    enable_grounding = True
                    logger.info("Enabling Gemini Google Search Grounding")
                    # We do NOT add this tool to gemini_tools, effectively "hiding" it
                    # so the model uses the built-in grounding instead.
                else:
                    filtered_tool_definitions.append(tool_def)

        if enable_grounding:
            gemini_tools.append(types.Tool(google_search=types.GoogleSearch()))

        # Convert other tools to Gemini format
        # Gemini expects: Tool(function_declarations=[...])
        function_declarations = []
        if filtered_tool_definitions:
            # Convert MCP/Agent tool defs to Gemini FunctionDeclarations
            # Agent format: list of servers, each has 'tools' list
            for server in filtered_tool_definitions:
                for tool in server.get("tools", []):
                    # Construct function declaration
                    # Name must be unique, usually "server-tool"
                    unique_name = f"{server['name']}-{tool['name']}"

                    func_decl = types.FunctionDeclaration(
                        name=unique_name,
                        description=tool.get("description", ""),
                        parameters=tool.get("schema", {})
                    )
                    function_declarations.append(func_decl)

        if function_declarations:
            gemini_tools.append(types.Tool(function_declarations=function_declarations))

        if gemini_tools:
            config.tools = gemini_tools

        # Convert history
        contents = self._convert_messages_to_gemini_format(messages_for_llm)

        # Retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Call Gemini
                # We use the async client methods if available,
                # but google-genai 1.0+ unifies this.
                # The generate_content_async method is standard.

                response = await self.client.aio.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=config
                )

                # Token usage
                self._update_token_usage(response.usage_metadata)

                # Process response
                # Gemini response might contain:
                # 1. Text
                # 2. Function Calls (parts)
                # 3. Grounding Metadata

                # We need to convert this back to the format the Agent expects.
                # The Agent expects a 'response' object that mimics OpenAI or
                # has 'choices'/'content'.

                # However, BaseClient._create_message contract returns (response_obj, history).
                # The caller expects something it can process in `process_llm_response`.
                # We should return a normalized response object or rely on Duck Typing.
                # But BaseClient implementation of `process_llm_response` (in OpenAIClient)
                # is specific to OpenAI format.

                # Wait, `BaseClient` does NOT implement `process_llm_response`.
                # `OpenAIClient` and `AnthropicClient` do.
                # So I must implement `process_llm_response` in this class too.

                return response, messages_history

            except Exception as e:
                logger.error(f"Gemini API Error (Attempt {attempt+1}): {e}")
                if attempt == max_retries - 1:
                    raise e
                await asyncio.sleep(2 * (attempt + 1))

    def process_llm_response(
        self, llm_response: Any, message_history: List[Dict], agent_type: str = "main"
    ) -> tuple[str, bool, List[Dict]]:
        """
        Process Gemini response and update history.
        """
        if not llm_response or not llm_response.candidates:
            self.task_log.log_step("error", "LLM | Response Error", "Empty response from Gemini")
            return "", True, message_history

        candidate = llm_response.candidates[0]
        content_parts = candidate.content.parts

        full_text = ""
        tool_calls = []

        for part in content_parts:
            if part.text:
                full_text += part.text
            elif part.function_call:
                # Convert Gemini function call to the internal format if needed
                # But typically the Agent expects the LLM to output specific patterns (XML/JSON)
                # OR we construct the tool call message.

                # The framework seems to support parsing from text (OpenAI/XML).
                # It also supports OpenAI object structure.

                # If Gemini returns a structured function call, we should format it
                # so `extract_tool_calls_info` can find it, OR handle it here.

                # Let's reconstruct the tool call into the text so parsing utils can find it,
                # OR format it as an OpenAI-like tool call if we want to reuse that logic.

                # The `parse_llm_response_for_tool_calls` function handles:
                # 1. Dict with 'output' (OpenAI Response API)
                # 2. List of tool_call objects (OpenAI Completion API)
                # 3. Text with <use_mcp_tool> (XML)

                # We can't easily inject into "text" and expect the parser to work
                # if the parser expects XML but we have objects.

                # EASIEST PATH: Since we are implementing `extract_tool_calls_info` (see below),
                # we can store the native function calls in a temporary way
                # or rely on `full_text` if Gemini puts it there (it doesn't).

                # We will append a special marker to full_text or handle it in `extract_tool_calls_info`.

                # Let's convert the function call to the XML format the agent likes,
                # so the text log looks consistent and downstream parsers work.

                args_json = part.function_call.args
                # json.dumps might be needed if args is a dict
                import json
                args_str = json.dumps(args_json) if isinstance(args_json, (dict, list)) else str(args_json)

                # Note: The agent splits server-tool by hyphen.
                # Gemini name is "server-tool".
                if "-" in part.function_call.name:
                    server, tool = part.function_call.name.rsplit("-", 1)
                else:
                    server = "unknown"
                    tool = part.function_call.name

                full_text += f"\n<use_mcp_tool>\n<server_name>{server}</server_name>\n<tool_name>{tool}</tool_name>\n<arguments>\n{args_str}\n</arguments>\n</use_mcp_tool>\n"

        # Handle Grounding Metadata (Search Results)
        # If grounding was used, Gemini appends citations/search info.
        # We should append this to the text so the user sees it.
        if candidate.grounding_metadata and candidate.grounding_metadata.search_entry_point:
             full_text += f"\n\n[Grounding] {candidate.grounding_metadata.search_entry_point.rendered_content}\n"

        # Add assistant response to history
        message_history.append({"role": "assistant", "content": full_text})

        return full_text, False, message_history

    def extract_tool_calls_info(
        self, llm_response: Any, assistant_response_text: str
    ) -> List[Dict]:
        """
        Extract tool calls.
        Since we reconstructed the XML in process_llm_response, we can reuse the util.
        """
        from ...utils.parsing_utils import parse_llm_response_for_tool_calls
        return parse_llm_response_for_tool_calls(assistant_response_text)

    def update_message_history(
        self, message_history: List[Dict], all_tool_results_content_with_id: List[Tuple]
    ) -> List[Dict]:
        """
        Update message history with tool results.
        Gemini expects function responses to be sent back.
        However, since we are converting everything to a unified history format (list of dicts),
        we can stick to the format the Agent uses (User message with tool results).

        In `_create_message`, we convert this back to what Gemini expects.
        """
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
        from ...utils.prompt_utils import generate_mcp_system_prompt
        return generate_mcp_system_prompt(date, mcp_servers)
