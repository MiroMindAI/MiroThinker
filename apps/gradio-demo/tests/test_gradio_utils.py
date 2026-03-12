# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

"""
Unit tests for Gradio demo utilities.

Tests for:
- ThreadSafeAsyncQueue
- filter_google_search_organic
"""

import asyncio
import pytest


class ThreadSafeAsyncQueue:
    """Thread-safe async queue wrapper (copied for testing)."""

    def __init__(self):
        self._queue = asyncio.Queue()
        self._loop = None
        self._closed = False

    def set_loop(self, loop):
        self._loop = loop

    async def put(self, item):
        """Put data safely from any thread"""
        if self._closed:
            return
        await self._queue.put(item)

    def put_nowait_threadsafe(self, item):
        """Put data from other threads - use direct queue put for lower latency"""
        if self._closed or not self._loop:
            return
        self._loop.call_soon_threadsafe(lambda: self._queue.put_nowait(item))

    async def get(self):
        return await self._queue.get()

    def close(self):
        self._closed = True


def filter_google_search_organic(organic: list) -> list:
    """
    Filter google search organic results to remove unnecessary information
    """
    result = []
    for item in organic:
        result.append(
            {
                "title": item.get("title", ""),
                "link": item.get("link", ""),
            }
        )
    return result


class TestThreadSafeAsyncQueue:
    """Tests for ThreadSafeAsyncQueue class."""

    @pytest.mark.asyncio
    async def test_put_and_get(self):
        """Test basic put and get operations."""
        queue = ThreadSafeAsyncQueue()
        queue.set_loop(asyncio.get_event_loop())

        await queue.put({"test": "data"})
        result = await queue.get()
        assert result == {"test": "data"}

    @pytest.mark.asyncio
    async def test_closed_queue_rejects_put(self):
        """Test that closed queue rejects put operations."""
        queue = ThreadSafeAsyncQueue()
        queue.set_loop(asyncio.get_event_loop())

        queue.close()
        await queue.put({"test": "data"})

        # Queue should be empty because put was rejected
        assert queue._queue.empty()

    @pytest.mark.asyncio
    async def test_close_sets_flag(self):
        """Test that close() sets the closed flag."""
        queue = ThreadSafeAsyncQueue()
        assert queue._closed is False

        queue.close()
        assert queue._closed is True

    @pytest.mark.asyncio
    async def test_put_nowait_threadsafe(self):
        """Test threadsafe put operation."""
        queue = ThreadSafeAsyncQueue()
        queue.set_loop(asyncio.get_event_loop())

        queue.put_nowait_threadsafe({"test": "data"})

        # Allow event loop to process the call_soon_threadsafe
        await asyncio.sleep(0.01)

        result = await queue.get()
        assert result == {"test": "data"}

    @pytest.mark.asyncio
    async def test_put_nowait_threadsafe_closed(self):
        """Test that put_nowait_threadsafe respects closed flag."""
        queue = ThreadSafeAsyncQueue()
        queue.set_loop(asyncio.get_event_loop())

        queue.close()
        queue.put_nowait_threadsafe({"test": "data"})

        await asyncio.sleep(0.01)
        assert queue._queue.empty()

    @pytest.mark.asyncio
    async def test_put_nowait_threadsafe_no_loop(self):
        """Test that put_nowait_threadsafe handles missing loop."""
        queue = ThreadSafeAsyncQueue()
        # Don't set loop

        queue.put_nowait_threadsafe({"test": "data"})

        await asyncio.sleep(0.01)
        assert queue._queue.empty()


class TestFilterGoogleSearchOrganic:
    """Tests for filter_google_search_organic function."""

    def test_basic_filtering(self):
        """Test basic filtering of search results."""
        organic = [
            {"title": "Result 1", "link": "https://example.com/1", "snippet": "..."},
            {"title": "Result 2", "link": "https://example.com/2", "snippet": "..."},
        ]
        result = filter_google_search_organic(organic)
        assert len(result) == 2
        assert result[0] == {"title": "Result 1", "link": "https://example.com/1"}
        assert result[1] == {"title": "Result 2", "link": "https://example.com/2"}

    def test_missing_fields(self):
        """Test handling of missing fields."""
        organic = [
            {"title": "Result 1"},  # Missing link
            {"link": "https://example.com/2"},  # Missing title
            {},  # Missing both
        ]
        result = filter_google_search_organic(organic)
        assert result[0] == {"title": "Result 1", "link": ""}
        assert result[1] == {"title": "", "link": "https://example.com/2"}
        assert result[2] == {"title": "", "link": ""}

    def test_empty_list(self):
        """Test handling of empty list."""
        result = filter_google_search_organic([])
        assert result == []

    def test_extra_fields_ignored(self):
        """Test that extra fields are ignored."""
        organic = [
            {
                "title": "Result",
                "link": "https://example.com",
                "snippet": "text",
                "date": "2024-01-01",
            }
        ]
        result = filter_google_search_organic(organic)
        assert "snippet" not in result[0]
        assert "date" not in result[0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])