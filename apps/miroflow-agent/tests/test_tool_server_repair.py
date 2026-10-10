# Copyright (c) 2025 MiroMind
# This source code is licensed under the Apache 2.0 License.

import importlib.util
from pathlib import Path

import pytest

# Load the standalone parser without initializing the full agent stack.
spec = importlib.util.spec_from_file_location(
    "parsing_utils", Path(__file__).parents[1] / "src/utils/parsing_utils.py"
)
parsing_utils = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parsing_utils)


@pytest.fixture(autouse=True)
def tool_mapping(monkeypatch):
    monkeypatch.setattr(
        parsing_utils,
        "_tool_server_mapping",
        {
            "google_search": "web",
            "scrape_and_extract_info": "web",
            "run_python_code": "python-server",
        },
    )


def call(server, tool):
    return f"<server_name>{server}</server_name>\n<tool_name>{tool}</tool_name>"


@pytest.mark.parametrize("correct_first", [True, False])
def test_repairs_wrong_call_even_when_another_call_is_correct(correct_first):
    correct = call("web", "google_search")
    wrong = call("wrong", "google_search")
    text = "\n".join([correct, wrong] if correct_first else [wrong, correct])

    assert parsing_utils.fix_server_name_in_text(text) == "\n".join([correct, correct])


def test_repairs_tools_sharing_a_server_independently():
    text = "\n".join(
        [
            call("web", "google_search"),
            call("wrong", "scrape_and_extract_info"),
            call("wrong", "python"),
            call("custom", "unrelated_tool"),
        ]
    )
    expected = "\n".join(
        [
            call("web", "google_search"),
            call("web", "scrape_and_extract_info"),
            call("python-server", "run_python_code"),
            call("custom", "unrelated_tool"),
        ]
    )

    assert parsing_utils.fix_server_name_in_text(text) == expected


def test_correct_calls_are_unchanged():
    text = call("web", "google_search")

    assert parsing_utils.fix_server_name_in_text(text) == text
