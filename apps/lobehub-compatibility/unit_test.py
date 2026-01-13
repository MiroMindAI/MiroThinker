#!/usr/bin/env python3
"""
Unit tests for MiroThinker chat template.

Run with: pytest unit_test.py -v
"""

from datetime import datetime
from pathlib import Path

import pytest
from jinja2 import BaseLoader, Environment

# ============================================================================
# Fixtures
# ============================================================================


def strftime_now(format_str: str) -> str:
    """Simulate vLLM's strftime_now function."""
    return datetime.now().strftime(format_str)


@pytest.fixture
def template():
    """Load the chat template."""
    template_path = Path(__file__).parent / "chat_template.jinja"
    with open(template_path, "r") as f:
        template_str = f.read()

    env = Environment(loader=BaseLoader())
    env.globals["strftime_now"] = strftime_now
    return env.from_string(template_str)


@pytest.fixture
def today_date():
    """Get today's date in YYYY-MM-DD format."""
    return datetime.now().strftime("%Y-%m-%d")


# ============================================================================
# Test: Basic Message Formatting
# ============================================================================


class TestBasicMessageFormatting:
    """Tests for basic message formatting without tools."""

    def test_user_message_format(self, template):
        """User message should be wrapped in <|im_start|>user ... <|im_end|>."""
        messages = [{"role": "user", "content": "Hello!"}]
        result = template.render(messages=messages, add_generation_prompt=False)

        assert "<|im_start|>user\nHello!<|im_end|>" in result

    def test_system_message_format(self, template):
        """System message should be wrapped correctly."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hi"},
        ]
        result = template.render(messages=messages, add_generation_prompt=False)

        assert "<|im_start|>system\nYou are helpful.<|im_end|>" in result

    def test_assistant_message_format(self, template):
        """Assistant message should be wrapped correctly with <think> tags."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        result = template.render(messages=messages, add_generation_prompt=False)

        # Assistant always outputs <think> tags (even if empty)
        assert (
            "<|im_start|>assistant\n<think>\n\n</think>\n\nHi there!<|im_end|>"
            in result
        )

    def test_add_generation_prompt(self, template):
        """add_generation_prompt should add <|im_start|>assistant at the end."""
        messages = [{"role": "user", "content": "Hello"}]
        result = template.render(messages=messages, add_generation_prompt=True)

        assert result.endswith("<|im_start|>assistant\n")

    def test_multi_turn_conversation(self, template):
        """Multi-turn conversation should maintain correct order."""
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "User 1"},
            {"role": "assistant", "content": "Assistant 1"},
            {"role": "user", "content": "User 2"},
        ]
        result = template.render(messages=messages, add_generation_prompt=True)

        # Check order
        sys_pos = result.find("System prompt")
        user1_pos = result.find("User 1")
        asst1_pos = result.find("Assistant 1")
        user2_pos = result.find("User 2")

        assert sys_pos < user1_pos < asst1_pos < user2_pos


# ============================================================================
# Test: Thinking/Reasoning Content
# ============================================================================


class TestThinkingContent:
    """Tests for <think> tag handling."""

    def test_reasoning_content_field(self, template):
        """reasoning_content field should be wrapped in <think> tags."""
        messages = [
            {"role": "user", "content": "What is 2+2?"},
            {
                "role": "assistant",
                "content": "The answer is 4.",
                "reasoning_content": "2+2=4 by basic arithmetic.",
            },
        ]
        result = template.render(messages=messages, add_generation_prompt=False)

        assert "<think>\n2+2=4 by basic arithmetic.\n</think>" in result
        assert "The answer is 4." in result

    def test_think_tags_in_content(self, template):
        """<think> tags in content should be extracted and reformatted."""
        messages = [
            {"role": "user", "content": "Question"},
            {
                "role": "assistant",
                "content": "<think>\nMy reasoning here.\n</think>\n\nMy answer here.",
            },
        ]
        result = template.render(messages=messages, add_generation_prompt=False)

        assert "<think>\nMy reasoning here.\n</think>" in result
        assert "My answer here." in result

    def test_think_preserved_in_history(self, template):
        """Think tags should be preserved in historical messages, not removed."""
        messages = [
            {"role": "user", "content": "First question"},
            {
                "role": "assistant",
                "content": "First answer",
                "reasoning_content": "First reasoning",
            },
            {"role": "user", "content": "Second question"},
        ]
        result = template.render(messages=messages, add_generation_prompt=True)

        # Historical thinking should be present
        assert "<think>\nFirst reasoning\n</think>" in result

    def test_enable_thinking_false(self, template):
        """enable_thinking=false should output empty think tags."""
        messages = [{"role": "user", "content": "Hello"}]
        result = template.render(
            messages=messages, add_generation_prompt=True, enable_thinking=False
        )

        assert result.endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n")

    def test_enable_thinking_true(self, template):
        """enable_thinking=true should not output empty think tags."""
        messages = [{"role": "user", "content": "Hello"}]
        result = template.render(
            messages=messages, add_generation_prompt=True, enable_thinking=True
        )

        assert result.endswith("<|im_start|>assistant\n")
        assert "<think>\n\n</think>" not in result


# ============================================================================
# Test: Tool Definitions in System Prompt
# ============================================================================


class TestToolDefinitions:
    """Tests for tool definition formatting in system prompt."""

    def test_tools_trigger_system_prompt(self, template, today_date):
        """When tools are provided, a special system prompt should be generated."""
        messages = [{"role": "user", "content": "Search something"}]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        result = template.render(
            messages=messages, tools=tools, add_generation_prompt=True
        )

        assert "In this environment you have access to a set of tools" in result
        assert f"Today is: {today_date}" in result
        assert "# Tool-Use Formatting Instructions" in result

    def test_tool_name_format(self, template):
        """Tool should be formatted with ### Tool name: header."""
        messages = [{"role": "user", "content": "Test"}]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "my_tool",
                    "description": "My description",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        result = template.render(
            messages=messages, tools=tools, add_generation_prompt=True
        )

        assert "### Tool name: my_tool" in result

    def test_tool_server_name(self, template):
        """Tool server should be my_mcp_server."""
        messages = [{"role": "user", "content": "Test"}]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "Test",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        result = template.render(
            messages=messages, tools=tools, add_generation_prompt=True
        )

        assert "## Server name: default" in result

    def test_tool_description_indentation(self, template):
        """Tool description should be indented with 4 spaces."""
        messages = [{"role": "user", "content": "Test"}]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "My tool description",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        result = template.render(
            messages=messages, tools=tools, add_generation_prompt=True
        )

        assert "Description:\n    My tool description" in result

    def test_tool_args_auto_generated(self, template):
        """Args section should be auto-generated from parameters.properties."""
        messages = [{"role": "user", "content": "Test"}]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search function",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                            "limit": {"type": "integer", "description": "Max results"},
                        },
                    },
                },
            }
        ]
        result = template.render(
            messages=messages, tools=tools, add_generation_prompt=True
        )

        assert "Args:" in result
        assert "query: Search query" in result
        assert "limit: Max results" in result

    def test_tool_args_not_duplicated(self, template):
        """If description already has Args:, don't add another."""
        messages = [{"role": "user", "content": "Test"}]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search function\n\nArgs:\n    query: The query",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"}
                        },
                    },
                },
            }
        ]
        result = template.render(
            messages=messages, tools=tools, add_generation_prompt=True
        )

        # Should only have one Args: section
        assert result.count("Args:") == 1

    def test_tool_json_schema_included(self, template):
        """Input JSON schema should be included."""
        messages = [{"role": "user", "content": "Test"}]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "test",
                    "description": "Test",
                    "parameters": {
                        "type": "object",
                        "properties": {"x": {"type": "string"}},
                    },
                },
            }
        ]
        result = template.render(
            messages=messages, tools=tools, add_generation_prompt=True
        )

        assert "Input JSON schema:" in result
        assert '"type": "object"' in result or '"type":"object"' in result

    def test_tool_without_function_wrapper(self, template):
        """Tools can be passed without the function wrapper."""
        messages = [{"role": "user", "content": "Test"}]
        tools = [
            {
                "name": "direct_tool",
                "description": "Direct tool format",
                "parameters": {"type": "object", "properties": {}},
            }
        ]
        result = template.render(
            messages=messages, tools=tools, add_generation_prompt=True
        )

        assert "### Tool name: direct_tool" in result

    def test_tool_none_description(self, template):
        """Tool with None description should not crash."""
        messages = [{"role": "user", "content": "Test"}]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "test",
                    "description": None,
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        # Should not raise an exception
        result = template.render(
            messages=messages, tools=tools, add_generation_prompt=True
        )
        assert "### Tool name: test" in result

    def test_tool_empty_description(self, template):
        """Tool with empty description should not crash."""
        messages = [{"role": "user", "content": "Test"}]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "test",
                    "description": "",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        result = template.render(
            messages=messages, tools=tools, add_generation_prompt=True
        )
        assert "### Tool name: test" in result

    def test_system_message_prepended_with_tools(self, template):
        """Custom system message should be prepended when tools are present."""
        messages = [
            {"role": "system", "content": "You are MiroThinker."},
            {"role": "user", "content": "Hi"},
        ]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "test",
                    "description": "Test",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        result = template.render(
            messages=messages, tools=tools, add_generation_prompt=True
        )

        # System message should come first, then tool instructions
        sys_idx = result.find("You are MiroThinker.")
        tools_idx = result.find("In this environment you have access")
        assert sys_idx < tools_idx


# ============================================================================
# Test: Tool Calls in Assistant Messages
# ============================================================================


class TestToolCalls:
    """Tests for tool call formatting in assistant messages."""

    def test_tool_call_format(self, template):
        """Tool calls should be formatted with <use_mcp_tool> tags."""
        messages = [
            {"role": "user", "content": "Search for AI"},
            {
                "role": "assistant",
                "content": "Let me search.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "web_search",
                            "arguments": '{"query": "AI news"}',
                        },
                    }
                ],
            },
        ]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        result = template.render(
            messages=messages, tools=tools, add_generation_prompt=False
        )

        assert "<use_mcp_tool>" in result
        assert "<server_name>default</server_name>" in result
        assert "<tool_name>web_search</tool_name>" in result
        assert "<arguments>" in result
        assert '{"query": "AI news"}' in result
        assert "</arguments>" in result
        assert "</use_mcp_tool>" in result

    def test_tool_call_no_content(self, template):
        """Tool call with None content should work."""
        messages = [
            {"role": "user", "content": "Search"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "search",
                            "arguments": '{"q": "test"}',
                        },
                    }
                ],
            },
        ]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        result = template.render(
            messages=messages, tools=tools, add_generation_prompt=False
        )

        # Should have tool call with empty think tags (no content before tool call)
        assert "<|im_start|>assistant\n<think>\n\n</think>\n\n<use_mcp_tool>" in result

    def test_multiple_tool_calls(self, template):
        """Multiple tool calls should be separated by newlines."""
        messages = [
            {"role": "user", "content": "Compare Tokyo and Osaka"},
            {
                "role": "assistant",
                "content": "I'll search both.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "search",
                            "arguments": '{"q": "Tokyo"}',
                        },
                    },
                    {
                        "id": "call_2",
                        "function": {
                            "name": "search",
                            "arguments": '{"q": "Osaka"}',
                        },
                    },
                ],
            },
        ]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        result = template.render(
            messages=messages, tools=tools, add_generation_prompt=False
        )

        # Extract assistant message part (after the last <|im_start|>assistant)
        assistant_start = result.rfind("<|im_start|>assistant")
        assistant_part = result[assistant_start:]

        # Should have two tool calls in assistant message
        assert assistant_part.count("<use_mcp_tool>") == 2
        assert assistant_part.count("</use_mcp_tool>") == 2

    def test_tool_call_arguments_dict(self, template):
        """Tool call with dict arguments should be JSON serialized."""
        messages = [
            {"role": "user", "content": "Search"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "search",
                            "arguments": {"q": "test", "limit": 5},  # dict, not string
                        },
                    }
                ],
            },
        ]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        result = template.render(
            messages=messages, tools=tools, add_generation_prompt=False
        )

        # Arguments should be JSON serialized
        assert "<arguments>" in result
        assert '"q"' in result or "'q'" in result


# ============================================================================
# Test: Tool Responses
# ============================================================================


class TestToolResponses:
    """Tests for tool response handling."""

    def test_tool_response_in_user_message(self, template):
        """Tool response should be embedded in a user message."""
        messages = [
            {"role": "user", "content": "Search"},
            {
                "role": "assistant",
                "content": "Searching...",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {"name": "search", "arguments": '{"q": "test"}'},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": "Search results here",
            },
        ]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        result = template.render(
            messages=messages, tools=tools, add_generation_prompt=True
        )

        # Tool response should be in a user message
        assert "<|im_start|>user\nSearch results here<|im_end|>" in result

    def test_multiple_tool_responses_merged(self, template):
        """Multiple consecutive tool responses should be merged into one user message."""
        messages = [
            {"role": "user", "content": "Compare"},
            {
                "role": "assistant",
                "content": "Searching...",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {"name": "search", "arguments": '{"q": "A"}'},
                    },
                    {
                        "id": "call_2",
                        "function": {"name": "search", "arguments": '{"q": "B"}'},
                    },
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "Result A"},
            {"role": "tool", "tool_call_id": "call_2", "content": "Result B"},
        ]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        result = template.render(
            messages=messages, tools=tools, add_generation_prompt=True
        )

        # Should have only one user message containing both results
        # Results should be separated by \n\n
        assert "Result A\n\nResult B" in result

        # Count im_start|>user - should have 2 (original user + tool results)
        user_count = result.count("<|im_start|>user")
        assert user_count == 2

    def test_tool_response_no_wrapper_tags(self, template):
        """Tool responses should NOT be wrapped in <tool_response> tags."""
        messages = [
            {"role": "user", "content": "Search"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {"name": "search", "arguments": '{"q": "test"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "Results"},
        ]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        result = template.render(
            messages=messages, tools=tools, add_generation_prompt=True
        )

        assert "<tool_response>" not in result
        assert "</tool_response>" not in result


# ============================================================================
# Test: Edge Cases
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_only_system_message(self, template):
        """Only system message should work."""
        messages = [{"role": "system", "content": "You are helpful."}]
        result = template.render(messages=messages, add_generation_prompt=False)
        assert "<|im_start|>system\nYou are helpful.<|im_end|>" in result

    def test_assistant_empty_content(self, template):
        """Assistant with empty string content should work."""
        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": ""},
        ]
        result = template.render(messages=messages, add_generation_prompt=False)
        # Assistant always outputs <think> tags (even with empty content)
        assert "<|im_start|>assistant\n<think>\n\n</think>\n\n<|im_end|>" in result

    def test_unicode_content(self, template):
        """Unicode content should be preserved."""
        messages = [
            {"role": "user", "content": "你好！🎉"},
            {"role": "assistant", "content": "こんにちは！"},
        ]
        result = template.render(messages=messages, add_generation_prompt=False)
        assert "你好！🎉" in result
        assert "こんにちは！" in result

    def test_special_characters_in_content(self, template):
        """Special characters should be preserved."""
        messages = [
            {"role": "user", "content": "Test <tag> & \"quotes\" 'apostrophe'"},
        ]
        result = template.render(messages=messages, add_generation_prompt=False)
        assert '<tag> & "quotes"' in result

    def test_newlines_preserved(self, template):
        """Newlines in content should be preserved."""
        messages = [
            {"role": "user", "content": "Line 1\nLine 2\n\nLine 4"},
        ]
        result = template.render(messages=messages, add_generation_prompt=False)
        assert "Line 1\nLine 2\n\nLine 4" in result


# ============================================================================
# Test: Complete Flow
# ============================================================================


class TestCompleteFlow:
    """Integration tests for complete conversation flows."""

    def test_full_tool_use_flow(self, template, today_date):
        """Test a complete tool use flow."""
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What's the weather?"},
            {
                "role": "assistant",
                "content": "Let me check.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "weather",
                            "arguments": '{"city": "Tokyo"}',
                        },
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "Sunny, 25°C"},
            {
                "role": "assistant",
                "content": "It's sunny and 25°C in Tokyo!",
            },
            {"role": "user", "content": "Thanks!"},
        ]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "weather",
                    "description": "Get weather info",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "city": {"type": "string", "description": "City name"}
                        },
                    },
                },
            }
        ]
        result = template.render(
            messages=messages, tools=tools, add_generation_prompt=True
        )

        # Check structure
        assert "<|im_start|>system" in result
        assert "You are a helpful assistant." in result
        assert f"Today is: {today_date}" in result
        assert "### Tool name: weather" in result
        assert "<use_mcp_tool>" in result
        assert "<server_name>default</server_name>" in result
        assert "Sunny, 25°C" in result
        assert "It's sunny and 25°C in Tokyo!" in result
        assert result.endswith("<|im_start|>assistant\n")

    def test_reasoning_with_tool_use(self, template):
        """Test reasoning content combined with tool use."""
        messages = [
            {"role": "user", "content": "Search for Python tutorials"},
            {
                "role": "assistant",
                "content": "I'll search for Python tutorials.",
                "reasoning_content": "User wants Python tutorials. I should use web search.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "search",
                            "arguments": '{"q": "Python tutorials"}',
                        },
                    }
                ],
            },
        ]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        result = template.render(
            messages=messages, tools=tools, add_generation_prompt=False
        )

        # Should have both thinking and tool call
        assert "<think>" in result
        assert "User wants Python tutorials" in result
        assert "</think>" in result
        assert "<use_mcp_tool>" in result


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
