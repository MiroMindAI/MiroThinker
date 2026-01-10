# Copyright (c) 2025 MiroMind
# This source code is licensed under the MIT License.

"""Wrapper utilities for handling responses and errors in a type-safe manner."""

from typing import Any, Dict, Optional


class ErrorBox:
    """
    A wrapper class for error messages.

    Use this to wrap error messages that should be distinguishable from normal responses.

    Example:
        >>> error = ErrorBox("Connection failed")
        >>> if ErrorBox.is_error_box(error):
        ...     print(f"Error: {error}")
    """

    def __init__(self, error_msg: str) -> None:
        self.error_msg = error_msg

    def __str__(self) -> str:
        return self.error_msg

    def __repr__(self) -> str:
        return f"ErrorBox({self.error_msg!r})"

    @staticmethod
    def is_error_box(something: Any) -> bool:
        """Check if the given object is an ErrorBox instance."""
        return isinstance(something, ErrorBox)


class ResponseBox:
    """
    A wrapper class for responses with optional extra information.

    Use this to wrap responses that may include additional metadata.

    Example:
        >>> response = ResponseBox({"data": "value"}, {"warning_msg": "Rate limited"})
        >>> if response.has_extra_info():
        ...     print(response.get_extra_info())
    """

    def __init__(
        self, response: Any, extra_info: Optional[Dict[str, Any]] = None
    ) -> None:
        self.response = response
        self.extra_info = extra_info

    def __str__(self) -> str:
        return str(self.response)

    def __repr__(self) -> str:
        return f"ResponseBox({self.response!r}, extra_info={self.extra_info!r})"

    @staticmethod
    def is_response_box(something: Any) -> bool:
        """Check if the given object is a ResponseBox instance."""
        return isinstance(something, ResponseBox)

    def has_extra_info(self) -> bool:
        """Check if this response has extra information attached."""
        return self.extra_info is not None

    def get_extra_info(self) -> Optional[Dict[str, Any]]:
        """Get the extra information attached to this response."""
        return self.extra_info

    def get_response(self) -> Any:
        """Get the wrapped response object."""
        return self.response
