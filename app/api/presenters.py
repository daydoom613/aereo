"""Turning stored records into the public JSON shapes, links included.

The API is a view of the data, not a mirror of the tables: every field is mapped here by name.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict

from app.models import Feature, UploadedFile
from app.schemas.files import (
    FeatureMeasurement,
    FileLinks,
    FileListLinks,
    FileResponse,
    FilesResponse,
    MeasurementResponse,
    MeasurementsResponse,
    MeasurementSummaryResponse,
    PageLinks,
    Pagination,
)
from app.services.file_service import FilePage, MeasurementPage

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


def files_response(page: FilePage, limit: int, offset: int) -> FilesResponse:
    def page_url(page_offset: int) -> str:
        return f"{FILES_PATH}/?limit={limit}&offset={page_offset}"

    next_url, prev_url = _neighbours(page_url, limit, offset, page.total)
    return FilesResponse(
        pagination=Pagination(limit=limit, offset=offset, total=page.total),
        links=FileListLinks(self=page_url(offset), next=next_url, prev=prev_url),
        items=[file_response(record) for record in page.files],
    )


def measurements_response(page: MeasurementPage, limit: int, offset: int) -> MeasurementsResponse:
    file = page.file
    total = file.feature_count or 0

    def page_url(page_offset: int) -> str:
        return f"{measurements_path(file.id)}?limit={limit}&offset={page_offset}"

    next_url, prev_url = _neighbours(page_url, limit, offset, total)
    return MeasurementsResponse(
        file_id=file.id,
        crs=file.crs,
        summary=MeasurementSummaryResponse(**asdict(page.summary)),
        pagination=Pagination(limit=limit, offset=offset, total=total),
        links=PageLinks(
            self=page_url(offset), file=file_path(file.id), next=next_url, prev=prev_url
        ),
        items=[_feature_measurement(feature, file.crs) for feature in page.features],
    )


def _neighbours(
    page_url: Callable[[int], str], limit: int, offset: int, total: int
) -> tuple[str | None, str | None]:
    """Links to the next and the previous page, where there is one."""
    next_url = page_url(offset + limit) if offset + limit < total else None
    prev_url = page_url(max(offset - limit, 0)) if offset > 0 else None
    return next_url, prev_url


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
            geodesic_value=feature.geodesic_value,
            status=feature.measurement_status,
            reason=feature.measurement_reason,
            geometry_repaired=feature.geometry_repaired,
        ),
    )
