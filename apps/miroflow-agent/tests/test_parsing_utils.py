# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

"""
Unit tests for parsing utilities.

Tests for:
- filter_none_values
- safe_json_loads
- _fix_backslash_escapes
- extract_llm_response_text
"""

import pytest
from src.utils.parsing_utils import (
    filter_none_values,
    safe_json_loads,
    _fix_backslash_escapes,
)


class TestFilterNoneValues:
    """Tests for filter_none_values function."""

    def test_filter_none_values_basic(self):
        """Test filtering None values from a dictionary."""
        input_dict = {"a": 1, "b": None, "c": 3}
        result = filter_none_values(input_dict)
        assert result == {"a": 1, "c": 3}

    def test_filter_none_values_all_none(self):
        """Test filtering when all values are None."""
        input_dict = {"a": None, "b": None}
        result = filter_none_values(input_dict)
        assert result == {}

    def test_filter_none_values_no_none(self):
        """Test filtering when no values are None."""
        input_dict = {"a": 1, "b": 2, "c": 3}
        result = filter_none_values(input_dict)
        assert result == input_dict

    def test_filter_none_values_empty_dict(self):
        """Test filtering an empty dictionary."""
        result = filter_none_values({})
        assert result == {}

    def test_filter_none_values_non_dict(self):
        """Test that non-dict values are returned unchanged."""
        assert filter_none_values("string") == "string"
        assert filter_none_values(123) == 123
        assert filter_none_values([1, 2, 3]) == [1, 2, 3]
        assert filter_none_values(None) is None

    def test_filter_none_values_nested(self):
        """Test that nested structures are preserved."""
        input_dict = {"a": {"nested": None}, "b": [1, None, 3]}
        result = filter_none_values(input_dict)
        assert result == {"a": {"nested": None}, "b": [1, None, 3]}


class TestFixBackslashEscapes:
    """Tests for _fix_backslash_escapes function."""

    def test_fix_windows_path(self):
        """Test fixing Windows paths with backslashes."""
        json_str = r'{"path": "C:\Users\test"}'
        result = _fix_backslash_escapes(json_str)
        # Should escape the backslashes before uppercase letters
        assert r"\\" in result

    def test_fix_backslash_before_digit(self):
        """Test fixing backslashes before digits."""
        json_str = r'{"value": "\1\2\3"}'
        result = _fix_backslash_escapes(json_str)
        assert r"\\" in result

    def test_preserve_valid_escapes(self):
        """Test that valid escape sequences are preserved."""
        json_str = r'{"text": "line1\nline2\ttab"}'
        result = _fix_backslash_escapes(json_str)
        # Should not modify valid escape sequences
        assert "\\n" in result and "\\t" in result

    def test_empty_string(self):
        """Test handling empty string."""
        result = _fix_backslash_escapes("")
        assert result == ""


class TestSafeJsonLoads:
    """Tests for safe_json_loads function."""

    def test_valid_json(self):
        """Test parsing valid JSON string."""
        json_str = '{"name": "test", "value": 123}'
        result = safe_json_loads(json_str)
        assert result == {"name": "test", "value": 123}

    def test_invalid_json_repair(self):
        """Test that invalid JSON is repaired when possible."""
        # Missing closing brace - json_repair should fix it
        json_str = '{"name": "test"'
        result = safe_json_loads(json_str)
        assert isinstance(result, dict)

    def test_empty_json(self):
        """Test parsing empty JSON object."""
        result = safe_json_loads("{}")
        assert result == {}

    def test_json_with_escaped_chars(self):
        """Test parsing JSON with escaped characters."""
        json_str = '{"text": "line1\\nline2"}'
        result = safe_json_loads(json_str)
        assert result["text"] == "line1\nline2"

    def test_json_with_nested_structure(self):
        """Test parsing nested JSON."""
        json_str = '{"outer": {"inner": {"value": 1}}}'
        result = safe_json_loads(json_str)
        assert result["outer"]["inner"]["value"] == 1

    def test_json_with_list(self):
        """Test parsing JSON with list."""
        json_str = '{"items": [1, 2, 3]}'
        result = safe_json_loads(json_str)
        assert result["items"] == [1, 2, 3]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])