# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

import argparse
import logging
import sys

from fastmcp import FastMCP
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger("miroflow")

# Initialize FastMCP server
mcp = FastMCP("reading-mcp-server")


@mcp.tool()
async def convert_to_markdown(uri: str) -> str:
    """Convert various types of resources (doc, ppt, pdf, excel, csv, zip file etc.)
    described by an file: or data: URI to markdown.

    Args:
        uri: Required. The URI of the resource to convert. Need to start with 'file:' or 'data:' schemes.

    Returns:
        str: The converted markdown content, or an error message if conversion fails.
    """
    if not uri or not uri.strip():
        return "Error: URI parameter is required and cannot be empty."

    # Validate URI scheme
    valid_schemes = ["http:", "https:", "file:", "data:"]
    if not any(uri.lower().startswith(scheme) for scheme in valid_schemes):
        return f"Error: Invalid URI scheme. Supported schemes are: {', '.join(valid_schemes)}"

    tool_name = "convert_to_markdown"
    arguments = {"uri": uri}

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "markitdown_mcp"],
    )

    result_content = ""
    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write, sampling_callback=None) as session:
                await session.initialize()
                try:
                    tool_result = await session.call_tool(
                        tool_name, arguments=arguments
                    )
                    result_content = (
                        tool_result.content[-1].text if tool_result.content else ""
                    )
                except Exception as tool_error:
                    logger.info(f"Tool execution error: {tool_error}")
                    return f"Error: Tool execution failed: {str(tool_error)}"
    except Exception as session_error:
        logger.info(f"Session error: {session_error}")
        return (
            f"Error: Failed to connect to markitdown-mcp server: {str(session_error)}"
        )

    return result_content


if __name__ == "__main__":
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Reading MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport method: 'stdio' or 'http' (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to use when running with HTTP transport (default: 8080)",
    )
    parser.add_argument(
        "--path",
        type=str,
        default="/mcp",
        help="URL path to use when running with HTTP transport (default: /mcp)",
    )

    # Parse command line arguments
    args = parser.parse_args()

    # Run the server with the specified transport method
    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        # For HTTP transport, include port and path options
        mcp.run(transport="streamable-http", port=args.port, path=args.path)
