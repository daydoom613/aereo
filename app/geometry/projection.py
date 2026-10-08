"""Choosing the projected CRS a feature is measured in.

The rule (docs/DECISIONS.md, D8): a feature is measured in the WGS 84 / UTM zone that contains the
centre of its bounding box, unless no single zone represents it well.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from pyproj import CRS

WGS84 = CRS.from_epsg(4326)

UTM_ZONE_WIDTH_DEG = 6.0
UTM_SOUTH_LIMIT_DEG = -80.0
UTM_NORTH_LIMIT_DEG = 84.0
# A feature this wide stays within 3.5 degrees of its zone's central meridian, where UTM area is
# within 0.3% of the ellipsoid. Wider features are measured on the ellipsoid instead.
UTM_MAX_FEATURE_WIDTH_DEG = 1.0
# EPSG numbers WGS 84 / UTM zones as 326xx (north) and 327xx (south), xx being the zone.
EPSG_WGS84_UTM_NORTH = 32600
EPSG_WGS84_UTM_SOUTH = 32700


def utm_epsg_code(longitude: float, latitude: float) -> int:
    """The EPSG code of the WGS 84 / UTM zone containing a point."""
    # Wrapping first means longitude 180 lands in zone 1, the same zone as -180.
    degrees_east_of_antimeridian = (longitude + 180.0) % 360.0
    zone = int(degrees_east_of_antimeridian // UTM_ZONE_WIDTH_DEG) + 1
    hemisphere = EPSG_WGS84_UTM_NORTH if latitude >= 0 else EPSG_WGS84_UTM_SOUTH
    return hemisphere + zone


@dataclass(frozen=True)
class LonLatBox:
    """A feature's bounding box in WGS 84 degrees."""

    west: float
    south: float
    east: float
    north: float

    @property
    def is_finite(self) -> bool:
        return all(math.isfinite(edge) for edge in (self.west, self.south, self.east, self.north))

    def fits_one_utm_zone(self) -> bool:
        crosses_antimeridian = self.east < self.west
        too_wide = self.east - self.west > UTM_MAX_FEATURE_WIDTH_DEG
        outside_utm_latitudes = self.south < UTM_SOUTH_LIMIT_DEG or self.north > UTM_NORTH_LIMIT_DEG
        return not (crosses_antimeridian or too_wide or outside_utm_latitudes)

    def utm_epsg_code(self) -> int:
        """The UTM zone of the box's centre."""
        return utm_epsg_code((self.west + self.east) / 2, (self.south + self.north) / 2)


def crs_label(crs: CRS | None) -> str | None:
    """A short public name for a CRS: its EPSG code when it has one, else its definition."""
    if crs is None:
        return None
    epsg = crs.to_epsg()
    return f"EPSG:{epsg}" if epsg is not None else crs.to_string()
