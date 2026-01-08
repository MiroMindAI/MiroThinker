# MiroThinker Tool Parser Plugin for vLLM

This plugin provides support for MiroThinker-style tool calling in vLLM. It allows models trained with the MiroThinker tool calling format (XML-based) to be served via vLLM's OpenAI-compatible API with proper tool parsing.

## Overview

The plugin consists of a custom `ToolParser` implementation that detects and parses XML tags in the model's output, converting them into standard OpenAI tool calls. It supports both streaming and non-streaming responses.

## Files

- **`MirothinkerToolParser.py`**: The Python implementation of the tool parser. It registers the parser name `mirothinker` with vLLM's `ToolParserManager`, [detail](https://docs.vllm.com.cn/en/latest/features/tool_calling/#quickstart).
- **`chat_template.jinja`**: A Jinja2 chat template that correctly formats the conversation history and injects tool definitions for the model.

## Tool Call Format

The parser expects the model to output tool calls in the following XML format(current mcp server format):

```xml
<use_mcp_tool>
    <server_name>default</server_name>
    <tool_name>server_name[SEP]tool_name</tool_name>
    <arguments>
    {
        "city": "Beijing",
        "unit": "celsius"
    }
    </arguments>
</use_mcp_tool>
```

The parser handles:
- Extraction of server name, tool name, and JSON arguments.
- Robust parsing of streaming output (partial tags).
- Auto-resolution of tool names if the `server_name` matches a prefix of available tools.

## Usage

To use this plugin with vLLM, you need to specify the plugin path, the parser name, and the chat template when starting the server.

### Command Line Arguments

- `--tool-parser-plugin /path/to/MirothinkerToolParser.py`: Loads the custom parser code.
- `--tool-call-parser mirothinker`: Activates the parser registered as `mirothinker`.
- `--chat-template /path/to/chat_template.jinja`: Uses the provided chat template.
- `--enable-auto-tool-choice`: Enables automatic tool choice handling.
- `--enable-log-requests and --enable-log-outputs `: Enable vllm log the input and output of model [pr](https://github.com/vllm-project/vllm/pull/20707)

### Example

See `serve_model_vllm.sh` for a complete example:

```bash
vllm serve /path/to/model \
    --served-model-name mirothinker \
    --port 8000 \
    --trust-remote-code \
    --chat-template ./chat_template.jinja \
    --tool-parser-plugin ./MirothinkerToolParser.py \
    --tool-call-parser mirothinker \
    --enable-auto-tool-choice \
```

## Requirements

- vLLM >= 0.11.0

