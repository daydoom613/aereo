"""Response bodies for uploaded files and their measurements."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.domain import (
    FileFormat,
    FileStatus,
    MeasurementMethod,
    MeasurementStatus,
    MeasurementType,
)


class FileLinks(BaseModel):
    self: str
    measurements: str


class FileResponse(BaseModel):
    id: str
    filename: str
    format: FileFormat
    size_bytes: int
    status: FileStatus
    feature_count: int | None = Field(description="Null until the file has been processed.")
    crs: str | None = Field(description="The file's CRS, for example EPSG:4326. Null if unknown.")
    crs_assumed: bool = Field(
        description="True when the file declared no CRS and EPSG:4326 was assumed."
    )
    error: str | None = Field(description="Why processing failed, when status is FAILED.")
    created_at: datetime
    processed_at: datetime | None
    links: FileLinks


class MeasurementResponse(BaseModel):
    type: MeasurementType | None = Field(description="Null for features that are not measured.")
    value: float | None
    unit: str | None = Field(description="m2 for area, m for length.")
    method: MeasurementMethod | None = Field(
        description="PROJECTED: measured in projected_crs. GEODESIC: measured on the ellipsoid."
    )
    projected_crs: str | None = Field(description="The CRS the feature was measured in.")
    geodesic_value: float | None = Field(
        description=(
            "The same measurement on the WGS 84 ellipsoid, in the same unit: the ground value, "
            "next to the grid value in `value`. Equal to `value` when method is GEODESIC."
        )
    )
    status: MeasurementStatus
    reason: str | None = Field(description="Why the feature was not measured.")
    geometry_repaired: bool = Field(
        description="True when an invalid polygon was repaired before measuring."
    )


class FeatureMeasurement(BaseModel):
    feature_index: int = Field(description="0-based position of the feature in the file.")
    source_id: str | None = Field(description="The file's own identifier for the feature, if any.")
    geometry_type: str | None
    geometry: dict[str, Any] | None = Field(
        default=None,
        description=(
            "GeoJSON geometry object with coordinates in the file's CRS. Null when the feature "
            "has none. Left out of the item when `include_geometry=false`."
        ),
    )
    crs: str | None
    properties: dict[str, Any]
    measurement: MeasurementResponse


class MeasurementSummaryResponse(BaseModel):
    total_area_m2: float
    total_length_m: float
    total_geodesic_area_m2: float
    total_geodesic_length_m: float
    measured: int
    not_required: int
    unsupported: int
    failed: int


class Pagination(BaseModel):
    limit: int
    offset: int
    total: int


class PageLinks(BaseModel):
    self: str
    file: str
    next: str | None
    prev: str | None


class FileListLinks(BaseModel):
    self: str
    next: str | None
    prev: str | None


class FilesResponse(BaseModel):
    pagination: Pagination
    links: FileListLinks
    items: list[FileResponse] = Field(description="Newest first.")


class MeasurementsResponse(BaseModel):
    file_id: str
    crs: str | None
    summary: MeasurementSummaryResponse = Field(description="Totals for the whole file.")
    pagination: Pagination
    links: PageLinks
    items: list[FeatureMeasurement]
