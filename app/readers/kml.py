"""Reading KML. GDAL's LIBKML driver does the parsing; every Folder and Document is a layer."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import suppress
from pathlib import Path
from xml.parsers import expat

import geopandas
import pyogrio
from pyproj import CRS

from app.core.errors import UnprocessableUploadError, UnsupportedFileTypeError
from app.domain import GeoDataset, SourceFeature
from app.readers.base import feature_rows, gdal_errors_as_read_errors, read_layer

# The KML standard fixes coordinates as WGS 84 longitude, latitude.
KML_CRS = CRS.from_epsg(4326)

_PLACEMARK_ID_FIELD = "id"
# Fields the driver reports that say how Google Earth draws a Placemark, not what it is.
_RENDERING_FIELDS = frozenset(
    {"altitudeMode", "tessellate", "extrude", "visibility", "drawOrder", "icon"}
)

_NOT_KML = "The file is not a KML document."
_SNIFF_CHUNK_BYTES = 64 * 1024


class KmlReader:
    def prepare(self, upload: Path, workdir: Path) -> Path:
        if _root_element(upload) != "kml":
            raise UnsupportedFileTypeError(_NOT_KML)
        return upload

    def read(self, source: Path) -> GeoDataset:
        features: list[SourceFeature] = []
        with gdal_errors_as_read_errors(source):
            for layer in range(len(pyogrio.list_layers(source))):
                features.extend(_placemarks(read_layer(source, layer)))
        return GeoDataset(features=features, crs=KML_CRS)


def _placemarks(layer: geopandas.GeoDataFrame) -> Iterator[SourceFeature]:
    for _record_id, geometry, fields in feature_rows(layer):
        placemark_id = fields.pop(_PLACEMARK_ID_FIELD, None)
        # KML attributes belong to a Placemark, not to a table: a field this Placemark does not
        # have is left out rather than reported as null.
        properties = {
            name: value
            for name, value in fields.items()
            if value is not None and name not in _RENDERING_FIELDS
        }
        yield SourceFeature(source_id=placemark_id, geometry=geometry, properties=properties)


def _root_element(path: Path) -> str | None:
    """The local name of the XML root element, or None if the file is not XML.

    Only the start of the file is parsed. A DOCTYPE is refused: KML needs none, and without a
    DTD there are no entities to expand (billion laughs) or to resolve from outside (XXE).
    """
    root: str | None = None

    def on_doctype(*_declaration: object) -> None:
        raise UnprocessableUploadError("KML files containing a DOCTYPE are not accepted.")

    def on_start_element(name: str, _attributes: object) -> None:
        nonlocal root
        if root is None:
            root = name.rsplit(":", 1)[-1]  # drop a namespace prefix such as "kml:"

    parser = expat.ParserCreate()
    parser.StartDoctypeDeclHandler = on_doctype
    parser.StartElementHandler = on_start_element
    # Malformed XML stops the scan. If the root was already seen this is still a KML upload,
    # and the read step reports what is wrong with it.
    with suppress(expat.ExpatError), path.open("rb") as stream:
        while root is None and (chunk := stream.read(_SNIFF_CHUNK_BYTES)):
            parser.Parse(chunk)
    return root
