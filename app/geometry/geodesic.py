"""Area and length on the WGS 84 ellipsoid, for features no single UTM zone fits.

Geometries passed in must be in WGS 84 longitude/latitude.
"""

from __future__ import annotations

from collections.abc import Iterator

from pyproj import Geod
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry

_WGS84_ELLIPSOID = Geod(ellps="WGS84")


def geodesic_length(geometry: BaseGeometry) -> float:
    """Length in metres of a LineString or MultiLineString."""
    return float(_WGS84_ELLIPSOID.geometry_length(geometry))


def geodesic_area(geometry: BaseGeometry) -> float:
    """Area in square metres of every polygon in the geometry, holes excluded."""
    return sum(_polygon_area(polygon) for polygon in _polygons(geometry))


def _polygon_area(polygon: Polygon) -> float:
    holes = sum(_ring_area(ring) for ring in polygon.interiors)
    return _ring_area(polygon.exterior) - holes


def _ring_area(ring: BaseGeometry) -> float:
    longitudes, latitudes = ring.xy
    signed_area, _perimeter = _WGS84_ELLIPSOID.polygon_area_perimeter(longitudes, latitudes)
    # The sign only says which way the ring is wound. Files do not wind rings consistently, and
    # pyproj's whole-polygon helper adds a hole instead of subtracting it when the hole is wound
    # the same way as the outer ring. Taking each ring's size on its own avoids that.
    return abs(float(signed_area))


def _polygons(geometry: BaseGeometry) -> Iterator[Polygon]:
    if geometry.geom_type == "Polygon":
        yield geometry
    for part in getattr(geometry, "geoms", ()):
        yield from _polygons(part)
