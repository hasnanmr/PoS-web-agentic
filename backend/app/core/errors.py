"""Domain errors raised by core services and mapped to the API error shape.

Core never imports from `api`; the API turns a `DomainError` into
`{"error": {"code", "message", "details"}}` with the status below.
"""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    status_code = 400

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class NotFoundError(DomainError):
    status_code = 404

    def __init__(self, entity: str, details: dict[str, Any] | None = None) -> None:
        super().__init__("not_found", f"{entity} not found", details)


class ConflictError(DomainError):
    status_code = 409


class ValidationFailedError(DomainError):
    status_code = 422

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__("validation_failed", message, details)
