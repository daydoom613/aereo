"""The two tables: one row per uploaded file, one row per feature found in it."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Dialect, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from app.domain import (
    FileFormat,
    FileStatus,
    MeasurementMethod,
    MeasurementStatus,
    MeasurementType,
)


class Base(DeclarativeBase):
    pass


class UtcDateTime(TypeDecorator[datetime]):
    """A timestamp that is always UTC. SQLite drops time zones, so they are restored on read."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return None if value is None else value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return None if value is None else value.replace(tzinfo=UTC)


def utc_now() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return str(uuid.uuid4())


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    filename: Mapped[str] = mapped_column(String(255))
    format: Mapped[FileFormat]
    size_bytes: Mapped[int]
    status: Mapped[FileStatus]
    crs: Mapped[str | None] = mapped_column(Text)
    crs_assumed: Mapped[bool] = mapped_column(default=False)
    feature_count: Mapped[int | None]
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)
    processed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class Feature(Base):
    __tablename__ = "features"
    # The unique constraint is also the index that serves "features of a file, in order".
    __table_args__ = (UniqueConstraint("file_id", "feature_index"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[str] = mapped_column(ForeignKey("uploaded_files.id", ondelete="CASCADE"))
    feature_index: Mapped[int]
    source_id: Mapped[str | None] = mapped_column(Text)
    geometry_type: Mapped[str | None] = mapped_column(String(32))
    geometry: Mapped[dict[str, Any] | None] = mapped_column(JSON(none_as_null=True))
    properties: Mapped[dict[str, Any]] = mapped_column(JSON)
    measurement_type: Mapped[MeasurementType | None]
    measurement_value: Mapped[float | None]
    measurement_unit: Mapped[str | None] = mapped_column(String(8))
    measurement_method: Mapped[MeasurementMethod | None]
    projected_crs: Mapped[str | None] = mapped_column(String(32))
    measurement_status: Mapped[MeasurementStatus]
    measurement_reason: Mapped[str | None] = mapped_column(Text)
    geometry_repaired: Mapped[bool] = mapped_column(default=False)
