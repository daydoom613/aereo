"""Storing and fetching uploaded files and their measured features."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from app.domain import (
    FileFormat,
    FileStatus,
    Measurement,
    MeasurementStatus,
    MeasurementSummary,
    MeasurementType,
    SourceFeature,
)
from app.models import Feature, UploadedFile
from app.models.tables import utc_now

MeasuredFeature = tuple[SourceFeature, Measurement]


class FileRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_processing(
        self, filename: str, file_format: FileFormat, size_bytes: int
    ) -> UploadedFile:
        """Record an accepted upload before its content is read."""
        record = UploadedFile(
            filename=filename,
            format=file_format,
            size_bytes=size_bytes,
            status=FileStatus.PROCESSING,
        )
        self._session.add(record)
        self._session.commit()
        return record

    def complete(
        self,
        record: UploadedFile,
        crs: str | None,
        crs_assumed: bool,
        measured_features: Sequence[MeasuredFeature],
    ) -> None:
        """Store the features and mark the file COMPLETED, in one transaction."""
        rows = [
            _feature_row(record.id, index, feature, measurement)
            for index, (feature, measurement) in enumerate(measured_features)
        ]
        if rows:
            self._session.execute(insert(Feature), rows)
        record.status = FileStatus.COMPLETED
        record.crs = crs
        record.crs_assumed = crs_assumed
        record.feature_count = len(rows)
        record.processed_at = utc_now()
        self._session.commit()

    def fail(self, record: UploadedFile, error: str) -> None:
        self._session.rollback()  # drop anything half-written for this file
        record.status = FileStatus.FAILED
        record.error = error
        record.processed_at = utc_now()
        self._session.commit()

    def get(self, file_id: str) -> UploadedFile | None:
        return self._session.get(UploadedFile, file_id)

    def features(self, file_id: str, limit: int, offset: int) -> Sequence[Feature]:
        query = (
            select(Feature)
            .where(Feature.file_id == file_id)
            .order_by(Feature.feature_index)
            .limit(limit)
            .offset(offset)
        )
        return self._session.scalars(query).all()

    def summary(self, file_id: str) -> MeasurementSummary:
        """Totals over every feature of the file, computed by the database."""
        query = (
            select(
                Feature.measurement_status,
                Feature.measurement_type,
                func.count(),
                func.sum(Feature.measurement_value),
            )
            .where(Feature.file_id == file_id)
            .group_by(Feature.measurement_status, Feature.measurement_type)
        )
        counts = dict.fromkeys(MeasurementStatus, 0)
        totals = dict.fromkeys(MeasurementType, 0.0)
        for status, measurement_type, count, total in self._session.execute(query):
            counts[status] += count
            # Only measured features have a value, so every other group sums to NULL.
            if measurement_type is not None and total is not None:
                totals[measurement_type] += total
        return MeasurementSummary(
            total_area_m2=totals[MeasurementType.AREA],
            total_length_m=totals[MeasurementType.LENGTH],
            measured=counts[MeasurementStatus.MEASURED],
            not_required=counts[MeasurementStatus.NOT_REQUIRED],
            unsupported=counts[MeasurementStatus.UNSUPPORTED],
            failed=counts[MeasurementStatus.FAILED],
        )


def _feature_row(
    file_id: str, index: int, feature: SourceFeature, measurement: Measurement
) -> dict[str, Any]:
    return {
        "file_id": file_id,
        "feature_index": index,
        "source_id": feature.source_id,
        "geometry_type": feature.geometry_type,
        "geometry": feature.geometry_as_geojson(),
        "properties": feature.properties,
        "measurement_type": measurement.type,
        "measurement_value": measurement.value,
        "measurement_unit": measurement.unit,
        "measurement_method": measurement.method,
        "projected_crs": measurement.projected_crs,
        "measurement_status": measurement.status,
        "measurement_reason": measurement.reason,
        "geometry_repaired": measurement.geometry_repaired,
    }
