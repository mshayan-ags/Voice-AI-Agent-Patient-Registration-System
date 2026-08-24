from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str
    field: Optional[str] = None
    # Per-field messages when more than one field failed validation at once,
    # so a caller (or the voice agent) can address every broken field in
    # one pass instead of a slow "one at a time" round trip. `details` is a
    # free-form bag for anything else an error needs to carry (e.g. the
    # existing record on a 409 conflict) - kept off the top-level envelope
    # so exactly one of {data, error} is ever populated, never both.
    field_errors: Optional[dict[str, str]] = None
    details: Optional[dict[str, Any]] = None


class Envelope(BaseModel, Generic[T]):
    data: Optional[T] = None
    error: Optional[ErrorDetail] = None


def ok(data: Any) -> dict:
    return {"data": data, "error": None}


def fail(
    code: str,
    message: str,
    field: Optional[str] = None,
    field_errors: Optional[dict[str, str]] = None,
    details: Optional[dict[str, Any]] = None,
) -> dict:
    return {
        "data": None,
        "error": {
            "code": code,
            "message": message,
            "field": field,
            "field_errors": field_errors,
            "details": details,
        },
    }
