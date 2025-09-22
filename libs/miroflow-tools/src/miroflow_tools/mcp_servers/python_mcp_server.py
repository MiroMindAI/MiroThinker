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
import os

from e2b_code_interpreter import Sandbox
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("e2b-python-interpreter")

# API keys
E2B_API_KEY = os.environ.get("E2B_API_KEY")
LOGS_DIR = os.environ.get(
    "LOGS_DIR", "../../logs"
)  # Directory where benchmark logs are stored

# DEFAULT TEMPLATE ID
DEFAULT_TEMPLATE_ID = "all_pip_apt_pkg"

# DEFAULT METADATA
DEFAULT_METADATA = {"env": "miro-thinker"}

# DEFAULT CONFS
DEFAULT_TIMEOUT = 1800  # seconds


@mcp.tool()
async def create_sandbox() -> str:
    """Create a linux sandbox.

    Args:
        timeout: Time in seconds before the sandbox is automatically shutdown. The default is 300 seconds.

    Returns:
        The id of the newly created sandbox. You should use this sandbox_id to run other tools in the sandbox.
    """
    max_retries = 3
    sandbox = None
    for attempt in range(1, max_retries + 1):
        try:
            sandbox = Sandbox.create(
                template=DEFAULT_TEMPLATE_ID,
                timeout=DEFAULT_TIMEOUT,
                api_key=E2B_API_KEY,
                metadata=DEFAULT_METADATA,
            )
            info = sandbox.get_info()
            # sandbox.beta_pause()

            tmpfiles_dir = os.path.join(LOGS_DIR, "tmpfiles")
            os.makedirs(tmpfiles_dir, exist_ok=True)

            return f"Sandbox created with sandbox_id: {info.sandbox_id}"
        except Exception as e:
            if attempt == max_retries:
                return f"Failed to create sandbox after {max_retries} attempts: {e}, please retry later."
            await asyncio.sleep(attempt * 2)  # Exponential backoff
        finally:
            # Set timeout before exit to prevent timeout after function exits
            try:
                if sandbox is not None:
                    sandbox.beta_pause()
                # sandbox.set_timeout(DEFAULT_TIMEOUT)
            except Exception:
                pass  # Ignore timeout setting errors


@mcp.tool()
async def run_command(command: str, sandbox_id: str) -> str:
    """Execute a command in the linux sandbox.

    Args:
        command: The command to execute.
        sandbox_id: The id of the sandbox to execute the command in. To create a new sandbox, use tool `create_sandbox`.

    Returns:
        A CommandResult object containing the result of the command execution, format like CommandResult(stderr=..., stdout=..., exit_code=..., error=...)
    """
    sandbox = None
    try:
        sandbox = Sandbox.connect(sandbox_id, api_key=E2B_API_KEY)
    except Exception:
        return f"[ERROR]: Failed to connect to sandbox {sandbox_id}, retry later. Make sure the sandbox is created and the id is correct."

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            # sandbox.set_timeout(
            #     DEFAULT_TIMEOUT
            # )  # refresh the timeout for each command execution
            result = sandbox.commands.run(command, timeout=DEFAULT_TIMEOUT)

            # Check if command contains package installation commands
            result_str = str(result)
            if "pip install" in command or "apt-get" in command:
                result_str += "\n\n[PACKAGE INSTALL STATUS]: The system packages and Python packages required for the task have been installed. No need to install them again unless a missing package error occurs during execution."

            return result_str
        except Exception as e:
            if attempt == max_retries:
                error_msg = f"[ERROR]: Failed to run command after {max_retries} attempts. Exception type: {type(e).__name__}, Details: {e}. \n\n[HINT]: Shell commands can be error-prone. Consider using the `run_python_code` tool instead to accomplish the same task with Python code, which often provides better error handling and more detailed error messages.\n\n[PERMISSION HINT]: You are running as user, not root. If you encounter permission issues, use `sudo` for commands that require administrator privileges (e.g., `sudo apt-get install`, `sudo systemctl`, etc.)."

                # Add package install status note for failed install commands too
                if "pip install" in command or "apt-get" in command:
                    error_msg += "\n\n[PACKAGE INSTALL STATUS]: The system packages and Python packages required for the task have been installed. No need to install them again unless a missing package error occurs during execution."

                return error_msg
            await asyncio.sleep(attempt * 2)  # Exponential backoff
        finally:
            # Set timeout before exit to prevent timeout after function exits
            try:
                sandbox.beta_pause()
                # sandbox.set_timeout(DEFAULT_TIMEOUT)
            except Exception:
                pass  # Ignore timeout setting errors


@mcp.tool()
async def run_python_code(code_block: str, sandbox_id: str) -> str:
    """Run python code in an interpreter and return the execution result.

    Args:
        code_block: The python code to run.
        sandbox_id: The id of the sandbox to run the code in. Reuse existing sandboxes whenever possible. To create a new sandbox, use tool `create_sandbox`.

    Returns:
        A CommandResult object containing the result of the command execution, format like CommandResult(stderr=..., stdout=..., exit_code=..., error=...)
    """
    sandbox = None
    try:
        sandbox = Sandbox.connect(sandbox_id=sandbox_id, api_key=E2B_API_KEY)
    except Exception:
        return f"[ERROR]: Failed to connect to sandbox {sandbox_id}, retry later. Make sure the sandbox is created and the id is correct."

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            # sandbox.set_timeout(
            #     DEFAULT_TIMEOUT
            # )  # refresh the timeout for each command execution

            execution = sandbox.run_code(code_block, timeout=DEFAULT_TIMEOUT)
            return str(execution)
        except Exception as e:
            if attempt == max_retries:
                return f"[ERROR]: Failed to run code in sandbox {sandbox_id} after {max_retries} attempts. Exception type: {type(e).__name__}, Details: {e}."
            await asyncio.sleep(attempt * 2)  # Exponential backoff
        finally:
            # Set timeout before exit to prevent timeout after function exits
            try:
                sandbox.beta_pause()
                # sandbox.set_timeout(DEFAULT_TIMEOUT)
            except Exception:
                pass  # Ignore timeout setting errors


@mcp.tool()
async def upload_file_from_local_to_sandbox(
    sandbox_id: str, local_file_path: str, sandbox_file_path: str = "/home/user"
) -> str:
    """Upload a local file to the `/home/user` dir of the remote python interpreter.

    Args:
        sandbox_id: The id of the sandbox to run the code in. Reuse existing sandboxes whenever possible. To create a new sandbox, use tool `create_sandbox`.
        local_file_path: The path of the file on local machine to upload.
        sandbox_file_path: The path of directory to upload the file to in the sandbox. Default is `/home/user/`.

    Returns:
        The path of the uploaded file in the remote python interpreter if the upload is successful.
    """
    sandbox = None
    try:
        sandbox = Sandbox.connect(sandbox_id, api_key=E2B_API_KEY)
    except Exception:
        return f"[ERROR]: Failed to connect to sandbox {sandbox_id}, retry later. Make sure the sandbox is created and the id is correct."

    try:
        # sandbox.set_timeout(
        #     DEFAULT_TIMEOUT
        # )  # refresh the timeout for each command execution

        # Get the uploaded file path
        uploaded_file_path = os.path.join(
            sandbox_file_path, os.path.basename(local_file_path)
        )

        # Upload the file
        with open(local_file_path, "rb") as f:
            sandbox.files.write(uploaded_file_path, f, request_timeout=DEFAULT_TIMEOUT)

        return f"File uploaded to {uploaded_file_path}\n\n[INFO]: For directly reading local files without uploading to sandbox, consider using the `convert_to_markdown` tool which can read various file types (Doc, PPT, PDF, Excel, CSV, ZIP, etc.) directly from local paths or URLs. Note that `convert_to_markdown` doesn't support files already in the sandbox."
    except Exception as e:
        return f"[ERROR]: Failed to upload file {local_file_path} to sandbox {sandbox_id}: {e}\n\n[INFO]: This tool is for uploading local files to the sandbox. For security reasons, downloading files from sandbox to local system is not supported. Alternatively, consider using the `convert_to_markdown` tool which can directly read various file types (Doc, PPT, PDF, Excel, CSV, ZIP, etc.) from local paths or URLs without uploading to sandbox."
    finally:
        # Set timeout before exit to prevent timeout after function exits
        try:
            sandbox.beta_pause()
            # sandbox.set_timeout(DEFAULT_TIMEOUT)
        except Exception:
            pass  # Ignore timeout setting errors


@mcp.tool()
async def download_file_from_internet_to_sandbox(
    sandbox_id: str, url: str, sandbox_file_path: str = "/home/user"
) -> str:
    """Download a file from the internet to the `/home/user` dir of the remote python interpreter.

    Args:
        sandbox_id: The id of the sandbox to run the code in. Reuse existing sandboxes whenever possible. To create a new sandbox, use tool `create_sandbox`.
        url: The URL of the file to download.
        sandbox_file_path: The path of directory to download the file to in the sandbox. Default is `/home/user/`.

    Returns:
        The path of the downloaded file in the python interpreter if the download is successful.
    """
    sandbox = None
    try:
        sandbox = Sandbox.connect(sandbox_id, api_key=E2B_API_KEY)
    except Exception:
        return f"[ERROR]: Failed to connect to sandbox {sandbox_id}, retry later. Make sure the sandbox is created and the id is correct."

    try:
        # sandbox.set_timeout(
        #     DEFAULT_TIMEOUT
        # )  # refresh the timeout for each command execution

        downloaded_file_path = os.path.join(sandbox_file_path, os.path.basename(url))

        # Download the file with retry logic
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            result = sandbox.commands.run(
                f"wget {url} -O {downloaded_file_path}", timeout=DEFAULT_TIMEOUT
            )
            if result.exit_code == 0:
                return f"File downloaded to {downloaded_file_path}\n\n[INFO]: For directly reading files from internet URLs without downloading to sandbox, consider using the `convert_to_markdown` tool which can read various file types (Doc, PPT, PDF, Excel, CSV, ZIP, etc.) directly from URLs. Note that `convert_to_markdown` doesn't support files already in the sandbox."
            elif attempt < max_retries:
                await asyncio.sleep(4**attempt)
                continue  # Retry
            else:
                return f"[ERROR]: Failed to download file from {url} to {downloaded_file_path} after {max_retries} attempts: {result}.\n\n[INFO]: This tool is for downloading files from the internet to the sandbox. To upload local files to the sandbox, use `upload_file_from_local_to_sandbox` instead. Alternatively, consider using the `convert_to_markdown` tool which can directly read various file types (Doc, PPT, PDF, Excel, CSV, ZIP, etc.) from internet URLs without downloading to sandbox."
    except Exception as e:
        return f"[ERROR]: Failed to download file from {url}: {e}\n\n[INFO]: This tool is for downloading files from the internet to the sandbox. To upload local files to the sandbox, use `upload_file_from_local_to_sandbox` instead. Alternatively, consider using the `convert_to_markdown` tool which can directly read various file types (Doc, PPT, PDF, Excel, CSV, ZIP, etc.) from internet URLs without downloading to sandbox."
    finally:
        # Set timeout before exit to prevent timeout after function exits
        try:
            sandbox.beta_pause()
            # sandbox.set_timeout(DEFAULT_TIMEOUT)
        except Exception:
            pass  # Ignore timeout setting errors


@mcp.tool()
async def download_file_from_sandbox_to_local(
    sandbox_id: str, sandbox_file_path: str, local_filename: str = None
) -> str:
    """Download a file from the sandbox to local system. Files in sandbox cannot be processed by tools from other servers - only local files and internet URLs can be processed by them.

    Args:
        sandbox_id: The id of the sandbox to download the file from. To have a sandbox, use tool `create_sandbox`.
        sandbox_file_path: The path of the file to download on the sandbox.
        local_filename: Optional filename to save as. If not provided, uses the original filename from sandbox_file_path.

    Returns:
        The local path of the downloaded file if successful, otherwise error message.
    """
    sandbox = None
    try:
        sandbox = Sandbox.connect(sandbox_id, api_key=E2B_API_KEY)
    except Exception:
        return f"[ERROR]: Failed to connect to sandbox {sandbox_id}, retry later. Make sure the sandbox is created and the id is correct."

    try:
        # sandbox.set_timeout(
        #     DEFAULT_TIMEOUT
        # )  # refresh the timeout for each command execution

        # Create tmpfiles directory if it doesn't exist
        if not LOGS_DIR:
            return "[ERROR]: LOGS_DIR environment variable is not set. Cannot determine where to save the file."

        tmpfiles_dir = os.path.join(LOGS_DIR, "tmpfiles")
        os.makedirs(tmpfiles_dir, exist_ok=True)

        # Determine local filename
        if local_filename is None or local_filename.strip() == "":
            local_filename = os.path.basename(sandbox_file_path)

        local_file_path = os.path.join(
            tmpfiles_dir, f"sandbox_{sandbox_id}_{local_filename}"
        )

        # Download the file
        with open(local_file_path, "wb") as f:
            content = sandbox.files.read(
                sandbox_file_path, format="bytes", request_timeout=DEFAULT_TIMEOUT
            )
            f.write(content)

        return f"File downloaded successfully to: {local_file_path}\n\n[INFO]: The file can now be accessed by other tools (reading, question-answering, etc.) which only support local files and internet URLs, not sandbox files."
    except Exception as e:
        return f"[ERROR]: Failed to download file {sandbox_file_path} from sandbox {sandbox_id}: {e}\n\n[INFO]: This tool is for downloading files from the sandbox to local system. To upload local files to the sandbox, use `upload_file_from_local_to_sandbox` instead."
    finally:
        # Set timeout before exit to prevent timeout after function exits
        try:
            sandbox.beta_pause()
            # sandbox.set_timeout(DEFAULT_TIMEOUT)
        except Exception:
            pass  # Ignore timeout setting errors


if __name__ == "__main__":
    mcp.run(transport="stdio")
