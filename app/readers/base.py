"""What every file reader provides, and the GDAL plumbing they share."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol

import geopandas
from pyogrio.errors import DataLayerError, DataSourceError
from shapely.geometry.base import BaseGeometry

from app.core.errors import GeoFileReadError
from app.domain import GeoDataset
from app.readers.properties import to_json_safe


class GeoFileReader(Protocol):
    def prepare(self, upload: Path, workdir: Path) -> Path:
        """Check the uploaded container and return the path GDAL should open.

        Raises UnsupportedFileTypeError or UnprocessableUploadError: the upload is rejected and
        nothing is stored.
        """
        ...

    def read(self, source: Path) -> GeoDataset:
        """Extract the features and CRS. Raises GeoFileReadError if the content is unreadable."""
        ...


@contextmanager
def gdal_errors_as_read_errors(source: Path) -> Iterator[None]:
    """Report GDAL's failures as GeoFileReadError, with the server's temporary path removed."""
    try:
        yield
    except (DataSourceError, DataLayerError) as error:
        message = _without_directory(str(error), source.parent)
        raise GeoFileReadError(f"The file could not be read: {message}") from error


def read_layer(source: Path, layer: int = 0) -> geopandas.GeoDataFrame:
    # on_invalid="ignore": a geometry GEOS cannot decode (a bare KML LinearRing, for one) comes
    # back as missing instead of aborting the whole layer.
    return geopandas.read_file(
        source, layer=layer, engine="pyogrio", fid_as_index=True, on_invalid="ignore"
    )


def feature_rows(
    frame: geopandas.GeoDataFrame,
) -> Iterator[tuple[Any, BaseGeometry | None, dict[str, Any]]]:
    """Yield (record id, geometry, JSON-safe properties) for every row of a layer."""
    attributes = frame.drop(columns="geometry").to_dict("records")
    for record_id, geometry, row in zip(frame.index, frame.geometry, attributes, strict=True):
        yield record_id, geometry, {str(name): to_json_safe(value) for name, value in row.items()}


def _without_directory(message: str, directory: Path) -> str:
    for spelling in (f"{directory}{os.sep}", f"{directory.as_posix()}/"):
        message = message.replace(spelling, "")
    return message
