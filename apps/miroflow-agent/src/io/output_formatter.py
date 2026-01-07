# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

import re

from ..utils.prompt_utils import FORMAT_ERROR_MESSAGE


class OutputFormatter:
    def _extract_boxed_content(self, text: str) -> str:
        r"""
        Extract the content of the last \boxed{...} occurrence in the given text.
        Supports:
          - Arbitrary levels of nested braces
          - Escaped braces (\{ and \})
          - Whitespace between \boxed and the opening brace
          - Empty content inside braces
          - Incomplete boxed expressions (extracts to end of string as fallback)
        Returns an empty string if no match is found.
        """
        if not text:
            return ""

        _BOXED_RE = re.compile(r"\\boxed\b", re.DOTALL)

        last_result = None  # Track the last boxed content (complete or incomplete)
        i = 0
        n = len(text)

        while True:
            # Find the next \boxed occurrence
            m = _BOXED_RE.search(text, i)
            if not m:
                break
            j = m.end()

            # Skip any whitespace after \boxed
            while j < n and text[j].isspace():
                j += 1

            # Require that the next character is '{'
            if j >= n or text[j] != "{":
                i = j
                continue

            # Parse the brace content manually to handle nesting and escapes
            depth = 0
            k = j
            escaped = False
            found_closing = False
            while k < n:
                ch = text[k]
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    # When depth returns to zero, the boxed content ends
                    if depth == 0:
                        last_result = text[j + 1 : k]
                        i = k + 1
                        found_closing = True
                        break
                k += 1

            # If we didn't find a closing brace, this is an incomplete boxed
            # Store it as the last result (will be overwritten if we find more boxed later)
            if not found_closing and depth > 0:
                last_result = text[j + 1 : n]
                i = k  # Continue from where we stopped
            elif not found_closing:
                i = j + 1  # Move past this invalid boxed

        # Return the last boxed content found (complete or incomplete)
        black_list = ["?", "??", "???", "？", "……", "…", "...", "unknown", None]
        return last_result.strip() if last_result not in black_list else ""

    def format_tool_result_for_user(self, tool_call_execution_result):
        """
        Format tool execution results to be fed back to LLM as user messages.
        Only includes necessary information (results or errors).
        """
        server_name = tool_call_execution_result["server_name"]
        tool_name = tool_call_execution_result["tool_name"]

        if "error" in tool_call_execution_result:
            # Provide concise error information to LLM
            content = f"Tool call to {tool_name} on {server_name} failed. Error: {tool_call_execution_result['error']}"
        elif "result" in tool_call_execution_result:
            # Provide the original output result of the tool
            content = tool_call_execution_result["result"]
            # Consider truncating overly long results
            max_len = 100_000  # 100k chars = 25k tokens
            if len(content) > max_len:
                content = content[:max_len] + "\n... [Result truncated]"
        else:
            content = f"Tool call to {tool_name} on {server_name} completed, but produced no specific output or result."

        # Return format suitable as user message content
        # return [{"type": "text", "text": content}]
        return {"type": "text", "text": content}

    def format_final_summary_and_log(self, final_answer_text, client=None):
        """Format final summary information, including answers and token statistics"""
        summary_lines = []
        summary_lines.append("\n" + "=" * 30 + " Final Answer " + "=" * 30)
        summary_lines.append(final_answer_text)

        # Extract boxed result - find the last match using safer regex patterns
        boxed_result = self._extract_boxed_content(final_answer_text)

        # Add extracted result section
        summary_lines.append("\n" + "-" * 20 + " Extracted Result " + "-" * 20)

        if boxed_result:
            summary_lines.append(boxed_result)
        elif final_answer_text:
            summary_lines.append("No \\boxed{} content found.")
            boxed_result = FORMAT_ERROR_MESSAGE

        # Token usage statistics and cost estimation - use client method
        if client and hasattr(client, "format_token_usage_summary"):
            token_summary_lines, log_string = client.format_token_usage_summary()
            summary_lines.extend(token_summary_lines)
        else:
            # If no client or client doesn't support it, use default format
            summary_lines.append("\n" + "-" * 20 + " Token Usage & Cost " + "-" * 20)
            summary_lines.append("Token usage information not available.")
            summary_lines.append("-" * (40 + len(" Token Usage & Cost ")))
            log_string = "Token usage information not available."

        return "\n".join(summary_lines), boxed_result, log_string
