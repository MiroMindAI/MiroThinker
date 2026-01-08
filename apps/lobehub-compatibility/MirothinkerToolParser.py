"""
Tool parser plugin for vLLM for MiroThinker MCP format to compatible with the tool calling interface of openai.
MCP format:
    <use_mcp_tool>
        <server_name>server name</server_name>
        <tool_name>tool name</tool_name>
        <arguments>
        {...}
        </arguments>
    </use_mcp_tool>
"""
import json
from collections.abc import Sequence
import json_repair
import regex as re

from vllm.entrypoints.chat_utils import make_tool_call_id
from vllm.entrypoints.openai.protocol import (
    ChatCompletionRequest,
    DeltaFunctionCall,
    DeltaMessage,
    DeltaToolCall,
    ExtractedToolCallInformation,
    FunctionCall,
    ToolCall,
)
from vllm.entrypoints.openai.tool_parsers.abstract_tool_parser import (
    ToolParser,ToolParserManager
)
from vllm.logger import init_logger

logger = init_logger(__name__)


class MirothinkerToolParser(ToolParser):
    def __init__(self, tokenizer):
        super().__init__(tokenizer)
        
        # State tracking for streaming
        self.current_tool_name_sent: bool = False
        self.prev_tool_call_arr: list[dict] = []
        self.current_tool_id: int = -1
        self.streamed_args_for_tool: list[str] = []
        self.buffer: str = ""  # Buffer for potential tool call tags
        self._resolved_tool_name_cache: dict[tuple[str, str], str] = {}

        # Correctness-first streaming state (incremental state machine)
        self._stream_mode: str = "text"  # "text" | "tool"
        self._text_token_prefix: str = ""  # possible prefix of <use_mcp_tool>
        self._tool_end_token_prefix: str = ""  # possible prefix of </use_mcp_tool>
        self._tool_block_buffer: str = ""  # accumulates between <use_mcp_tool> and </use_mcp_tool>
        self._stream_tool_call_ids: list[str] = []
        
        # Token definitions
        self.tool_call_start_token: str = "<use_mcp_tool>"
        self.tool_call_end_token: str = "</use_mcp_tool>"
        
        # Regex patterns
        self.tool_call_regex = re.compile(
            r'<use_mcp_tool>\s*'
            r'<server_name>(.*?)</server_name>\s*'
            r'<tool_name>(.*?)</tool_name>\s*'
            r'<arguments>\s*(.*?)\s*</arguments>\s*'
            r'</use_mcp_tool>',
            re.DOTALL
        )
        
        # For streaming partial tool calls
        # IMPORTANT: Use GREEDY matching (.*) for arguments to capture all content
        # in streaming mode. We'll clean up </arguments> tag in the code if present.
        # The outer ()? makes the whole <arguments> section optional
        # The inner (.*) will match empty string if <arguments> exists but has no content yet
        self.partial_tool_regex = re.compile(
            r'<use_mcp_tool>\s*'
            r'(?:<server_name>(.*?)</server_name>\s*)?'
            r'(?:<tool_name>(.*?)</tool_name>\s*)?'
            r'(?:<arguments>(\s*.*))?',  # Move \s* inside capture group so empty match returns ""
            re.DOTALL
        )

        # For correctness-first parsing on COMPLETE tool blocks only
        self._complete_tool_block_regex = re.compile(
            r'<use_mcp_tool>\s*'
            r'(?:<server_name>(.*?)</server_name>\s*)?'
            r'(?:<tool_name>(.*?)</tool_name>\s*)?'
            r'(?:<arguments>\s*(.*?)\s*(?:</arguments>\s*)?)?'
            r'</use_mcp_tool>',
            re.DOTALL,
        )

    def _resolve_tool_name(self, server_name: str, tool_name: str, request: ChatCompletionRequest) -> str:
        """
        Resolve the actual tool name by combining server_name and tool_name
        if server_name is not 'default'.
        """
        if not server_name or server_name == "default":
            return tool_name
            
        if not request or not request.tools:
            return tool_name

        cache_key = (server_name, tool_name)
        cached = self._resolved_tool_name_cache.get(cache_key)
        if cached:
            return cached
            
        # Filter tools that contain server_name
        candidates = []
        for tool in request.tools:
            if hasattr(tool, "function") and hasattr(tool.function, "name"):
                name = tool.function.name
                if tool_name in name:
                    candidates.append(name)
        if len(candidates) == 1:
            resolved = candidates[0]
            self._resolved_tool_name_cache[cache_key] = resolved
            return resolved
        # Find match containing tool_name
        for candidate in candidates:
            if server_name in candidate:
                logger.debug("Resolved tool %s -> %s (server: %s)", tool_name, candidate, server_name)
                self._resolved_tool_name_cache[cache_key] = candidate
                return candidate
                
        return tool_name

    def adjust_request(self, request: ChatCompletionRequest) -> ChatCompletionRequest:
        request = super().adjust_request(request)
        if request.tools and request.tool_choice != "none":
            # Do not skip special tokens for proper tool parsing
            request.skip_special_tokens = False
        return request
    
    def _ensure_tool_id_valid(self, tool_id: int) -> bool:
        """Ensure the tool_id is valid and arrays have enough elements"""
        if tool_id < 0:
            return False
        
        # Ensure arrays are large enough
        while len(self.streamed_args_for_tool) <= tool_id:
            self.streamed_args_for_tool.append("")
        while len(self.prev_tool_call_arr) <= tool_id:
            self.prev_tool_call_arr.append({})
        
        return True

    def extract_tool_calls(
        self,
        model_output: str,
        request: ChatCompletionRequest,
    ) -> ExtractedToolCallInformation:
        # Sanity check; avoid unnecessary processing
        if logger.isEnabledFor(10):  # DEBUG
            logger.debug("model_output len=%s", len(model_output))
        if self.tool_call_start_token not in model_output or request.tool_choice == "none" or not request.tools:
            return ExtractedToolCallInformation(
                tools_called=False, tool_calls=[], content=model_output
            )
        
        try:
            tool_calls = []
            had_any_match = False
            had_parse_error = False
            # Find all complete tool calls
            for match in self.tool_call_regex.finditer(model_output):
                had_any_match = True
                server_name = match.group(1).strip()
                tool_name = match.group(2).strip()
                arguments_str = match.group(3).strip()
                
                # Resolve tool name
                tool_name = self._resolve_tool_name(server_name, tool_name, request)
                
                try:
                    # Parse arguments as JSON
                    arguments = json.loads(arguments_str)
                    
                    tool_call = ToolCall(
                        type="function",
                        function=FunctionCall(
                            name=tool_name,
                            arguments=json.dumps(arguments, ensure_ascii=False),
                        ),
                    )
                    tool_calls.append(tool_call)
                    
                except json.JSONDecodeError:
                    try:
                        repaired = json_repair.repair_json(arguments_str)
                        if not repaired:
                            had_parse_error = True
                            logger.warning(
                                "Failed to repair tool arguments JSON: %s", arguments_str
                            )
                            continue

                        arguments = json.loads(repaired)
                        tool_call = ToolCall(
                            type="function",
                            function=FunctionCall(
                                name=tool_name,
                                arguments=json.dumps(arguments, ensure_ascii=False),
                            ),
                        )
                        tool_calls.append(tool_call)
                    except Exception:
                        had_parse_error = True
                        logger.warning(
                            "Failed to parse tool arguments after repair: %s", arguments_str
                        )
                        continue
            
            # If we couldn't successfully parse tool calls (or format didn't match), do not truncate.
            # Return the full model output as content to avoid losing text.
            if had_parse_error or not tool_calls or not had_any_match:
                return ExtractedToolCallInformation(
                    tools_called=False, tool_calls=[], content=model_output
                )
            
            # Extract content before first tool call
            content = model_output[:model_output.find(self.tool_call_start_token)]
            
            return ExtractedToolCallInformation(
                tools_called=len(tool_calls) > 0,
                tool_calls=tool_calls,
                content=content if content else None,
            )
            
        except Exception:
            logger.exception("Error in extracting tool call from response.")
            return ExtractedToolCallInformation(
                tools_called=False, tool_calls=[], content=model_output
            )

    def extract_tool_calls_streaming(
        self,
        previous_text: str,
        current_text: str,
        delta_text: str,
        previous_token_ids: Sequence[int],
        current_token_ids: Sequence[int],
        delta_token_ids: Sequence[int],
        request: ChatCompletionRequest,
    ) -> DeltaMessage | None:     
        
        # Reset state if this is the start of a new request
        if not previous_text:
            self.current_tool_name_sent = False
            self.prev_tool_call_arr = []
            self.current_tool_id = -1
            self.streamed_args_for_tool = []
            self.buffer = ""
            self._resolved_tool_name_cache = {}

            self._stream_mode = "text"
            self._text_token_prefix = ""
            self._tool_end_token_prefix = ""
            self._tool_block_buffer = ""
            self._stream_tool_call_ids = []

        # If tools are disabled for this request, do not suppress tags or parse tool calls.
        # Flush any internal buffers as plain text so we never drop output.
        if request.tool_choice == "none" or not request.tools:
            out = ""
            if self.buffer:
                out += self.buffer
                self.buffer = ""
            if self._text_token_prefix:
                out += self._text_token_prefix
                self._text_token_prefix = ""
            if self._tool_block_buffer:
                out += self.tool_call_start_token + self._tool_block_buffer
                self._tool_block_buffer = ""
            if self._tool_end_token_prefix:
                out += self._tool_end_token_prefix
                self._tool_end_token_prefix = ""
            out += delta_text
            return DeltaMessage(content=out) if out else None

        def _longest_token_prefix_at_end(s: str, token: str) -> str:
            max_len = min(len(token) - 1, len(s))
            for i in range(max_len, 0, -1):
                if token.startswith(s[-i:]):
                    return s[-i:]
            return ""

        emitted_text_parts: list[str] = []
        emitted_tool_calls: list[DeltaToolCall] = []

        chunk = delta_text

        while chunk:
            if self._stream_mode == "text":
                if self._text_token_prefix:
                    chunk = self._text_token_prefix + chunk
                    self._text_token_prefix = ""

                start_idx = chunk.find(self.tool_call_start_token)
                if start_idx < 0:
                    prefix = _longest_token_prefix_at_end(chunk, self.tool_call_start_token)
                    if prefix:
                        safe = chunk[: -len(prefix)]
                        if safe:
                            emitted_text_parts.append(safe)
                        self._text_token_prefix = prefix
                    else:
                        emitted_text_parts.append(chunk)
                    break

                before = chunk[:start_idx]
                if before:
                    emitted_text_parts.append(before)
                chunk = chunk[start_idx + len(self.tool_call_start_token) :]
                self._stream_mode = "tool"
                self._tool_block_buffer = ""
                self._tool_end_token_prefix = ""
                continue

            # tool mode
            if self._tool_end_token_prefix:
                chunk = self._tool_end_token_prefix + chunk
                self._tool_end_token_prefix = ""

            end_idx = chunk.find(self.tool_call_end_token)
            if end_idx < 0:
                prefix = _longest_token_prefix_at_end(chunk, self.tool_call_end_token)
                if prefix:
                    self._tool_block_buffer += chunk[: -len(prefix)]
                    self._tool_end_token_prefix = prefix
                else:
                    self._tool_block_buffer += chunk
                break

            # Complete tool block
            self._tool_block_buffer += chunk[:end_idx]
            tool_block = (
                self.tool_call_start_token + self._tool_block_buffer + self.tool_call_end_token
            )
            remainder = chunk[end_idx + len(self.tool_call_end_token) :]

            # Reset tool buffers before parsing
            self._stream_mode = "text"
            self._tool_block_buffer = ""
            self._tool_end_token_prefix = ""

            try:
                m = self._complete_tool_block_regex.search(tool_block)
                if not m:
                    emitted_text_parts.append(tool_block)
                    chunk = remainder
                    continue

                server_name = (m.group(1) or "").strip()
                tool_name = (m.group(2) or "").strip()
                arguments_str = (m.group(3) or "").strip()
                
                if not tool_name:
                    emitted_text_parts.append(tool_block)
                    chunk = remainder
                    continue

                resolved_name = (
                    self._resolve_tool_name(server_name, tool_name, request)
                    if server_name
                    else tool_name
                )

                # Finalize arguments strictly at end of the block
                if not arguments_str:
                    arguments_json_str = "{}"
                else:
                    try:
                        arguments_obj = json.loads(arguments_str)
                    except Exception:
                        repaired = json_repair.repair_json(arguments_str)
                        if not repaired:
                            emitted_text_parts.append(tool_block)
                            chunk = remainder
                            continue
                        arguments_obj = json.loads(repaired)
                    arguments_json_str = json.dumps(arguments_obj, ensure_ascii=False)

                tool_index = len(self._stream_tool_call_ids)
                tool_call_id = make_tool_call_id()
                self._stream_tool_call_ids.append(tool_call_id)

                emitted_tool_calls.append(
                    DeltaToolCall(
                        index=tool_index,
                        type="function",
                        id=tool_call_id,
                        function=DeltaFunctionCall(
                            name=resolved_name,
                            arguments=arguments_json_str,
                        ).model_dump(exclude_none=True),
                    )
                )

            except Exception:
                logger.exception(
                    "Error parsing complete tool block in streaming; falling back to plain text."
                )
                emitted_text_parts.append(tool_block)

            chunk = remainder

        emitted_text = "".join(emitted_text_parts) if emitted_text_parts else None
        if emitted_text is not None and emitted_text == "":
            emitted_text = None
        if emitted_text is None and not emitted_tool_calls:
            return None
            
        # vLLM's DeltaMessage.tool_calls is validated as a list; do not pass None explicitly.
        if emitted_tool_calls:
            return DeltaMessage(content=emitted_text, tool_calls=emitted_tool_calls)
        return DeltaMessage(content=emitted_text)


# Register the tool parser to ToolParserManager
ToolParserManager.register_module(
    "mirothinker", True ,MirothinkerToolParser
)
