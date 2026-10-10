"""The shared vocabulary of the service: enums and the value objects passed between layers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pyproj import CRS
from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry

# Measurements are reported to the millimetre: finer than any survey, without float noise.
MEASUREMENT_DECIMALS = 3


class FileFormat(StrEnum):
    KML = "KML"
    SHAPEFILE = "SHAPEFILE"


class FileStatus(StrEnum):
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class MeasurementType(StrEnum):
    AREA = "AREA"
    LENGTH = "LENGTH"

    @property
    def unit(self) -> str:
        """UCUM unit code: square metres for area, metres for length."""
        return "m2" if self is MeasurementType.AREA else "m"


class MeasurementMethod(StrEnum):
    PROJECTED = "PROJECTED"
    GEODESIC = "GEODESIC"


class MeasurementStatus(StrEnum):
    MEASURED = "MEASURED"
    NOT_REQUIRED = "NOT_REQUIRED"
    UNSUPPORTED = "UNSUPPORTED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class Measurement:
    """The outcome of measuring one feature. Every feature gets one, measured or not."""

    status: MeasurementStatus
    type: MeasurementType | None = None
    value: float | None = None
    method: MeasurementMethod | None = None
    projected_crs: str | None = None
    # The same quantity on the WGS 84 ellipsoid. Equal to `value` when the method is GEODESIC.
    geodesic_value: float | None = None
    reason: str | None = None
    geometry_repaired: bool = False

    @property
    def unit(self) -> str | None:
        if self.type is None or self.value is None:
            return None
        return self.type.unit

    @classmethod
    def not_required(cls) -> Measurement:
        return cls(status=MeasurementStatus.NOT_REQUIRED)

    @classmethod
    def unsupported(cls, reason: str, type: MeasurementType | None = None) -> Measurement:
        return cls(status=MeasurementStatus.UNSUPPORTED, type=type, reason=reason)

    @classmethod
    def failed(cls, type: MeasurementType, reason: str) -> Measurement:
        return cls(status=MeasurementStatus.FAILED, type=type, reason=reason)


@dataclass(frozen=True)
class SourceFeature:
    """One feature as read from the file."""

    source_id: str | None
    geometry: BaseGeometry | None
    properties: dict[str, Any]

    @property
    def geometry_type(self) -> str | None:
        return None if self.geometry is None else str(self.geometry.geom_type)

    def geometry_as_geojson(self) -> dict[str, Any] | None:
        """The geometry as a GeoJSON geometry object, coordinates in the file's CRS."""
        return None if self.geometry is None else dict(mapping(self.geometry))


@dataclass(frozen=True)
class GeoDataset:
    """Everything a reader extracts from one file."""

    features: list[SourceFeature]
    crs: CRS | None
    crs_assumed: bool = False


@dataclass(frozen=True)
class MeasurementSummary:
    """Totals over all the features of one file."""

    total_area_m2: float
    total_length_m: float
    total_geodesic_area_m2: float
    total_geodesic_length_m: float
    measured: int
    not_required: int
    unsupported: int
    failed: int
