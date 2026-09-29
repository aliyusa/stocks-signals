"""The DataPoint envelope: every externally sourced value travels with its provenance."""

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel

from app.models.entities import DataStatus

T = TypeVar("T")


class DataPoint(BaseModel, Generic[T]):
    value: T | None
    source: str | None
    as_of: datetime | None
    frequency: str | None
    status: DataStatus
    note: str | None = None

    @classmethod
    def unavailable(cls, note: str, source: str | None = None) -> "DataPoint[T]":
        return cls(value=None, source=source, as_of=None, frequency=None, status=DataStatus.UNAVAILABLE, note=note)


class Message(BaseModel):
    detail: str
