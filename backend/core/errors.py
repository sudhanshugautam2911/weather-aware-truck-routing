"""Errors the API turns into clear, user-facing messages.

`message` is written for the end user (a driver or dispatcher): it says what
happened and what to do next. `field` points the UI at the input to fix.
"""

from __future__ import annotations


class AppError(Exception):
    status = 400

    def __init__(self, code: str, message: str, *, field: str | None = None, status: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
        if status is not None:
            self.status = status

    def as_dict(self) -> dict:
        body = {"code": self.code, "message": self.message}
        if self.field:
            body["field"] = self.field
        return body


class UpstreamError(AppError):
    """A third-party service failed or is busy."""

    status = 503
