"""Typed error of the library."""

from __future__ import annotations

from typing import Literal

ErrorCode = Literal["invalid_config", "invalid_sample", "too_many_samples", "input_invalid"]

_MAX_MESSAGE = 200


class SLOError(Exception):
    """Base error of the library.

    Attributes:
        code: Stable machine-readable error code.
        row: 1-based input row for sample errors, otherwise ``None``.
        message: Human-readable description, at most 200 characters, never a secret.
    """

    def __init__(self, code: ErrorCode, row: int | None = None, message: str = "") -> None:
        self.code: ErrorCode = code
        self.row = row
        self.message = (message or code)[:_MAX_MESSAGE]
        super().__init__(self.message)
