# Copyright (c) 2025 MiroMind
# This source code is licensed under the Apache 2.0 License.

import asyncio
import functools
import logging
from typing import Any, Awaitable, Callable, Protocol, TypeVar

from mcp import ClientSession, StdioServerParameters  # (already imported in config.py)
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client

from .mcp_servers.browser_session import PlaywrightSession

logger = logging.getLogger("miroflow_agent")

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


class PersistentMCPSession:
    """Maintains a persistent MCP session for a single server (stdio or SSE).

    Instead of spawning a new subprocess for every tool call, this keeps the
    subprocess alive and reuses the session across calls.  On connection
    failure it transparently reconnects once.
    """

    def __init__(self, server_name: str, server_params):
        self.server_name = server_name
        self.server_params = server_params
        self._client = None
        self._session: ClientSession | None = None
        self._lock = asyncio.Lock()

    async def _connect(self):
        """Establish the underlying transport + MCP session."""
        if isinstance(self.server_params, StdioServerParameters):
            self._client = stdio_client(self.server_params)
        elif isinstance(self.server_params, str) and self.server_params.startswith(
            ("http://", "https://")
        ):
            self._client = sse_client(self.server_params)
        else:
            raise TypeError(
                f"Unknown server params type for {self.server_name}: "
                f"{type(self.server_params)}"
            )

        read, write = await self._client.__aenter__()
        self._session = ClientSession(read, write, sampling_callback=None)
        await self._session.__aenter__()
        await self._session.initialize()

    async def ensure_connected(self):
        """Connect if not already connected."""
        async with self._lock:
            if self._session is None:
                await self._connect()

    async def call_tool(self, tool_name: str, arguments: dict | None = None) -> str:
        """Call a tool, reconnecting once on failure."""
        await self.ensure_connected()
        try:
            tool_result = await self._session.call_tool(tool_name, arguments=arguments)
            return tool_result.content[-1].text if tool_result.content else ""
        except Exception:
            # Connection may have died — reconnect once and retry
            await self.close()
            await self.ensure_connected()
            tool_result = await self._session.call_tool(tool_name, arguments=arguments)
            return tool_result.content[-1].text if tool_result.content else ""

    async def close(self):
        """Tear down session and transport."""
        async with self._lock:
            if self._session is not None:
                try:
                    await self._session.__aexit__(None, None, None)
                except Exception:
                    pass
                self._session = None
            if self._client is not None:
                try:
                    await self._client.__aexit__(None, None, None)
                except Exception:
                    pass
                self._client = None


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
        # Persistent MCP sessions keyed by server name
        self._sessions: dict[str, PersistentMCPSession] = {}

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

    def _get_or_create_session(self, server_name: str) -> PersistentMCPSession:
        """Get an existing persistent session or create a new one."""
        if server_name not in self._sessions:
            server_params = self.server_dict[server_name]
            self._sessions[server_name] = PersistentMCPSession(
                server_name, server_params
            )
        return self._sessions[server_name]

    async def _get_single_server_tools(self, config):
        """Connect to a single server and get its tool definitions."""
        server_name = config["name"]
        server_params = config["params"]
        one_server_for_prompt = {"name": server_name, "tools": []}
        self._log(
            "info",
            "ToolManager | Get Tool Definitions",
            f"Getting tool definitions for server '{server_name}'...",
        )

        try:
            if isinstance(server_params, StdioServerParameters):
                async with stdio_client(server_params) as (read, write):
                    async with ClientSession(
                        read, write, sampling_callback=None
                    ) as session:
                        await session.initialize()
                        tools_response = await session.list_tools()
                        # black list some tools
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
            elif isinstance(server_params, str) and server_params.startswith(
                ("http://", "https://")
            ):
                # SSE endpoint
                async with sse_client(server_params) as (read, write):
                    async with ClientSession(
                        read, write, sampling_callback=None
                    ) as session:
                        await session.initialize()
                        tools_response = await session.list_tools()
                        for tool in tools_response.tools:
                            one_server_for_prompt["tools"].append(
                                {
                                    "name": tool.name,
                                    "description": tool.description,
                                    "schema": tool.inputSchema,
                                }
                            )
            else:
                self._log(
                    "error",
                    "ToolManager | Unknown Parameter Type",
                    f"Error: Unknown parameter type for server '{server_name}': {type(server_params)}",
                )
                raise TypeError(
                    f"Unknown server params type for {server_name}: {type(server_params)}"
                )

            self._log(
                "info",
                "ToolManager | Tool Definitions Success",
                f"Successfully obtained {len(one_server_for_prompt['tools'])} tool definitions from server '{server_name}'.",
            )

        except Exception as e:
            self._log(
                "error",
                "ToolManager | Connection Error",
                f"Error: Unable to connect or get tools from server '{server_name}': {e}",
            )
            # Still add server entry, but mark tool list as empty or include error information
            one_server_for_prompt["tools"] = [{"error": f"Unable to fetch tools: {e}"}]

        return one_server_for_prompt

    async def get_all_tool_definitions(self):
        """
        Connect to all configured servers and get their tool definitions.
        Servers are initialized in parallel using asyncio.gather() for speed.
        Returns a list suitable for passing to the Prompt generator.
        """
        # Launch all server connections in parallel
        results = await asyncio.gather(
            *(self._get_single_server_tools(config) for config in self.server_configs),
            return_exceptions=True,
        )

        all_servers_for_prompt = []
        for config, result in zip(self.server_configs, results):
            if isinstance(result, Exception):
                server_name = config["name"]
                self._log(
                    "error",
                    "ToolManager | Connection Error",
                    f"Error: Unable to connect or get tools from server '{server_name}': {result}",
                )
                all_servers_for_prompt.append(
                    {
                        "name": server_name,
                        "tools": [{"error": f"Unable to fetch tools: {result}"}],
                    }
                )
            else:
                all_servers_for_prompt.append(result)

        return all_servers_for_prompt

    @with_timeout(1200)
    async def execute_tool_call(self, server_name, tool_name, arguments) -> Any:
        """
        Execute a single tool call using a persistent MCP session.
        Sessions are lazily created on first call and reused across subsequent calls.
        """

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
            f"Calling tool '{tool_name}' on server '{server_name}' (persistent session)",
            metadata={"arguments": arguments},
        )

        # Playwright keeps its own special session (browser state)
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

        # All other servers: use persistent session
        try:
            session = self._get_or_create_session(server_name)
            result_content = await session.call_tool(tool_name, arguments)

            # post hoc check for browsing agent reading answers from hf datasets
            if self._should_block_hf_scraping(tool_name, arguments):
                result_content = "You are trying to scrape a Hugging Face dataset for answers, please do not use the scrape tool for this purpose."

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

    async def close_all_sessions(self):
        """Close all persistent MCP sessions. Call at task end."""
        for name, session in self._sessions.items():
            try:
                await session.close()
                self._log(
                    "info",
                    "ToolManager | Session Closed",
                    f"Closed persistent session for server '{name}'",
                )
            except Exception as e:
                self._log(
                    "error",
                    "ToolManager | Session Close Error",
                    f"Error closing session for server '{name}': {e}",
                )
        self._sessions.clear()

        # Also close playwright session
        if self.browser_session is not None:
            try:
                await self.browser_session.close()
            except Exception:
                pass
            self.browser_session = None
