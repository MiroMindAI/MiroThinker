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
import json
import logging

from mcp import StdioServerParameters
from mcp.client.session import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client

logger = logging.getLogger("miroflow")


class PlaywrightSession:
    """Class to maintain a persistent Playwright MCP session."""

    def __init__(self, server_params):
        self.server_params = server_params
        self.read = None
        self.write = None
        self.session = None
        self._client = None

    async def connect(self):
        """Connect to the MCP server and initialize the session."""
        if self.session is None:
            if isinstance(self.server_params, StdioServerParameters):
                self._client = stdio_client(self.server_params)
            else:
                self._client = sse_client(self.server_params)
            self.read, self.write = await self._client.__aenter__()
            self.session = ClientSession(self.read, self.write, sampling_callback=None)
            await self.session.__aenter__()
            await self.session.initialize()
            logger.info("Connected to MCP server and initialized session")

    async def call_tool(self, tool_name, arguments=None):
        """Call a tool while maintaining the session."""
        if self.session is None:
            await self.connect()

        logger.info(f"Calling tool '{tool_name}'")
        tool_result = await self.session.call_tool(tool_name, arguments=arguments)
        result_content = tool_result.content[0].text if tool_result.content else ""
        return result_content

    async def close(self):
        """Close the session and connection."""
        if self.session:
            await self.session.__aexit__(None, None, None)
            self.session = None

        if self._client:
            await self._client.__aexit__(None, None, None)
            self._client = None
            self.read = None
            self.write = None
            logger.info("Closed MCP session")


# Example usage:
async def test_persistent_session():
    # Create a persistent session
    mcp_session = PlaywrightSession("http://localhost:8931")

    try:
        # First call: Navigate to a website
        await mcp_session.call_tool("browser_navigate", {"url": "https://example.com"})
        logger.info("Navigation complete")

        # Wait a moment for the page to load
        await asyncio.sleep(2)

        # Second call: Take a snapshot of the current page
        snapshot_result = await mcp_session.call_tool("browser_snapshot", {})

        # Process and save the snapshot
        snapshot_json = json.loads(snapshot_result)
        logger.info(f"Snapshot taken of page: {snapshot_json.get('url')}")
        logger.info(f"Page title: {snapshot_json.get('title')}")

        with open("snapshot.json", "w") as f:
            json.dump(snapshot_json, f, indent=2, ensure_ascii=False)

        logger.info("Snapshot saved to snapshot.json")

    finally:
        # Close the session when done with all tool calls
        await mcp_session.close()


if __name__ == "__main__":
    asyncio.run(test_persistent_session())
