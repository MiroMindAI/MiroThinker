# Copyright (c) 2025 MiroMind
# This source code is licensed under the Apache 2.0 License.

import asyncio
import functools
from contextlib import AsyncExitStack
from typing import Any, Awaitable, Callable, Protocol, TypeVar

from mcp import ClientSession, StdioServerParameters  # (already imported in config.py)
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client

from .mcp_servers.browser_session import PlaywrightSession

# logger = logging.getLogger("miroflow_agent")

R = TypeVar("R")


def with_timeout(timeout_s: float = 300.0):
    """
    Decorator: wraps any *async* function in asyncio.wait_for().
    Usage:
        @with_timeout(20)
        async def create_message_foo(...): ...
    """

    def decorator(
        func: Callable[..., Awaitable[R]],
    ) -> Callable[..., Awaitable[R]]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> R:
            return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_s)

        return wrapper

    return decorator


class ToolManagerProtocol(Protocol):
    """this enables other kinds of tool manager."""

    async def get_all_tool_definitions(self) -> Any: ...
    async def execute_tool_call(
        self, *, server_name: str, tool_name: str, arguments: dict[str, Any]
    ) -> Any: ...


class ToolManager(ToolManagerProtocol):
    def __init__(self, server_configs, tool_blacklist=None):
        """
        Initialize ToolManager.
        :param server_configs: List returned by create_server_parameters()
        """
        self.server_configs = server_configs
        self.server_dict = {
            config["name"]: config["params"] for config in server_configs
        }
        self.browser_session = None
        self.tool_blacklist = tool_blacklist if tool_blacklist else set()
        self.task_log = None
        self._session_stacks: dict[str, AsyncExitStack] = {}
        self._sessions: dict[str, ClientSession] = {}
        self._session_locks: dict[str, asyncio.Lock] = {}

    def set_task_log(self, task_log):
        """Set the task logger for structured logging."""
        self.task_log = task_log

        self._log(
            "info",
            "ToolManager | Initialization",
            f"ToolManager initialized, loaded servers: {list(self.server_dict.keys())}",
        )

    def _log(self, level, step_name, message, metadata=None):
        """Helper method to log using task_log if available, otherwise skip logging."""
        if self.task_log:
            self.task_log.log_step(level, step_name, message, metadata)

    def _is_huggingface_dataset_or_space_url(self, url):
        """
        Check if the URL is a Hugging Face dataset or space URL.
        :param url: The URL to check
        :return: True if it's a HuggingFace dataset or space URL, False otherwise
        """
        if not url:
            return False
        return "huggingface.co/datasets" in url or "huggingface.co/spaces" in url

    def _should_block_hf_scraping(self, tool_name, arguments):
        """
        Check if we should block scraping of Hugging Face datasets/spaces.
        :param tool_name: The name of the tool being called
        :param arguments: The arguments passed to the tool
        :return: True if scraping should be blocked, False otherwise
        """
        return (
            tool_name in ["scrape", "scrape_website"]
            and arguments.get("url")
            and self._is_huggingface_dataset_or_space_url(arguments["url"])
        )

    def get_server_params(self, server_name):
        """Get parameters for the specified server"""
        return self.server_dict.get(server_name)

    async def _get_or_create_session(
        self, server_name: str, server_params
    ) -> ClientSession:
        """Get or create a persistent MCP session for a server.

        Sessions are kept alive for the lifetime of the ToolManager, eliminating
        per-call subprocess spawning overhead. Call ``close()`` when the task ends.
        """
        if server_name not in self._session_locks:
            self._session_locks[server_name] = asyncio.Lock()

        async with self._session_locks[server_name]:
            if server_name in self._sessions:
                return self._sessions[server_name]

            stack = AsyncExitStack()
            try:
                if isinstance(server_params, StdioServerParameters):
                    read, write = await stack.enter_async_context(
                        stdio_client(server_params)
                    )
                elif isinstance(server_params, str) and server_params.startswith(
                    ("http://", "https://")
                ):
                    read, write = await stack.enter_async_context(
                        sse_client(server_params)
                    )
                else:
                    await stack.aclose()
                    raise TypeError(
                        f"Unknown server params type for {server_name}: {type(server_params)}"
                    )

                session = await stack.enter_async_context(
                    ClientSession(read, write, sampling_callback=None)
                )
                await session.initialize()
                self._session_stacks[server_name] = stack
                self._sessions[server_name] = session
                return session
            except Exception:
                await stack.aclose()
                raise

    async def close(self) -> None:
        """Close all persistent MCP server sessions."""
        for server_name, stack in list(self._session_stacks.items()):
            try:
                await stack.aclose()
            except Exception as e:
                self._log(
                    "error",
                    "ToolManager | Session Close Error",
                    f"Error closing session for '{server_name}': {e}",
                )
        self._session_stacks.clear()
        self._sessions.clear()
        if self.browser_session is not None:
            try:
                await self.browser_session.close()
            except Exception:
                pass
            self.browser_session = None

    async def get_all_tool_definitions(self):
        """
        Connect to all configured servers and get their tool definitions.
        Returns a list suitable for passing to the Prompt generator.

        Sessions opened here are kept alive and reused by ``execute_tool_call``,
        so there is no need to reconnect when tools are actually invoked.
        """
        all_servers_for_prompt = []
        for config in self.server_configs:
            server_name = config["name"]
            server_params = config["params"]
            one_server_for_prompt = {"name": server_name, "tools": []}
            self._log(
                "info",
                "ToolManager | Get Tool Definitions",
                f"Getting tool definitions for server '{server_name}'...",
            )

            try:
                session = await self._get_or_create_session(server_name, server_params)
                tools_response = await session.list_tools()
                for tool in tools_response.tools:
                    if (server_name, tool.name) in self.tool_blacklist:
                        self._log(
                            "info",
                            "ToolManager | Tool Blacklisted",
                            f"Tool '{tool.name}' in server '{server_name}' is blacklisted, skipping.",
                        )
                        continue
                    one_server_for_prompt["tools"].append(
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "schema": tool.inputSchema,
                        }
                    )

                self._log(
                    "info",
                    "ToolManager | Tool Definitions Success",
                    f"Successfully obtained {len(one_server_for_prompt['tools'])} tool definitions from server '{server_name}'.",
                )
                all_servers_for_prompt.append(one_server_for_prompt)

            except Exception as e:
                self._log(
                    "error",
                    "ToolManager | Connection Error",
                    f"Error: Unable to connect or get tools from server '{server_name}': {e}",
                )
                one_server_for_prompt["tools"] = [
                    {"error": f"Unable to fetch tools: {e}"}
                ]
                all_servers_for_prompt.append(one_server_for_prompt)

        return all_servers_for_prompt

    @with_timeout(1200)
    async def execute_tool_call(self, server_name, tool_name, arguments) -> Any:
        """
        Execute a single tool call.
        :param server_name: Server name
        :param tool_name: Tool name
        :param arguments: Tool arguments dictionary
        :return: Dictionary containing result or error
        """

        # Original remote server call logic
        server_params = self.get_server_params(server_name)
        if not server_params:
            self._log(
                "error",
                "ToolManager | Server Not Found",
                f"Error: Attempting to call server '{server_name}' not found",
            )
            return {
                "server_name": server_name,
                "tool_name": tool_name,
                "error": f"Server '{server_name}' not found.",
            }

        self._log(
            "info",
            "ToolManager | Tool Call Start",
            f"Connecting to server '{server_name}' to call tool '{tool_name}'",
            metadata={"arguments": arguments},
        )

        if server_name == "playwright":
            try:
                if self.browser_session is None:
                    self.browser_session = PlaywrightSession(server_params)
                    await self.browser_session.connect()
                tool_result = await self.browser_session.call_tool(
                    tool_name, arguments=arguments
                )
                return {
                    "server_name": server_name,
                    "tool_name": tool_name,
                    "result": tool_result,
                }
            except Exception as e:
                return {
                    "server_name": server_name,
                    "tool_name": tool_name,
                    "error": f"Tool call failed: {str(e)}",
                }
        else:
            try:
                session = await self._get_or_create_session(server_name, server_params)
                result_content = None
                try:
                    tool_result = await session.call_tool(
                        tool_name, arguments=arguments
                    )
                    result_content = (
                        tool_result.content[-1].text if tool_result.content else ""
                    )
                    if self._should_block_hf_scraping(tool_name, arguments):
                        result_content = "You are trying to scrape a Hugging Face dataset for answers, please do not use the scrape tool for this purpose."
                except Exception as tool_error:
                    self._log(
                        "error",
                        "ToolManager | Tool Execution Error",
                        f"Tool execution error: {tool_error}",
                    )
                    return {
                        "server_name": server_name,
                        "tool_name": tool_name,
                        "error": f"Tool execution failed: {str(tool_error)}",
                    }

                self._log(
                    "info",
                    "ToolManager | Tool Call Success",
                    f"Tool '{tool_name}' (server: '{server_name}') called successfully.",
                )

                return {
                    "server_name": server_name,
                    "tool_name": tool_name,
                    "result": result_content,
                }

            except Exception as outer_e:
                self._log(
                    "error",
                    "ToolManager | Tool Call Failed",
                    f"Error: Failed to call tool '{tool_name}' (server: '{server_name}'): {outer_e}",
                )

                error_message = str(outer_e)

                if (
                    tool_name in ["scrape", "scrape_website"]
                    and "unhandled errors" in error_message
                    and "url" in arguments
                    and arguments["url"] is not None
                ):
                    try:
                        self._log(
                            "info",
                            "ToolManager | Fallback Attempt",
                            "Attempting fallback using MarkItDown...",
                        )
                        from markitdown import MarkItDown

                        md = MarkItDown(
                            docintel_endpoint="<document_intelligence_endpoint>"
                        )
                        result = md.convert(arguments["url"])
                        self._log(
                            "info",
                            "ToolManager | Fallback Success",
                            "MarkItDown fallback successful",
                        )
                        return {
                            "server_name": server_name,
                            "tool_name": tool_name,
                            "result": result.text_content,
                        }
                    except Exception as inner_e:
                        self._log(
                            "error",
                            "ToolManager | Fallback Failed",
                            f"Fallback also failed: {inner_e}",
                        )

                return {
                    "server_name": server_name,
                    "tool_name": tool_name,
                    "error": f"Tool call failed: {error_message}",
                }
