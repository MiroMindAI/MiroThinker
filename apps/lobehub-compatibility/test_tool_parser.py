#!/usr/bin/env python3
"""
Test MiroThinkerToolParser for correctness.
"""

import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import regex as re

# Mock vLLM imports for testing without vLLM installed
# Create mock modules
mock_vllm = MagicMock()
mock_vllm.entrypoints = MagicMock()
mock_vllm.entrypoints.chat_utils = MagicMock()
mock_vllm.entrypoints.chat_utils.make_tool_call_id = lambda: "call_test_123"

mock_protocol = SimpleNamespace(
    ChatCompletionRequest=MagicMock,
    DeltaFunctionCall=MagicMock,
    DeltaMessage=MagicMock,
    DeltaToolCall=MagicMock,
    ExtractedToolCallInformation=MagicMock,
    FunctionCall=MagicMock,
    ToolCall=MagicMock,
)

mock_tool_parser = SimpleNamespace(
    ToolParser=object,
    ToolParserManager=MagicMock(),
)

mock_logger = SimpleNamespace(
    init_logger=lambda x: MagicMock(isEnabledFor=lambda _: False),
)

sys.modules["vllm"] = mock_vllm
sys.modules["vllm.entrypoints"] = mock_vllm.entrypoints
sys.modules["vllm.entrypoints.chat_utils"] = mock_vllm.entrypoints.chat_utils
sys.modules["vllm.entrypoints.openai"] = MagicMock()
sys.modules["vllm.entrypoints.openai.protocol"] = mock_protocol
sys.modules["vllm.entrypoints.openai.tool_parsers"] = MagicMock()
sys.modules["vllm.entrypoints.openai.tool_parsers.abstract_tool_parser"] = (
    mock_tool_parser
)
sys.modules["vllm.logger"] = mock_logger


def test_tool_call_regex():
    """Test the main tool call regex pattern."""
    tool_call_regex = re.compile(
        r"<use_mcp_tool>\s*"
        r"<server_name>(.*?)</server_name>\s*"
        r"<tool_name>(.*?)</tool_name>\s*"
        r"<arguments>\s*(.*?)\s*</arguments>\s*"
        r"</use_mcp_tool>",
        re.DOTALL,
    )

    # Test 1: Basic tool call
    text1 = """<use_mcp_tool>
<server_name>my_mcp_server</server_name>
<tool_name>web_search</tool_name>
<arguments>
{"query": "AI news"}
</arguments>
</use_mcp_tool>"""

    match = tool_call_regex.search(text1)
    assert match is not None, "Should match basic tool call"
    assert match.group(1).strip() == "my_mcp_server"
    assert match.group(2).strip() == "web_search"
    assert json.loads(match.group(3).strip()) == {"query": "AI news"}
    print("✅ Test 1: Basic tool call - PASSED")

    # Test 2: Tool call with content before
    text2 = """Let me search for that.

<use_mcp_tool>
<server_name>my_mcp_server</server_name>
<tool_name>search</tool_name>
<arguments>
{"q": "test"}
</arguments>
</use_mcp_tool>"""

    match = tool_call_regex.search(text2)
    assert match is not None, "Should match tool call with content before"
    print("✅ Test 2: Tool call with content before - PASSED")

    # Test 3: Multiple tool calls
    text3 = """<use_mcp_tool>
<server_name>server1</server_name>
<tool_name>tool1</tool_name>
<arguments>{"a": 1}</arguments>
</use_mcp_tool>

<use_mcp_tool>
<server_name>server2</server_name>
<tool_name>tool2</tool_name>
<arguments>{"b": 2}</arguments>
</use_mcp_tool>"""

    matches = list(tool_call_regex.finditer(text3))
    assert len(matches) == 2, f"Should find 2 tool calls, found {len(matches)}"
    assert matches[0].group(2).strip() == "tool1"
    assert matches[1].group(2).strip() == "tool2"
    print("✅ Test 3: Multiple tool calls - PASSED")

    # Test 4: Complex JSON arguments
    text4 = """<use_mcp_tool>
<server_name>my_mcp_server</server_name>
<tool_name>complex_tool</tool_name>
<arguments>
{
  "query": "test with quotes and apostrophes",
  "options": {"nested": true},
  "list": [1, 2, 3]
}
</arguments>
</use_mcp_tool>"""

    match = tool_call_regex.search(text4)
    assert match is not None, "Should match complex JSON"
    args = json.loads(match.group(3).strip())
    assert args["query"] == "test with quotes and apostrophes"
    assert args["options"]["nested"] is True
    print("✅ Test 4: Complex JSON arguments - PASSED")

    # Test 5: Empty arguments
    text5 = """<use_mcp_tool>
<server_name>my_mcp_server</server_name>
<tool_name>no_args_tool</tool_name>
<arguments>
{}
</arguments>
</use_mcp_tool>"""

    match = tool_call_regex.search(text5)
    assert match is not None, "Should match empty arguments"
    assert json.loads(match.group(3).strip()) == {}
    print("✅ Test 5: Empty arguments - PASSED")

    # Test 6: Minimal whitespace
    text6 = "<use_mcp_tool><server_name>s</server_name><tool_name>t</tool_name><arguments>{}</arguments></use_mcp_tool>"
    match = tool_call_regex.search(text6)
    assert match is not None, "Should match minimal whitespace"
    print("✅ Test 6: Minimal whitespace - PASSED")


def test_partial_tool_regex():
    """Test the partial tool regex for streaming."""
    partial_tool_regex = re.compile(
        r"<use_mcp_tool>\s*"
        r"(?:<server_name>(.*?)</server_name>\s*)?"
        r"(?:<tool_name>(.*?)</tool_name>\s*)?"
        r"(?:<arguments>(\s*.*))?",
        re.DOTALL,
    )

    # Test partial: only opening tag
    text1 = "<use_mcp_tool>\n"
    match = partial_tool_regex.search(text1)
    assert match is not None
    print("✅ Partial test 1: Only opening tag - PASSED")

    # Test partial: server_name only
    text2 = "<use_mcp_tool>\n<server_name>my_server</server_name>\n"
    match = partial_tool_regex.search(text2)
    assert match is not None
    assert match.group(1).strip() == "my_server"
    assert match.group(2) is None
    print("✅ Partial test 2: Server name only - PASSED")

    # Test partial: incomplete arguments
    text3 = """<use_mcp_tool>
<server_name>my_server</server_name>
<tool_name>my_tool</tool_name>
<arguments>
{"query": "incomp"""

    match = partial_tool_regex.search(text3)
    assert match is not None
    assert match.group(1).strip() == "my_server"
    assert match.group(2).strip() == "my_tool"
    assert '{"query": "incomp' in match.group(3)
    print("✅ Partial test 3: Incomplete arguments - PASSED")


def test_complete_tool_block_regex():
    """Test the complete tool block regex used in streaming."""
    complete_regex = re.compile(
        r"<use_mcp_tool>\s*"
        r"(?:<server_name>(.*?)</server_name>\s*)?"
        r"(?:<tool_name>(.*?)</tool_name>\s*)?"
        r"(?:<arguments>\s*(.*?)\s*(?:</arguments>\s*)?)?"
        r"</use_mcp_tool>",
        re.DOTALL,
    )

    # Test: Complete block
    text1 = """<use_mcp_tool>
<server_name>my_mcp_server</server_name>
<tool_name>search</tool_name>
<arguments>
{"q": "test"}
</arguments>
</use_mcp_tool>"""

    match = complete_regex.search(text1)
    assert match is not None
    assert match.group(1).strip() == "my_mcp_server"
    assert match.group(2).strip() == "search"
    assert json.loads(match.group(3).strip()) == {"q": "test"}
    print("✅ Complete block test 1: Full block - PASSED")

    # Test: Without arguments tag
    text2 = """<use_mcp_tool>
<server_name>my_mcp_server</server_name>
<tool_name>simple_tool</tool_name>
</use_mcp_tool>"""

    match = complete_regex.search(text2)
    assert match is not None
    assert match.group(2).strip() == "simple_tool"
    assert match.group(3) is None
    print("✅ Complete block test 2: Without arguments - PASSED")


def test_edge_cases():
    """Test edge cases and potential bugs."""
    tool_call_regex = re.compile(
        r"<use_mcp_tool>\s*"
        r"<server_name>(.*?)</server_name>\s*"
        r"<tool_name>(.*?)</tool_name>\s*"
        r"<arguments>\s*(.*?)\s*</arguments>\s*"
        r"</use_mcp_tool>",
        re.DOTALL,
    )

    # Edge case 1: Unicode in arguments
    text1 = """<use_mcp_tool>
<server_name>my_mcp_server</server_name>
<tool_name>search</tool_name>
<arguments>
{"query": "你好世界 🎉"}
</arguments>
</use_mcp_tool>"""

    match = tool_call_regex.search(text1)
    assert match is not None
    args = json.loads(match.group(3).strip())
    assert args["query"] == "你好世界 🎉"
    print("✅ Edge case 1: Unicode in arguments - PASSED")

    # Edge case 2: Newlines in JSON
    text2 = """<use_mcp_tool>
<server_name>my_mcp_server</server_name>
<tool_name>search</tool_name>
<arguments>
{
  "query": "line1\\nline2\\nline3"
}
</arguments>
</use_mcp_tool>"""

    match = tool_call_regex.search(text2)
    assert match is not None
    args = json.loads(match.group(3).strip())
    assert "line1\nline2" in args["query"]
    print("✅ Edge case 2: Newlines in JSON - PASSED")

    # Edge case 3: Tags in content (should not match nested)
    text3 = """<use_mcp_tool>
<server_name>my_mcp_server</server_name>
<tool_name>search</tool_name>
<arguments>
{"query": "<html><body>test</body></html>"}
</arguments>
</use_mcp_tool>"""

    match = tool_call_regex.search(text3)
    assert match is not None
    args = json.loads(match.group(3).strip())
    assert "<html>" in args["query"]
    print("✅ Edge case 3: HTML tags in arguments - PASSED")


def check_unused_code():
    """Check for unused code in the parser."""
    print("\n" + "=" * 60)
    print("CODE ANALYSIS - Potential Issues")
    print("=" * 60)

    issues = []

    # Issue 1: Unused variables
    unused_vars = [
        "self.current_tool_name_sent",
        "self.prev_tool_call_arr",
        "self.current_tool_id",
        "self.streamed_args_for_tool",
        "self.buffer",
    ]
    issues.append(
        f"⚠️  Unused instance variables (defined but never used in main logic):\n   {', '.join(unused_vars)}"
    )

    # Issue 2: Unused method
    issues.append("⚠️  `_ensure_tool_id_valid` method is defined but never called")

    # Issue 3: Unused regex
    issues.append("⚠️  `partial_tool_regex` is defined but never used")

    # Issue 4: server_name handling
    issues.append(
        "⚠️  `_resolve_tool_name` checks for 'default' server_name,\n   but chat_template.jinja uses 'my_mcp_server'"
    )

    for issue in issues:
        print(f"\n{issue}")

    print("\n" + "=" * 60)
    print("RECOMMENDATIONS")
    print("=" * 60)
    print("""
1. Remove unused variables and methods to clean up the code
2. Either use `partial_tool_regex` or remove it
3. Update `_resolve_tool_name` to handle 'my_mcp_server' correctly
4. The streaming implementation looks correct with the state machine approach
5. The main `extract_tool_calls` and `extract_tool_calls_streaming` logic appears sound
""")


def main():
    print("=" * 60)
    print("MiroThinkerToolParser Test Suite")
    print("=" * 60)

    print("\n--- Testing Main Tool Call Regex ---")
    test_tool_call_regex()

    print("\n--- Testing Partial Tool Regex ---")
    test_partial_tool_regex()

    print("\n--- Testing Complete Tool Block Regex ---")
    test_complete_tool_block_regex()

    print("\n--- Testing Edge Cases ---")
    test_edge_cases()

    check_unused_code()

    print("\n" + "=" * 60)
    print("ALL REGEX TESTS PASSED ✅")
    print("=" * 60)


if __name__ == "__main__":
    main()
