"""Builders shared by the tests: known shapes, and the KML and shapefile uploads made from them."""

from __future__ import annotations

import shapely
from pyproj import Transformer
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

UTM_43N = 32643
WGS84 = 4326

# A 1000 m x 1000 m square on the central meridian of UTM zone 43N, near Bengaluru.
SQUARE_1KM = box(500_000, 1_400_000, 501_000, 1_401_000)
SQUARE_1KM_AREA = 1_000_000.0


def reproject(geometry: BaseGeometry, source: int | str, target: int | str) -> BaseGeometry:
    transformer = Transformer.from_crs(source, target, always_xy=True)
    return shapely.transform(geometry, transformer.transform, interleaved=False)


def to_wgs84(geometry: BaseGeometry, source: int | str = UTM_43N) -> BaseGeometry:
    return reproject(geometry, source, WGS84)
