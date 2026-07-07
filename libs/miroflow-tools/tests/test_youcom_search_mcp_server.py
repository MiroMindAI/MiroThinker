"""Unit tests for the You.com MCP server tools.

Tests input validation and error-handling without real HTTP calls.
Mocks out mcp/fastmcp/tenacity since those packages aren't installed
in the test environment.
"""

import json
import os
import sys
import types
from unittest.mock import patch, MagicMock

# --- Mock heavy dependencies before importing the target module ---

# mcp.server.fastmcp.FastMCP
_mcp_mod = types.ModuleType("mcp")
_mcp_server_mod = types.ModuleType("mcp.server")
_mcp_fastmcp_mod = types.ModuleType("mcp.server.fastmcp")
class _FakeFastMCP:
    def __init__(self, name=""):
        self.name = name
    def tool(self, *a, **kw):
        def deco(fn):
            return fn
        return deco
    def run(self):
        pass
_mcp_fastmcp_mod.FastMCP = _FakeFastMCP
sys.modules["mcp"] = _mcp_mod
sys.modules["mcp.server"] = _mcp_server_mod
sys.modules["mcp.server.fastmcp"] = _mcp_fastmcp_mod

# tenacity
_tenacity_mod = types.ModuleType("tenacity")
def _identity_retry(*a, **kw):
    def deco(fn):
        return fn
    return deco
class _Stop:
    @staticmethod
    def after_attempt(n): return lambda *a, **kw: None
class _Wait:
    @staticmethod
    def exponential(**kw): return lambda *a, **kw: None
class _Retry:
    @staticmethod
    def retry_if_exception_type(*a, **kw): return lambda *a, **kw: None
_tenacity_mod.retry = _identity_retry
_tenacity_mod.stop_after_attempt = _Stop.after_attempt
_tenacity_mod.wait_exponential = _Wait.exponential
_tenacity_mod.retry_if_exception_type = _Retry.retry_if_exception_type
sys.modules["tenacity"] = _tenacity_mod

# .utils (decode_http_urls_in_dict)
_utils_mod = types.ModuleType("miroflow_tools.mcp_servers.utils")
def decode_http_urls_in_dict(d):
    return d
_utils_mod.decode_http_urls_in_dict = decode_http_urls_in_dict
sys.modules["miroflow_tools"] = types.ModuleType("miroflow_tools")
sys.modules["miroflow_tools.mcp_servers"] = types.ModuleType("miroflow_tools.mcp_servers")
sys.modules["miroflow_tools.mcp_servers.utils"] = _utils_mod

# Now load the target module from file
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "youcom_search_mcp_server",
    os.path.join(
        os.path.dirname(__file__), "..", "src", "miroflow_tools", "mcp_servers",
        "youcom_search_mcp_server.py",
    ),
)
_target = importlib.util.module_from_spec(_spec)
_target.__package__ = "miroflow_tools.mcp_servers"
_spec.loader.exec_module(_target)

youcom_search = _target.youcom_search
youcom_research = _target.youcom_research


def _parse(result: str) -> dict:
    return json.loads(result)


# --- youcom_search tests ---

def test_search_no_api_key():
    with patch.object(_target, "YOUCOM_API_KEY", ""):
        result = _parse(youcom_search("test query"))
    assert result["success"] is False
    assert "YDC_API_KEY" in result["error"]


def test_search_empty_query():
    with patch.object(_target, "YOUCOM_API_KEY", "fake-key"):
        result = _parse(youcom_search(""))
    assert result["success"] is False
    assert "required" in result["error"].lower()


def test_search_success():
    mock_response = {
        "results": [
            {"title": "Example", "url": "https://example.com", "snippet": "A snippet."}
        ],
        "images": [],
    }
    with patch.object(_target, "YOUCOM_API_KEY", "fake-key"):
        with patch.object(_target, "_post_json", return_value=mock_response):
            result = _parse(youcom_search("hello world", max_results=5))
    assert result["results"][0]["title"] == "Example"
    assert result["results"][0]["url"] == "https://example.com"


# --- youcom_research tests ---

def test_research_no_api_key():
    with patch.object(_target, "YOUCOM_API_KEY", ""):
        result = _parse(youcom_research("complex question"))
    assert result["success"] is False
    assert "YDC_API_KEY" in result["error"]


def test_research_empty_input():
    with patch.object(_target, "YOUCOM_API_KEY", "fake-key"):
        result = _parse(youcom_research(""))
    assert result["success"] is False
    assert "required" in result["error"].lower()


def test_research_invalid_effort():
    with patch.object(_target, "YOUCOM_API_KEY", "fake-key"):
        result = _parse(youcom_research("query", research_effort="invalid"))
    assert result["success"] is False
    assert "research_effort" in result["error"].lower()


def test_research_success():
    mock_response = {
        "output": {
            "content": "Research says [[1]] ...",
            "content_type": "text",
            "sources": [{"url": "https://src.com", "title": "Src", "snippets": ["s1"]}],
        }
    }
    with patch.object(_target, "YOUCOM_API_KEY", "fake-key"):
        with patch.object(_target, "_post_json", return_value=mock_response):
            result = _parse(youcom_research("complex question", research_effort="lite"))
    assert result["output"]["content"] == "Research says [[1]] ..."
    assert result["output"]["sources"][0]["url"] == "https://src.com"


if __name__ == "__main__":
    test_search_no_api_key()
    test_search_empty_query()
    test_search_success()
    test_research_no_api_key()
    test_research_empty_input()
    test_research_invalid_effort()
    test_research_success()
    print("All 7 tests passed.")
