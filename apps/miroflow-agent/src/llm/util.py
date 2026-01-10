# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

"""
Utility decorators and helpers for LLM client operations.

This module provides:
- Timeout decorator for async LLM API calls
- Other common utilities shared across LLM providers
"""

import asyncio
import functools
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


def with_timeout(
    timeout_s: float = 300.0,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """
    Decorator: wraps any *async* function in asyncio.wait_for().
    Usage:
        @with_timeout(20)
        async def create_message_foo(...): ...
    """

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_s)

        return wrapper

    return decorator
