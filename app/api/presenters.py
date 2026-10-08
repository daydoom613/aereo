"""Turning stored records into the public JSON shapes, links included.

The API is a view of the data, not a mirror of the tables: every field is mapped here by name.
"""

from __future__ import annotations

from dataclasses import asdict

from app.models import Feature, UploadedFile
from app.schemas.files import (
    FeatureMeasurement,
    FileLinks,
    FileResponse,
    MeasurementResponse,
    MeasurementsResponse,
    MeasurementSummaryResponse,
    PageLinks,
    Pagination,
)
from app.services.file_service import MeasurementPage

FILES_PATH = "/api/files"


def file_path(file_id: str) -> str:
    return f"{FILES_PATH}/{file_id}/"


def measurements_path(file_id: str) -> str:
    return f"{file_path(file_id)}measurements/"


def file_response(record: UploadedFile) -> FileResponse:
    return FileResponse(
        id=record.id,
        filename=record.filename,
        format=record.format,
        size_bytes=record.size_bytes,
        status=record.status,
        feature_count=record.feature_count,
        crs=record.crs,
        crs_assumed=record.crs_assumed,
        error=record.error,
        created_at=record.created_at,
        processed_at=record.processed_at,
        links=FileLinks(self=file_path(record.id), measurements=measurements_path(record.id)),
    )


def measurements_response(page: MeasurementPage, limit: int, offset: int) -> MeasurementsResponse:
    file = page.file
    total = file.feature_count or 0

    def page_url(page_offset: int) -> str:
        return f"{measurements_path(file.id)}?limit={limit}&offset={page_offset}"

    return MeasurementsResponse(
        file_id=file.id,
        crs=file.crs,
        summary=MeasurementSummaryResponse(**asdict(page.summary)),
        pagination=Pagination(limit=limit, offset=offset, total=total),
        links=PageLinks(
            self=page_url(offset),
            file=file_path(file.id),
            next=page_url(offset + limit) if offset + limit < total else None,
            prev=page_url(max(offset - limit, 0)) if offset > 0 else None,
        ),
        items=[_feature_measurement(feature, file.crs) for feature in page.features],
    )


def _feature_measurement(feature: Feature, crs: str | None) -> FeatureMeasurement:
    return FeatureMeasurement(
        feature_index=feature.feature_index,
        source_id=feature.source_id,
        geometry_type=feature.geometry_type,
        geometry=feature.geometry,
        crs=crs,
        properties=feature.properties,
        measurement=MeasurementResponse(
            type=feature.measurement_type,
            value=feature.measurement_value,
            unit=feature.measurement_unit,
            method=feature.measurement_method,
            projected_crs=feature.projected_crs,
            status=feature.measurement_status,
            reason=feature.measurement_reason,
            geometry_repaired=feature.geometry_repaired,
        ),
    )
