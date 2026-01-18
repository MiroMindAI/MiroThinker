from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, Literal, cast

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import TextContent
from miroflow_tools.manager import ToolManagerProtocol
from pydantic import BaseModel, HttpUrl


class ConfigBase(BaseModel):
    name: str


class StdIOConfig(ConfigBase):
    kind: Literal["stdio"]
    params: StdioServerParameters


class SSEConfig(ConfigBase):
    kind: Literal["sse"]
    url: HttpUrl


class StreamableHttpConfig(ConfigBase):
    kind: Literal["streamable_http"]
    url: HttpUrl


Config = StdIOConfig | SSEConfig | StreamableHttpConfig


@asynccontextmanager
async def connect(cfg: Config):
    """
    returns a mcp.ClientSession instance, depending on Config.
    """
    async with AsyncExitStack() as stack:
        read, write = None, None
        if cfg.kind == "stdio":
            cfg = cast(StdIOConfig, cfg)
            read, write = await stack.enter_async_context(stdio_client(cfg.params))
        elif cfg.kind == "sse":
            cfg = cast(SSEConfig, cfg)
            read, write = await stack.enter_async_context(sse_client(str(cfg.url)))
        elif cfg.kind == "streamable_http":
            cfg = cast(StreamableHttpConfig, cfg)
            read, write, _ = await stack.enter_async_context(
                streamablehttp_client(str(cfg.url))
            )
        else:  # type: ignore
            raise TypeError("unknown kind {} in cfg".format(cfg.kind))
        if read is not None and write is not None:
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            yield session


class LoggingMixin:
    """
    add logging instance (.task_log) and helper functions (info(), error()) to any class.
    """

    task_log: Any = None

    def add_log(self, logger: Any):
        self.task_log = logger

    def _log(self, level: str, step_name: str, message: str, metadata=None):
        """Helper method to log using task_log if available, otherwise skip logging."""
        if self.task_log:
            self.task_log.log_step(level, step_name, message, metadata)

    def info(self, step_name: str, message: str):
        self._log("info", f"ToolManagerV2 | {step_name}", message)

    def error(self, step_name: str, message: str):
        self._log("error", f"ToolManagerV2 | {step_name}", message)


class ToolManagerV2(ToolManagerProtocol, LoggingMixin):
    """
    implements a barebone ToolManager. Difference in Version 2:
    1. Deprecate huggingface block + browser session (tool name no longer matches).
    2. add supports for streamable_http.
    """

    def __init__(self, server_configs: list[dict[str, Any]]):
        """
        Initialize ToolManager.
        :param server_configs: List returned by create_server_parameters()
        """
        parsed_configs = []
        for config in server_configs:
            kind = config.get("kind")
            if kind == "stdio":
                config = StdIOConfig.model_validate(config)
            elif kind == "sse":
                config = SSEConfig.model_validate(config)
            elif kind == "streamable_http":
                config = StreamableHttpConfig.model_validate(config)
            else:
                raise ValueError(f"unknown kind {kind} in config")
            parsed_configs.append(config)
        self.server_dict = {config.name: config for config in parsed_configs}

    async def get_all_tool_definitions(self):
        """
        Connect to all configured servers and get their tool definitions.
        Returns a list suitable for passing to the Prompt generator.
        """

        async def inner_list_tools(session: ClientSession):
            """helper function to reduce indentation level"""
            try:
                response = await session.list_tools()
                return response, None
            except Exception as e:
                return None, e

        final = []
        # Process remote server tools
        for name, config in self.server_dict.items():
            self.info(
                "Get Tool Definitions",
                f"Getting tool definitions for server '{name}'...",
            )
            curr = {"name": name, "tools": []}
            try:
                async with connect(config) as session:
                    response, error = await inner_list_tools(session)
                    if error is not None:
                        self.error(
                            "List Tools Error",
                            f"Unable to connect or get tools from server '{name}': {str(error)}",
                        )
                        curr["tools"] = [
                            {"error": f"Unable to fetch tools: {str(error)}"}
                        ]
                    if response is not None:
                        for tool in response.tools:
                            curr["tools"].append(
                                {
                                    "name": tool.name,  # type: ignore
                                    "description": tool.description,
                                    "schema": tool.inputSchema,
                                }
                            )
            except Exception as e:
                self.error("MCP session Error", f"MCP session error: {str(e)}")
                curr["tools"] = [{"error": f"MCP session error: {str(e)}"}]
            finally:
                final.append(curr)

        return final

    async def execute_tool_call(
        self, *, server_name: str, tool_name: str, arguments: dict[str, Any]
    ) -> Any:
        """
        Execute a single tool call.
        :param server_name: Server name
        :param tool_name: Tool name
        :param arguments: Tool arguments dictionary
        :return: Dictionary containing result or error
        """

        def rv(*, exc: str | None = None, res: str | None = None):
            common = {"server_name": server_name, "tool_name": tool_name}
            depends = {"error": exc} if exc is not None else {"result": res}
            return common | depends

        async def inner_call_tool(
            session: ClientSession, tool_name: str, arguments: dict[str, Any]
        ):
            """helper function to reduce indentation level"""
            try:
                tool_result = await session.call_tool(tool_name, arguments=arguments)
                final = ""
                if tool_result is not None:
                    if (
                        getattr(tool_result, "content", None) is not None
                        and len(tool_result.content) > 0
                    ):
                        block = tool_result.content[-1]
                        if isinstance(block, TextContent):
                            final = block.text
                return final, None
            except Exception as e:
                return None, e

        config = self.server_dict.get(server_name, None)
        if config is None:
            self.error(
                "Server Not Found",
                f"Attempting to call server '{server_name}' not found",
            )
            return rv(exc=f"Server '{server_name}' not found.")

        self.info(
            "Tool Call Start",
            f"Connecting to server '{server_name}' to call tool '{tool_name}'",
        )
        try:
            async with connect(config) as session:
                res, exc = await inner_call_tool(session, tool_name, arguments)
                if exc is not None:
                    self.error(
                        "Tool Execution Error",
                        f"Tool execution error: {exc}",
                    )
                    return rv(exc=f"Tool execution failed: {str(exc)}")
                if res is not None:
                    return rv(res=res)
        except Exception as e:
            self.error(
                "MCP Session Error",
                f"MCP session error: {e}",
            )
            return rv(exc=f"MCP session error: {str(e)}")
