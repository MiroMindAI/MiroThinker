# Copyright (c) 2025 Miromind.ai
# This source code is licensed under the MIT License.

import os

from e2b_code_interpreter import Sandbox
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("stateless-python-server")

# API keys
E2B_API_KEY = os.environ.get("E2B_API_KEY")

# DEFAULT CONFS
DEFAULT_TIMEOUT = 300  # seconds


@mcp.tool()
async def python(code: str) -> str:
    """Use this tool to execute STATELESS Python code in your chain of thought. The code will not be shown to the user. This tool should be used for internal reasoning, but not for code that is intended to be visible to the user (e.g. when creating plots, tables, or files).
    When you send a message containing python code to python, it will be executed in a stateless docker container, and the stdout of that process will be returned to you. You have to use print statements to access the output.
    IMPORTANT: Your python environment is not shared between calls. You will have to pass your entire code each time.

        Args:
            code: The python code to run.

        Returns:
            A string containing the execution result including stdout and stderr.
    """
    sandbox = Sandbox.create(
        timeout=DEFAULT_TIMEOUT, api_key=E2B_API_KEY, template="1av7fdjfvcparqo8efq6"
    )

    max_attempts = 2
    for attempt in range(1, max_attempts + 1):
        try:
            execution = sandbox.run_code(code)
            break
        except Exception as e:
            if attempt == max_attempts:
                raise e
    execution = sandbox.run_code(code)

    sandbox.kill()

    return str(execution)


if __name__ == "__main__":
    mcp.run(transport="stdio")
