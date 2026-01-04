# 🛠️ MiroFlow Tools

> A comprehensive tool management system and MCP (Model Context Protocol) server collection for MiroFlow, providing a unified interface to various AI capabilities including code execution, vision processing, audio transcription, web searching, reasoning, and document reading.

## ✨ Features

- **🔧 Unified Tool Management**: Centralized `ToolManager` for managing multiple MCP servers
- **🌐 Multiple Transport Protocols**: Support for both stdio and SSE (HTTP) connections
- **📦 Rich Tool Ecosystem**: Pre-built MCP servers for common AI tasks
- **⚙️ Flexible Configuration**: Tool blacklisting, timeout management, and custom server configurations
- **🛡️ Error Handling**: Robust retry logic and fallback mechanisms

## 📦 Installation

```bash
pip install miroflow-tools
```

## 📋 MCP Servers Overview

Quick reference tables of all available MCP servers and their tools. Click on "Details" to jump to the full documentation.

### 📊 Tools Used in MiroThinker v1.0 and v1.5

The following tools were used in the MiroThinker v1.0 and v1.5 evaluation:

| Category                   | Server Name                 | Tools                                                                                                                | Key Environment Variables                                                                 | Link                                     |
|----------------------------|-----------------------------|----------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------|------------------------------------------|
| **Execution Environment**  | `tool-python`               | `create_sandbox`, `run_command`, `run_python_code`                                                                   | `E2B_API_KEY`, `LOGS_DIR`                                                                 | [Details](#tool-python)                  |
| **File Management**        | `tool-python`               | `upload_file_from_local_to_sandbox`, `download_file_from_sandbox_to_local`, `download_file_from_internet_to_sandbox` | `E2B_API_KEY`, `LOGS_DIR`                                                                 | [Details](#tool-python)                  |
| **Information Retrieval**  | `search_and_scrape_webpage` | `google_search`                                                                                                      | `SERPER_API_KEY`, `SERPER_BASE_URL`                                                        | [Details](#search_and_scrape_webpage)    |
| **Information Retrieval**  | `jina_scrape_llm_summary`   | `scrape_and_extract_info`                                                                                            | `JINA_API_KEY`, `JINA_BASE_URL`, `SUMMARY_LLM_BASE_URL`, `SUMMARY_LLM_MODEL_NAME`, `SUMMARY_LLM_API_KEY` | [Details](#jina_scrape_llm_summary)      |

### 🔧 Additional Available Tools

The following tools are implemented but were not used in the MiroThinker v1.0/v1.5 evaluation:

| Category                    | Server Name          | Tools                                             | Key Environment Variables                                           | Link                           |
|-----------------------------|----------------------|---------------------------------------------------|---------------------------------------------------------------------|--------------------------------|
| **Web Searching**           | `tool-google-search` | `google_search`, `scrape_website`                 | `SERPER_API_KEY`, `SERPER_BASE_URL`, `JINA_API_KEY`, `JINA_BASE_URL` | [Details](#tool-google-search) |
| **Web Searching (Sougou)**  | `tool-sougou-search` | `sougou_search`, `scrape_website`                 | `TENCENTCLOUD_SECRET_ID`, `TENCENTCLOUD_SECRET_KEY`, `JINA_API_KEY`, `JINA_BASE_URL` | [Details](#tool-sougou-search) |
| **Vision Processing**       | `tool-vqa`           | `visual_question_answering`                       | `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`                            | [Details](#tool-vqa)           |
| **Vision Processing**       | `tool-vqa-os`        | `visual_question_answering`                       | `VISION_API_KEY`, `VISION_BASE_URL`, `VISION_MODEL_NAME`            | [Details](#tool-vqa-os)        |
| **Audio Processing**        | `tool-transcribe`    | `audio_transcription`, `audio_question_answering` | `OPENAI_API_KEY`, `OPENAI_BASE_URL`                                  | [Details](#tool-transcribe)    |
| **Audio Processing**        | `tool-transcribe-os` | `audio_transcription`                             | `WHISPER_API_KEY`, `WHISPER_BASE_URL`, `WHISPER_MODEL_NAME`         | [Details](#tool-transcribe-os) |
| **Document Reading**        | `tool-reading`       | `convert_to_markdown`                             | None required                                                       | [Details](#tool-reading)       |
| **Reasoning Engine**        | `tool-reasoning`     | `reasoning`                                       | `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`                            | [Details](#tool-reasoning)     |
| **Reasoning Engine**        | `tool-reasoning-os`  | `reasoning`                                       | `REASONING_API_KEY`, `REASONING_BASE_URL`, `REASONING_MODEL_NAME`   | [Details](#tool-reasoning-os)  |

## 🚀 Quick Start

<details>
<summary>Click to expand code example</summary>

```python
import asyncio
from miroflow_tools import ToolManager
from mcp import StdioServerParameters

async def main():
# Initialize tool manager with server configurations
    server_configs = [
        {
            "name": "tool-python",
            "params": StdioServerParameters(
                command="python",
                args=["-m", "miroflow_tools.mcp_servers.python_mcp_server"],
                env={"E2B_API_KEY": "your_e2b_api_key"}  # Required for Python execution
            )
        },
        # Add more server configurations...
    ]

    tool_manager = ToolManager(server_configs)

    # Get all available tool definitions
    tool_definitions = await tool_manager.get_all_tool_definitions()

    # Create a sandbox first
    sandbox_result = await tool_manager.execute_tool_call(
        server_name="tool-python",
        tool_name="create_sandbox",
        arguments={"timeout": 600}
    )

    # Extract sandbox_id from result
    sandbox_id = sandbox_result['result'].split('sandbox_id:')[-1].strip()

    # Execute a tool call
    result = await tool_manager.execute_tool_call(
    server_name="tool-python",
    tool_name="run_python_code",
        arguments={"code_block": "print('Hello, World!')", "sandbox_id": sandbox_id}
    )
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
```

</details>

## 🔧 ToolManager

The `ToolManager` class is the central component for managing and executing tools across multiple MCP servers.

### Key Features

- **🔌 Multi-Server Support**: Manage tools from multiple MCP servers simultaneously
- **🔗 Connection Management**: Automatic connection handling for stdio and SSE transports
- **🚫 Tool Blacklisting**: Filter out specific tools from specific servers
- **📝 Structured Logging**: Optional task logging integration
- **🔄 Error Recovery**: Automatic retry logic and fallback mechanisms

### Methods

- `get_all_tool_definitions()`: Retrieve tool schemas from all configured servers
- `execute_tool_call(server_name, tool_name, arguments)`: Execute a specific tool
- `set_task_log(task_log)`: Enable structured logging
- `get_server_params(server_name)`: Get configuration for a specific server

### Example Usage

<details>
<summary>Click to expand code example</summary>

```python
import asyncio
from miroflow_tools import ToolManager
from mcp import StdioServerParameters

async def main():
    # Configure servers
    server_configs = [
        {
            "name": "python-server",
            "params": StdioServerParameters(
                command="python",
                args=["-m", "miroflow_tools.mcp_servers.python_mcp_server"],
                env={"E2B_API_KEY": "your_key"}
            )
        }
    ]

    # Initialize with optional blacklist
    tool_blacklist = {("python-server", "some_tool")}
    manager = ToolManager(server_configs, tool_blacklist=tool_blacklist)

    # Enable logging
    # manager.set_task_log(your_task_logger)

    # Get tools
    tools = await manager.get_all_tool_definitions()

    # Create a sandbox first (required before running code)
    sandbox_result = await manager.execute_tool_call(
        server_name="python-server",
        tool_name="create_sandbox",
        arguments={"timeout": 600}
    )
    sandbox_id = sandbox_result['result'].split('sandbox_id:')[-1].strip()

    # Execute tool
    result = await manager.execute_tool_call(
        server_name="python-server",
        tool_name="run_python_code",
        arguments={"code_block": "1 + 1", "sandbox_id": sandbox_id}
    )
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
```

</details>

## 🔌 MCP Servers

### Server: tool-python

Execute Python code in isolated E2B sandboxes with persistent sessions.

**Tools**:

- 🔨 `create_sandbox(timeout=600)`: Create a new Linux sandbox
- 🐍 `run_python_code(code_block, sandbox_id)`: Execute Python code
- 💻 `run_command(command, sandbox_id)`: Run shell commands
- ⬆️ `upload_file_from_local_to_sandbox(sandbox_id, local_file_path, sandbox_file_path)`: Upload files
- ⬇️ `download_file_from_internet_to_sandbox(sandbox_id, url, sandbox_file_path)`: Download files
- 💾 `download_file_from_sandbox_to_local(sandbox_id, sandbox_file_path, local_filename)`: Download files

**Environment Variables**:

- 🔑 `E2B_API_KEY`: E2B API key (required)
- 📁 `LOGS_DIR`: Directory for temporary files (default: `../../logs`)

**Example**:

<details>
<summary>Click to expand code example</summary>

```python
import asyncio
from miroflow_tools import ToolManager
from mcp import StdioServerParameters

async def main():
    # Configure server with environment variables
    server_configs = [
        {
            "name": "tool-python",
            "params": StdioServerParameters(
                command="python",
                args=["-m", "miroflow_tools.mcp_servers.python_mcp_server"],
                env={"E2B_API_KEY": "your_e2b_api_key"}
            )
        }
    ]

    manager = ToolManager(server_configs)

    # Create sandbox
    result = await manager.execute_tool_call(
        server_name="tool-python",
        tool_name="create_sandbox",
        arguments={"timeout": 600}
    )

    # Extract sandbox_id from result
    sandbox_id = result['result'].split('sandbox_id:')[-1].strip()

    # Run code
    result = await manager.execute_tool_call(
        server_name="tool-python",
        tool_name="run_python_code",
        arguments={"code_block": "import numpy as np; print(np.array([1,2,3]))", "sandbox_id": sandbox_id}
    )
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
```

</details>

### Server: tool-vqa

Analyze images and answer questions about visual content using Anthropic Claude.

**Tools**:

- 👁️ `visual_question_answering(image_path_or_url, question)`: Answer questions about images

**Environment Variables**:

- 🔑 `ANTHROPIC_API_KEY`: Anthropic API key (required)
- 🌐 `ANTHROPIC_BASE_URL`: API base URL (default: `https://api.anthropic.com`)

**Example**:

<details>
<summary>Click to expand code example</summary>

```python
import asyncio
from miroflow_tools import ToolManager
from mcp import StdioServerParameters

async def main():
    server_configs = [
        {
            "name": "tool-vqa",
            "params": StdioServerParameters(
                command="python",
                args=["-m", "miroflow_tools.mcp_servers.vision_mcp_server"],
                env={
                    "ANTHROPIC_API_KEY": "your_anthropic_api_key",
                    "ANTHROPIC_BASE_URL": "https://api.anthropic.com"
                }
            )
        }
    ]

    manager = ToolManager(server_configs)

    result = await manager.execute_tool_call(
        server_name="tool-vqa",
        tool_name="visual_question_answering",
        arguments={
            "image_path_or_url": "https://example.com/image.jpg",
            "question": "What is in this image?"
        }
    )
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
```

</details>

### Server: tool-vqa-os

Analyze images and answer questions about visual content using open-source compatible models.

**Tools**:

- 👁️ `visual_question_answering(image_path_or_url, question)`: Answer questions about images

**Environment Variables**:

- 🔑 `VISION_API_KEY`: API key (required)
- 🌐 `VISION_BASE_URL`: API endpoint URL (required)
- 🤖 `VISION_MODEL_NAME`: Model name (required)

**Example**:

<details>
<summary>Click to expand code example</summary>

```python
import asyncio
from miroflow_tools import ToolManager
from mcp import StdioServerParameters

async def main():
    server_configs = [
        {
            "name": "tool-vqa-os",
            "params": StdioServerParameters(
                command="python",
                args=["-m", "miroflow_tools.mcp_servers.vision_mcp_server_os"],
                env={
                    "VISION_API_KEY": "your_vision_api_key",
                    "VISION_BASE_URL": "your_vision_base_url",
                    "VISION_MODEL_NAME": "your_vision_model_name"
                }
            )
        }
    ]

    manager = ToolManager(server_configs)

    result = await manager.execute_tool_call(
        server_name="tool-vqa-os",
        tool_name="visual_question_answering",
        arguments={
            "image_path_or_url": "https://example.com/image.jpg",
            "question": "What is in this image?"
        }
    )
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
```

</details>

### Server: tool-transcribe

Transcribe audio files and answer questions about audio content using OpenAI Whisper.

**Tools**:

- 🎤 `audio_transcription(audio_path_or_url)`: Transcribe audio to text
- 🎧 `audio_question_answering(audio_path_or_url, question)`: Answer questions about audio

**Environment Variables**:

- 🔑 `OPENAI_API_KEY`: OpenAI API key (required)
- 🌐 `OPENAI_BASE_URL`: API base URL (default: `https://api.openai.com/v1`)

**Supported Formats**: 🎵 MP3, WAV, M4A, AAC, OGG, FLAC

**Example**:

<details>
<summary>Click to expand code example</summary>

```python
import asyncio
from miroflow_tools import ToolManager
from mcp import StdioServerParameters

async def main():
    server_configs = [
        {
            "name": "tool-transcribe",
            "params": StdioServerParameters(
                command="python",
                args=["-m", "miroflow_tools.mcp_servers.audio_mcp_server"],
                env={
                    "OPENAI_API_KEY": "your_openai_api_key",
                    "OPENAI_BASE_URL": "https://api.openai.com/v1"
                }
            )
        }
    ]

    manager = ToolManager(server_configs)

    # Transcribe audio
    result = await manager.execute_tool_call(
        server_name="tool-transcribe",
        tool_name="audio_transcription",
        arguments={"audio_path_or_url": "/path/to/audio.mp3"}
    )
    print(result)

    # Answer questions about audio
    result = await manager.execute_tool_call(
        server_name="tool-transcribe",
        tool_name="audio_question_answering",
        arguments={
            "audio_path_or_url": "/path/to/audio.mp3",
            "question": "What is the main topic discussed?"
        }
    )
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
```

</details>

### Server: tool-transcribe-os

Transcribe audio files using open-source compatible models.

**Tools**:

- 🎤 `audio_transcription(audio_path_or_url)`: Transcribe audio to text

**Environment Variables**:

- 🔑 `WHISPER_API_KEY`: API key (required)
- 🌐 `WHISPER_BASE_URL`: API endpoint URL (required)
- 🤖 `WHISPER_MODEL_NAME`: Model name (required)

**Supported Formats**: 🎵 MP3, WAV, M4A, AAC, OGG, FLAC

**Example**:

<details>
<summary>Click to expand code example</summary>

```python
import asyncio
from miroflow_tools import ToolManager
from mcp import StdioServerParameters

async def main():
    server_configs = [
        {
            "name": "tool-transcribe-os",
            "params": StdioServerParameters(
                command="python",
                args=["-m", "miroflow_tools.mcp_servers.audio_mcp_server_os"],
                env={
                    "WHISPER_API_KEY": "your_whisper_api_key",
                    "WHISPER_BASE_URL": "your_whisper_base_url",
                    "WHISPER_MODEL_NAME": "your_whisper_model_name"
                }
            )
        }
    ]

    manager = ToolManager(server_configs)

    result = await manager.execute_tool_call(
        server_name="tool-transcribe-os",
        tool_name="audio_transcription",
        arguments={"audio_path_or_url": "/path/to/audio.mp3"}
    )
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
```

</details>

### Server: tool-reading

Convert various document formats to Markdown using MarkItDown.

**Tools**:

- 📄 `convert_to_markdown(uri)`: Convert documents (PDF, DOC, PPT, Excel, CSV, ZIP, etc.) to Markdown. URI must start with `file:`, `data:`, `http:`, or `https:` scheme.

**Supported Formats**: 📄 PDF, DOC, DOCX, PPT, PPTX, XLS, XLSX, CSV, ZIP, and more

**Example**:

<details>
<summary>Click to expand code example</summary>

```python
import asyncio
from miroflow_tools import ToolManager
from mcp import StdioServerParameters

async def main():
    # Configure server (no additional environment variables required)
    server_configs = [
        {
            "name": "tool-reading",
            "params": StdioServerParameters(
                command="python",
                args=["-m", "miroflow_tools.mcp_servers.reading_mcp_server"]
            )
        }
    ]

    manager = ToolManager(server_configs)

    result = await manager.execute_tool_call(
        server_name="tool-reading",
        tool_name="convert_to_markdown",
        arguments={"uri": "file:///path/to/document.pdf"}
    )
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
```

</details>

### Server: tool-reasoning

Solve complex reasoning problems requiring chain-of-thought using Anthropic Claude with thinking.

**Tools**:

- 🧠 `reasoning(question)`: Solve hard math problems, puzzles, riddles, and IQ test questions

**Environment Variables**:

- 🔑 `ANTHROPIC_API_KEY`: Anthropic API key (required)
- 🌐 `ANTHROPIC_BASE_URL`: API base URL (default: `https://api.anthropic.com`)

**Example**:

<details>
<summary>Click to expand code example</summary>

```python
import asyncio
from miroflow_tools import ToolManager
from mcp import StdioServerParameters

async def main():
    server_configs = [
        {
            "name": "tool-reasoning",
            "params": StdioServerParameters(
                command="python",
                args=["-m", "miroflow_tools.mcp_servers.reasoning_mcp_server"],
                env={
                    "ANTHROPIC_API_KEY": "your_anthropic_api_key",
                    "ANTHROPIC_BASE_URL": "https://api.anthropic.com"
                }
            )
        }
    ]

    manager = ToolManager(server_configs)

    result = await manager.execute_tool_call(
        server_name="tool-reasoning",
        tool_name="reasoning",
        arguments={"question": "Solve: If a train travels 60 mph for 2 hours, then 80 mph for 1 hour, what's the average speed?"}
    )
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
```

</details>

### Server: tool-reasoning-os

Solve complex reasoning problems requiring chain-of-thought using open-source compatible models.

**Tools**:

- 🧠 `reasoning(question)`: Solve hard math problems, puzzles, riddles, and IQ test questions

**Environment Variables**:

- 🔑 `REASONING_API_KEY`: API key (required)
- 🌐 `REASONING_BASE_URL`: API endpoint URL (required)
- 🤖 `REASONING_MODEL_NAME`: Model name (required)

**Example**:

<details>
<summary>Click to expand code example</summary>

```python
import asyncio
from miroflow_tools import ToolManager
from mcp import StdioServerParameters

async def main():
    server_configs = [
        {
            "name": "tool-reasoning-os",
            "params": StdioServerParameters(
                command="python",
                args=["-m", "miroflow_tools.mcp_servers.reasoning_mcp_server_os"],
                env={
                    "REASONING_API_KEY": "your_reasoning_api_key",
                    "REASONING_BASE_URL": "your_reasoning_base_url",
                    "REASONING_MODEL_NAME": "your_reasoning_model_name"
                }
            )
        }
    ]

    manager = ToolManager(server_configs)

    result = await manager.execute_tool_call(
        server_name="tool-reasoning-os",
        tool_name="reasoning",
        arguments={"question": "Solve: If a train travels 60 mph for 2 hours, then 80 mph for 1 hour, what's the average speed?"}
    )
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
```

</details>

### Server: search_and_scrape_webpage

Google search via Serper API. Used in MiroThinker v1.0/v1.5 evaluation.

**Tools**:

- 🔍 `google_search(q, gl="us", hl="en", location=None, num=None, tbs=None, page=None, autocorrect=None)`: Perform web searches via Serper API and retrieve rich results

**Environment Variables**:

- 🔑 `SERPER_API_KEY`: Serper API key (required)
- 🌐 `SERPER_BASE_URL`: Serper API base URL (default: `https://google.serper.dev`)

**Example**:

<details>
<summary>Click to expand code example</summary>

```python
import asyncio
from miroflow_tools import ToolManager
from mcp import StdioServerParameters

async def main():
    server_configs = [
        {
            "name": "search_and_scrape_webpage",
            "params": StdioServerParameters(
                command="python",
                args=["-m", "miroflow_tools.dev_mcp_servers.search_and_scrape_webpage"],
                env={
                    "SERPER_API_KEY": "your_serper_api_key",
                    "SERPER_BASE_URL": "https://google.serper.dev"
                }
            )
        }
    ]

    manager = ToolManager(server_configs)

    result = await manager.execute_tool_call(
        server_name="search_and_scrape_webpage",
        tool_name="google_search",
        arguments={
            "q": "Python async programming",
            "gl": "us",
            "hl": "en",
            "num": 10
        }
    )
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
```

</details>

### Server: jina_scrape_llm_summary

Scrape content from URLs and extract meaningful information using an LLM. Used in MiroThinker v1.0/v1.5 evaluation.

**Tools**:

- 🔎 `scrape_and_extract_info(url, info_to_extract, custom_headers=None)`: Scrape content from a URL (web pages, PDFs, code files, etc.) and extract meaningful information using an LLM

**Environment Variables**:

- 🔑 `JINA_API_KEY`: Jina.ai API key (required)
- 🌐 `JINA_BASE_URL`: Jina.ai API base URL (default: `https://r.jina.ai`)
- 🔗 `SUMMARY_LLM_BASE_URL`: LLM API base URL for summarization (required)
- 🤖 `SUMMARY_LLM_MODEL_NAME`: LLM model name for summarization (required)
- 🔑 `SUMMARY_LLM_API_KEY`: LLM API key for summarization (optional, depends on LLM provider)

**Example**:

<details>
<summary>Click to expand code example</summary>

```python
import asyncio
from miroflow_tools import ToolManager
from mcp import StdioServerParameters

async def main():
    server_configs = [
        {
            "name": "jina_scrape_llm_summary",
            "params": StdioServerParameters(
                command="python",
                args=["-m", "miroflow_tools.dev_mcp_servers.jina_scrape_llm_summary"],
                env={
                    "JINA_API_KEY": "your_jina_api_key",
                    "JINA_BASE_URL": "https://r.jina.ai",
                    "SUMMARY_LLM_BASE_URL": "your_llm_base_url",
                    "SUMMARY_LLM_MODEL_NAME": "your_llm_model_name",
                    "SUMMARY_LLM_API_KEY": "your_llm_api_key"
                }
            )
        }
    ]

    manager = ToolManager(server_configs)

    result = await manager.execute_tool_call(
        server_name="jina_scrape_llm_summary",
        tool_name="scrape_and_extract_info",
        arguments={
            "url": "https://example.com/article",
            "info_to_extract": "What is the main topic of this article?"
        }
    )
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
```

</details>

### Server: tool-google-search

Google search via Serper API with website scraping capabilities.

**Tools**:

- 🔍 `google_search(q, gl="us", hl="en", location=None, num=10, tbs=None, page=1)`: Google search
- 🌐 `scrape_website(url)`: Scrape website content using Jina.ai

**Environment Variables**:

- 🔑 `SERPER_API_KEY`: Serper API key (required for Google search)
- 🌐 `SERPER_BASE_URL`: Serper API base URL (default: `https://google.serper.dev`)
- 🔑 `JINA_API_KEY`: Jina.ai API key (required for scraping)
- 🌐 `JINA_BASE_URL`: Jina.ai API base URL (default: `https://r.jina.ai`)

**Filtering Options** (via environment variables):

- 🚫 `REMOVE_SNIPPETS`: Remove snippets from search results
- 🚫 `REMOVE_KNOWLEDGE_GRAPH`: Remove knowledge graph from results
- 🚫 `REMOVE_ANSWER_BOX`: Remove answer box from results

**Example**:

<details>
<summary>Click to expand code example</summary>

```python
import asyncio
from miroflow_tools import ToolManager
from mcp import StdioServerParameters

async def main():
    server_configs = [
        {
            "name": "tool-google-search",
            "params": StdioServerParameters(
                command="python",
                args=["-m", "miroflow_tools.mcp_servers.searching_google_mcp_server"],
                env={
                    "SERPER_API_KEY": "your_serper_api_key",
                    "SERPER_BASE_URL": "https://google.serper.dev",
                    "JINA_API_KEY": "your_jina_api_key",
                    "JINA_BASE_URL": "https://r.jina.ai"
                }
            )
        }
    ]

    manager = ToolManager(server_configs)

    # Google search
    result = await manager.execute_tool_call(
        server_name="tool-google-search",
        tool_name="google_search",
        arguments={
            "q": "Python async programming",
            "gl": "us",
            "hl": "en",
            "num": 10
        }
    )
    print(result)

    # Scrape website
    result = await manager.execute_tool_call(
        server_name="tool-google-search",
        tool_name="scrape_website",
        arguments={"url": "https://example.com/article"}
    )
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
```

</details>

### Server: tool-sougou-search

Sougou search (optimized for Chinese) with website scraping capabilities. *Optional: Not used in the MiroThinker v1.0/v1.5 evaluation*

**Tools**:

- 🔍 `sougou_search(Query, Cnt=10)`: Sougou search (Chinese)
- 🌐 `scrape_website(url)`: Scrape website content using Jina.ai

**Environment Variables**:

- 🔑 `TENCENTCLOUD_SECRET_ID`: Tencent Cloud secret ID (required)
- 🔑 `TENCENTCLOUD_SECRET_KEY`: Tencent Cloud secret key (required)
- 🔑 `JINA_API_KEY`: Jina.ai API key (required for scraping)
- 🌐 `JINA_BASE_URL`: Jina.ai API base URL (default: `https://r.jina.ai`)

**Example**:

<details>
<summary>Click to expand code example</summary>

```python
import asyncio
from miroflow_tools import ToolManager
from mcp import StdioServerParameters

async def main():
    server_configs = [
        {
            "name": "tool-sougou-search",
            "params": StdioServerParameters(
                command="python",
                args=["-m", "miroflow_tools.mcp_servers.searching_sougou_mcp_server"],
                env={
                    "TENCENTCLOUD_SECRET_ID": "your_tencent_secret_id",
                    "TENCENTCLOUD_SECRET_KEY": "your_tencent_secret_key",
                    "JINA_API_KEY": "your_jina_api_key",
                    "JINA_BASE_URL": "https://r.jina.ai"
                }
            )
        }
    ]

    manager = ToolManager(server_configs)

    # Sougou search
    result = await manager.execute_tool_call(
        server_name="tool-sougou-search",
        tool_name="sougou_search",
        arguments={
            "Query": "Python 异步编程",
            "Cnt": 10
        }
    )
    print(result)

    # Scrape website
    result = await manager.execute_tool_call(
        server_name="tool-sougou-search",
        tool_name="scrape_website",
        arguments={"url": "https://example.com/article"}
    )
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
```

</details>

## 🚀 Development

### Adding a New MCP Server

1. Create a new server file in `mcp_servers/`
1. Use `FastMCP` to define tools:
   ```python
   from fastmcp import FastMCP
   mcp = FastMCP("server-name")

   @mcp.tool()
   async def my_tool(arg: str) -> str:
       """Tool description."""
       return "result"

   if __name__ == "__main__":
       mcp.run(transport="stdio")
   ```
1. Add server configuration to your application
1. Update this README with server documentation
