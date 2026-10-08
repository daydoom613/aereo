"""Builders shared by the tests: known shapes, and the KML and shapefile uploads made from them."""

from __future__ import annotations

import io
import struct
import zipfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import geopandas
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


# --- KML -------------------------------------------------------------------------------------


def kml_geometry(geometry: BaseGeometry) -> str:
    kind = geometry.geom_type
    if kind == "Point":
        return f"<Point>{_coordinates(geometry.coords)}</Point>"
    if kind == "LineString":
        return f"<LineString>{_coordinates(geometry.coords)}</LineString>"
    if kind == "Polygon":
        outer = f"<outerBoundaryIs>{_ring(geometry.exterior.coords)}</outerBoundaryIs>"
        holes = "".join(
            f"<innerBoundaryIs>{_ring(hole.coords)}</innerBoundaryIs>"
            for hole in geometry.interiors
        )
        return f"<Polygon>{outer}{holes}</Polygon>"
    parts = "".join(kml_geometry(part) for part in geometry.geoms)
    return f"<MultiGeometry>{parts}</MultiGeometry>"


def placemark(
    geometry: BaseGeometry | None = None,
    *,
    name: str = "Feature",
    placemark_id: str | None = None,
    data: Mapping[str, Any] | None = None,
    geometry_xml: str | None = None,
) -> str:
    """One Placemark. `geometry_xml` supplies raw KML for shapes Shapely cannot express."""
    id_attribute = f' id="{placemark_id}"' if placemark_id else ""
    fields = "".join(
        f'<Data name="{key}"><value>{value}</value></Data>' for key, value in (data or {}).items()
    )
    extended_data = f"<ExtendedData>{fields}</ExtendedData>" if fields else ""
    if geometry_xml is None:
        geometry_xml = "" if geometry is None else kml_geometry(geometry)
    return f"<Placemark{id_attribute}><name>{name}</name>{extended_data}{geometry_xml}</Placemark>"


def folder(name: str, *children: str) -> str:
    return f"<Folder><name>{name}</name>{''.join(children)}</Folder>"


def kml_document(*children: str, name: str = "Test survey") -> bytes:
    body = f"<Document><name>{name}</name>{''.join(children)}</Document>"
    return kml_file(body)


def kml_file(body: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<kml xmlns="http://www.opengis.net/kml/2.2">{body}</kml>'
    ).encode()


def _coordinates(points: Iterable[tuple[float, ...]]) -> str:
    text = " ".join(",".join(repr(float(value)) for value in point) for point in points)
    return f"<coordinates>{text}</coordinates>"


def _ring(points: Iterable[tuple[float, ...]]) -> str:
    return f"<LinearRing>{_coordinates(points)}</LinearRing>"


# --- shapefile archives ----------------------------------------------------------------------


def layer(
    geometries: list[BaseGeometry | None], crs: int | None = WGS84, **columns: list[Any]
) -> geopandas.GeoDataFrame:
    return geopandas.GeoDataFrame(columns, geometry=geometries, crs=crs)


def shapefile_parts(frame: geopandas.GeoDataFrame, stem: str = "parcels") -> dict[str, bytes]:
    """The files GDAL writes for a shapefile, keyed by file name."""
    with TemporaryDirectory() as directory:
        frame.to_file(Path(directory) / f"{stem}.shp", engine="pyogrio")
        return {part.name: part.read_bytes() for part in sorted(Path(directory).iterdir())}


def zip_of(entries: Mapping[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def shapefile_zip(
    frame: geopandas.GeoDataFrame,
    *,
    stem: str = "parcels",
    folder_name: str = "",
    without: tuple[str, ...] = (),
) -> bytes:
    """A zipped shapefile, optionally inside a folder or with some parts (by extension) left out."""
    parts = shapefile_parts(frame, stem)
    return zip_of(
        {
            f"{folder_name}{name}": content
            for name, content in parts.items()
            if Path(name).suffix not in without
        }
    )


def mark_first_entry_encrypted(archive: bytes) -> bytes:
    """Set the 'encrypted' flag on the first entry of the zip's central directory."""
    patched = bytearray(archive)
    record = patched.find(b"PK\x01\x02")
    patched[record + 8] |= 0x01
    return bytes(patched)


def understate_size_of(archive: bytes, entry_name: str, declared_size: int) -> bytes:
    """Rewrite the uncompressed size the central directory declares for one entry."""
    patched = bytearray(archive)
    record = patched.find(b"PK\x01\x02")
    while record != -1:
        name_length = struct.unpack_from("<H", patched, record + 28)[0]
        name = patched[record + 46 : record + 46 + name_length].decode()
        if name == entry_name:
            struct.pack_into("<I", patched, record + 24, declared_size)
            return bytes(patched)
        record = patched.find(b"PK\x01\x02", record + 4)
    raise KeyError(entry_name)
