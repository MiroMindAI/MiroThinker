# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

"""Input/Output module for processing task inputs and formatting outputs."""

from .input_handler import process_input
from .output_formatter import OutputFormatter

__all__ = [
    "process_input",
    "OutputFormatter",
]
