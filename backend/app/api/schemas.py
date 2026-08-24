from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str
    message: str
    field: Optional[str] = None


class Envelope(BaseModel, Generic[T]):
    data: Optional[T] = None
    error: Optional[ErrorDetail] = None


def ok(data: Any) -> dict:
    return {"data": data, "error": None}


def fail(code: str, message: str, field: Optional[str] = None) -> dict:
    return {"data": None, "error": {"code": code, "message": message, "field": field}}
