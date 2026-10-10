"""Measuring features: area for polygons, length for lines, always in metres."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from operator import attrgetter

import shapely
from pyproj import CRS, Transformer
from pyproj.exceptions import ProjError
from shapely.geometry.base import BaseGeometry

from app.domain import (
    MEASUREMENT_DECIMALS,
    Measurement,
    MeasurementMethod,
    MeasurementStatus,
    MeasurementType,
)
from app.geometry.geodesic import geodesic_area, geodesic_length
from app.geometry.projection import WGS84, LonLatBox

logger = logging.getLogger(__name__)

_MEASUREMENT_BY_GEOMETRY_TYPE = {
    "Polygon": MeasurementType.AREA,
    "MultiPolygon": MeasurementType.AREA,
    "LineString": MeasurementType.LENGTH,
    "MultiLineString": MeasurementType.LENGTH,
}
_POINT_TYPES = frozenset({"Point", "MultiPoint"})

_Measure = Callable[[BaseGeometry], float]
_PLANAR_MEASURE: dict[MeasurementType, _Measure] = {
    MeasurementType.AREA: attrgetter("area"),
    MeasurementType.LENGTH: attrgetter("length"),
}
_GEODESIC_MEASURE: dict[MeasurementType, _Measure] = {
    MeasurementType.AREA: geodesic_area,
    MeasurementType.LENGTH: geodesic_length,
}

_NO_GEOMETRY = "The feature has no readable geometry."
_UNKNOWN_CRS = "unknown CRS"
_UNRELATED_CRS = (
    "The file's CRS cannot be related to WGS 84, so distances on the ground are unknown."
)
_IMPLAUSIBLE_AS_DEGREES = (
    "The file declares no CRS, and read as longitude/latitude this feature would be wider than "
    "1 degree or in a polar region, so its coordinates are probably not degrees. Add the .prj "
    "file to the archive."
)
_OUT_OF_RANGE = "The coordinates are outside the valid range of the file's CRS."
_UNMEASURABLE = "The geometry could not be measured."


class FeatureMeasurer:
    """Measures the features of one file. Holds the coordinate transformers for that file's CRS."""

    def __init__(self, source_crs: CRS | None, crs_assumed: bool = False) -> None:
        self._source_crs = source_crs
        self._crs_assumed = crs_assumed
        self._to_wgs84: Transformer | None = None
        self._crs_problem = _UNKNOWN_CRS
        self._to_utm: dict[int, Transformer] = {}
        if source_crs is not None:
            try:
                self._to_wgs84 = Transformer.from_crs(source_crs, WGS84, always_xy=True)
            except ProjError:
                self._crs_problem = _UNRELATED_CRS

    def measure(self, geometry: BaseGeometry | None) -> Measurement:
        """Never raises: a feature that cannot be measured says why in its Measurement."""
        if geometry is None or geometry.is_empty:
            return Measurement.unsupported(_NO_GEOMETRY)
        if geometry.geom_type in _POINT_TYPES:
            return Measurement.not_required()
        measurement_type = _MEASUREMENT_BY_GEOMETRY_TYPE.get(geometry.geom_type)
        if measurement_type is None:
            return Measurement.unsupported(f"A {geometry.geom_type} has no single area or length.")
        if self._to_wgs84 is None:
            return Measurement.unsupported(self._crs_problem, measurement_type)
        try:
            return self._measure(measurement_type, geometry, self._to_wgs84)
        except Exception:
            # One bad feature must not fail the whole file.
            logger.warning("A %s could not be measured", geometry.geom_type, exc_info=True)
            return Measurement.failed(measurement_type, _UNMEASURABLE)

    def _measure(
        self, measurement_type: MeasurementType, geometry: BaseGeometry, to_wgs84: Transformer
    ) -> Measurement:
        flat = shapely.force_2d(geometry)
        repaired = measurement_type is MeasurementType.AREA and not flat.is_valid
        if repaired:
            flat = shapely.make_valid(flat)

        extent = LonLatBox(*to_wgs84.transform_bounds(*flat.bounds))
        if not extent.is_finite:
            return Measurement.failed(measurement_type, _OUT_OF_RANGE)

        if extent.fits_one_utm_zone():
            epsg = extent.utm_epsg_code()
            projected = _transformed(flat, self._utm_transformer(epsg))
            value = _PLANAR_MEASURE[measurement_type](projected)
            method, projected_crs = MeasurementMethod.PROJECTED, f"EPSG:{epsg}"
        elif self._crs_assumed:
            # An assumed CRS is trusted only while the result looks like survey data. On a grid
            # in metres anything over a metre wide reads as over a degree, and lands here.
            return Measurement.unsupported(_IMPLAUSIBLE_AS_DEGREES, measurement_type)
        else:
            value = _GEODESIC_MEASURE[measurement_type](_transformed(flat, to_wgs84))
            method, projected_crs = MeasurementMethod.GEODESIC, None

        if not math.isfinite(value):
            return Measurement.failed(measurement_type, _OUT_OF_RANGE)
        return Measurement(
            status=MeasurementStatus.MEASURED,
            type=measurement_type,
            value=round(value, MEASUREMENT_DECIMALS),
            method=method,
            projected_crs=projected_crs,
            geometry_repaired=repaired,
        )

    def _utm_transformer(self, epsg: int) -> Transformer:
        if epsg not in self._to_utm:
            self._to_utm[epsg] = Transformer.from_crs(
                self._source_crs, CRS.from_epsg(epsg), always_xy=True
            )
        return self._to_utm[epsg]


def _transformed(geometry: BaseGeometry, transformer: Transformer) -> BaseGeometry:
    # interleaved=False hands pyproj separate x and y arrays, which is what it expects.
    return shapely.transform(geometry, transformer.transform, interleaved=False)
