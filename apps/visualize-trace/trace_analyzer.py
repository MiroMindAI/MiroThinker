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

import json
import re
from typing import Any, Dict, List, Optional


class TraceAnalyzer:
    """
    Class for analyzing trace JSON files, convenient for reading and accessing important information

    Supports two tool call formats:
    1. Old format (MCP): Tool calls using XML tag format in content
    2. New format: Tool calls using tool_calls field directly in message
    """

    def __init__(self, json_file_path: str):
        """
        Initialize analyzer

        Args:
            json_file_path: Path to the JSON file
        """
        self.json_file_path = json_file_path
        self.data = self._load_json()

    def _load_json(self) -> Dict[str, Any]:
        """Load JSON file"""
        try:
            with open(self.json_file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            raise Exception(f"Failed to load JSON file: {e}")

    def _parse_new_format_tool_name(self, tool_name: str) -> tuple[str, str]:
        """
        Parse new format tool name

        Args:
            tool_name: New format tool name, for example:
                      - "tool-server_name-tool_name" format
                      - "agent-browsing-search_and_browse" format (browser agent)

        Returns:
            tuple: (server_name, actual_tool_name)
        """
        # Handle agent-browsing-* format (browser agent calls)
        if tool_name.startswith("agent-browsing-"):
            server_name = "agent-browsing"
            actual_tool_name = tool_name[len("agent-browsing-") :]
            return server_name, actual_tool_name

        # Handle other agent-* formats
        elif tool_name.startswith("agent-"):
            # Find the last '-' to split server_name and tool_name
            last_dash = tool_name.rfind("-")
            if last_dash > 6:  # There's content after "agent-"
                server_name = tool_name[:last_dash]
                actual_tool_name = tool_name[last_dash + 1 :]
            else:
                server_name = tool_name
                actual_tool_name = ""
            return server_name, actual_tool_name

        # Handle tool-server_name-tool_name format
        elif tool_name.startswith("tool-"):
            parts = tool_name.split("-", 2)
            if len(parts) >= 3:
                server_name = parts[1]
                actual_tool_name = parts[2]
            else:
                server_name = "unknown"
                actual_tool_name = tool_name
            return server_name, actual_tool_name

        # Other formats
        else:
            server_name = "unknown"
            actual_tool_name = tool_name
            return server_name, actual_tool_name

    # ==================== Basic Information ====================

    def get_basic_info(self) -> Dict[str, Any]:
        """Get basic information of the task"""
        return {
            "status": self.data.get("status"),
            "task_id": self.data.get("task_id"),
            "start_time": self.data.get("start_time"),
            "end_time": self.data.get("end_time"),
            "final_boxed_answer": self.data.get("final_boxed_answer"),
            "ground_truth": self.data.get("ground_truth"),
            "final_judge_result": self.data.get("final_judge_result"),
            "judge_type": self.data.get("judge_type"),
            "error": self.data.get("error", ""),
        }

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary information"""
        trace_data = self.data.get("trace_data", {})
        return trace_data.get("performance_summary", {})

    # ==================== Main Agent Message History ====================

    def get_main_agent_history(self) -> Dict[str, Any]:
        """Get main agent message history"""
        return self.data.get("main_agent_message_history", {})

    def get_main_agent_messages(self) -> List[Dict[str, Any]]:
        """Get main agent message list"""
        history = self.get_main_agent_history()
        return history.get("message_history", [])

    # ==================== Browser Agent Message History ====================

    def get_browser_agent_sessions(self) -> Dict[str, Any]:
        """Get all browser agent sessions"""
        # Try two possible key names
        browser_sessions = self.data.get("browser_agent_message_history_sessions", {})
        if not browser_sessions:
            browser_sessions = self.data.get("sub_agent_message_history_sessions", {})
        return browser_sessions

    def get_browser_agent_session_messages(
        self, session_id: str
    ) -> List[Dict[str, Any]]:
        """Get message list for specified session"""
        sessions = self.get_browser_agent_sessions()
        session = sessions.get(session_id, {})
        return session.get("message_history", [])

    # ==================== MCP Tool Call Parsing ====================

    def parse_mcp_tool_call(self, text: str) -> Optional[Dict[str, Any]]:
        """Parse MCP tool call"""
        pattern = r"<use_mcp_tool>\s*<server_name>(.*?)</server_name>\s*<tool_name>(.*?)</tool_name>\s*<arguments>\s*(.*?)\s*</arguments>\s*</use_mcp_tool>"

        match = re.search(pattern, text, re.DOTALL)
        if match:
            server_name = match.group(1).strip()
            tool_name = match.group(2).strip()
            arguments_str = match.group(3).strip()

            try:
                arguments = json.loads(arguments_str)
            except json.JSONDecodeError:
                arguments = arguments_str

            return {
                "server_name": server_name,
                "tool_name": tool_name,
                "arguments": arguments,
            }

        return None

    def extract_text_content(self, content) -> str:
        """Extract text from message content"""
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
            return "".join(text_parts)
        return str(content)

    def analyze_conversation_flow(self) -> List[Dict[str, Any]]:
        """Analyze conversation flow, including tool calls"""
        flow_steps = []
        main_messages = self.get_main_agent_messages()
        sub_agent_sessions = self.get_browser_agent_sessions()

        sub_agent_call_count = 0

        for i, message in enumerate(main_messages):
            role = message.get("role")
            content = message.get("content", [])

            text_content = self.extract_text_content(content)

            step = {
                "step_id": i,
                "agent": "main_agent",
                "role": role,
                "content_preview": text_content[:200] + "..."
                if len(text_content) > 200
                else text_content,
                "full_content": text_content,
                "tool_calls": [],
                "browser_session": None,
                "timestamp": message.get("timestamp", ""),
                "browser_flow": [],
            }

            # If it's an assistant message, check for tool calls
            if role == "assistant":
                # Check for new format tool_calls
                if "tool_calls" in message and message["tool_calls"]:
                    for tool_call in message["tool_calls"]:
                        # Convert new format to unified format
                        if "function" in tool_call:
                            function_info = tool_call["function"]
                            tool_name = function_info.get("name", "")
                            arguments = function_info.get("arguments", "")

                            # Parse arguments string as JSON (if it's a string)
                            if isinstance(arguments, str):
                                try:
                                    arguments = json.loads(arguments)
                                except json.JSONDecodeError:
                                    pass

                            # Extract server_name from tool_name (if available)
                            server_name, actual_tool_name = (
                                self._parse_new_format_tool_name(tool_name)
                            )

                            parsed_tool_call = {
                                "server_name": server_name,
                                "tool_name": actual_tool_name,
                                "arguments": arguments,
                                "id": tool_call.get("id", ""),
                                "type": tool_call.get("type", "function"),
                                "format": "new",
                            }
                            step["tool_calls"].append(parsed_tool_call)

                            # Handle browser agent calls - maintain complete consistency with MCP format logic
                            if server_name.startswith("agent-"):
                                sub_agent_call_count += 1
                                session_id = f"{server_name}_{sub_agent_call_count}"
                                step["browser_session"] = session_id

                                # Analyze browser session conversation flow
                                if session_id in sub_agent_sessions:
                                    browser_flow = self.analyze_browser_session_flow(
                                        session_id
                                    )
                                    step["browser_flow"] = browser_flow
                            elif server_name.startswith("browsing-agent"):
                                sub_agent_call_count += 1
                                session_id = f"browser_agent_{sub_agent_call_count}"
                                step["browser_session"] = session_id

                                # Analyze browser session conversation flow
                                if session_id in sub_agent_sessions:
                                    browser_flow = self.analyze_browser_session_flow(
                                        session_id
                                    )
                                    step["browser_flow"] = browser_flow

                # Check for old format MCP tool calls (maintain compatibility)
                mcp_tool_call = self.parse_mcp_tool_call(text_content)
                if mcp_tool_call:
                    mcp_tool_call["format"] = "mcp"  # Mark as old format
                    step["tool_calls"].append(mcp_tool_call)

                    # If browsing-agent is called, associate browser session
                    if mcp_tool_call["server_name"].startswith("agent-"):
                        sub_agent_call_count += 1
                        session_id = (
                            f"{mcp_tool_call['server_name']}_{sub_agent_call_count}"
                        )
                        step["browser_session"] = session_id

                        # Analyze browser session conversation flow
                        if session_id in sub_agent_sessions:
                            browser_flow = self.analyze_browser_session_flow(session_id)
                            step["browser_flow"] = browser_flow
                    elif mcp_tool_call["server_name"].startswith("browsing-agent"):
                        sub_agent_call_count += 1
                        session_id = f"browser_agent_{sub_agent_call_count}"
                        step["browser_session"] = session_id

                        # Analyze browser session conversation flow
                        if session_id in sub_agent_sessions:
                            browser_flow = self.analyze_browser_session_flow(session_id)
                            step["browser_flow"] = browser_flow
            flow_steps.append(step)

        return flow_steps

    def analyze_browser_session_flow(self, session_id: str) -> List[Dict[str, Any]]:
        """Analyze browser session conversation flow"""
        browser_messages = self.get_browser_agent_session_messages(session_id)
        browser_flow = []

        for i, message in enumerate(browser_messages):
            role = message.get("role")
            content = message.get("content", [])

            text_content = self.extract_text_content(content)

            step = {
                "step_id": i,
                "agent": session_id,
                "role": role,
                "content_preview": text_content[:200] + "..."
                if len(text_content) > 200
                else text_content,
                "full_content": text_content,
                "tool_calls": [],
                "timestamp": message.get("timestamp", ""),
            }

            # If it's an assistant message, check for tool calls
            if role == "assistant":
                # Check for new format tool_calls
                if "tool_calls" in message and message["tool_calls"]:
                    for tool_call in message["tool_calls"]:
                        # Convert new format to unified format
                        if "function" in tool_call:
                            function_info = tool_call["function"]
                            tool_name = function_info.get("name", "")
                            arguments = function_info.get("arguments", "")

                            # Parse arguments string as JSON (if it's a string)
                            if isinstance(arguments, str):
                                try:
                                    arguments = json.loads(arguments)
                                except json.JSONDecodeError:
                                    pass

                            # Extract server_name from tool_name (if available)
                            server_name, actual_tool_name = (
                                self._parse_new_format_tool_name(tool_name)
                            )

                            parsed_tool_call = {
                                "server_name": server_name,
                                "tool_name": actual_tool_name,
                                "arguments": arguments,
                                "id": tool_call.get("id", ""),
                                "type": tool_call.get("type", "function"),
                                "format": "new",
                            }
                            step["tool_calls"].append(parsed_tool_call)

                # Check for old format MCP tool calls (maintain compatibility)
                mcp_tool_call = self.parse_mcp_tool_call(text_content)
                if mcp_tool_call:
                    mcp_tool_call["format"] = "mcp"  # Mark as old format
                    step["tool_calls"].append(mcp_tool_call)

            browser_flow.append(step)

        return browser_flow

    def get_execution_summary(self) -> Dict[str, Any]:
        """Get execution summary information"""
        flow_steps = self.analyze_conversation_flow()

        total_steps = len(flow_steps)
        tool_calls = []
        browser_sessions = []

        for step in flow_steps:
            if step["tool_calls"]:
                tool_calls.extend(step["tool_calls"])
            if step.get("browser_session"):
                browser_sessions.append(step["browser_session"])

            # Collect tool calls from browser sessions
            if step.get("browser_flow"):
                for browser_step in step["browser_flow"]:
                    if browser_step.get("tool_calls"):
                        tool_calls.extend(browser_step["tool_calls"])

        # Tool usage statistics
        tool_usage = {}
        for tool in tool_calls:
            # Choose appropriate key name generation method based on format
            if tool.get("format") == "new":
                # New format: use server_name.tool_name, if server_name is unknown then use only tool_name
                if tool.get("server_name") != "unknown":
                    key = f"{tool['server_name']}.{tool['tool_name']}"
                else:
                    key = tool["tool_name"]
            else:
                # Old format (MCP): maintain original method
                key = f"{tool['server_name']}.{tool['tool_name']}"
            tool_usage[key] = tool_usage.get(key, 0) + 1

        return {
            "total_steps": total_steps,
            "total_tool_calls": len(tool_calls),
            "browser_sessions_count": len(browser_sessions),
            "tool_usage_distribution": tool_usage,
            "browser_sessions": browser_sessions,
        }

    def get_spans_summary(self) -> Dict[str, Any]:
        """Get spans statistical summary"""
        trace_data = self.data.get("trace_data", {})
        spans = trace_data.get("spans", [])

        agent_stats = {}
        for span in spans:
            agent = span.get("agent_context", "unknown")
            if agent not in agent_stats:
                agent_stats[agent] = {
                    "count": 0,
                    "total_duration": 0,
                    "span_types": set(),
                }
            agent_stats[agent]["count"] += 1
            agent_stats[agent]["total_duration"] += span.get("duration_seconds", 0)
            agent_stats[agent]["span_types"].add(span.get("name", "unknown"))

        # Convert set to list
        for agent in agent_stats:
            agent_stats[agent]["span_types"] = list(agent_stats[agent]["span_types"])

        return {
            "total_spans": len(spans),
            "total_duration": sum(span.get("duration_seconds", 0) for span in spans),
            "agent_stats": agent_stats,
        }

    def get_step_logs_summary(self) -> Dict[str, Any]:
        """Get step logs summary statistics"""
        logs = self.data.get("step_logs", [])

        status_count = {}
        step_type_count = {}

        for log in logs:
            status = log.get("status", "unknown")
            step_name = log.get("step_name", "unknown")

            status_count[status] = status_count.get(status, 0) + 1
            step_type_count[step_name] = step_type_count.get(step_name, 0) + 1

        return {
            "total_logs": len(logs),
            "status_distribution": status_count,
            "step_type_distribution": step_type_count,
        }
