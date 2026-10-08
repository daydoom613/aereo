"""Which reader handles which upload."""

from __future__ import annotations

from pathlib import PurePosixPath

from app.core.config import Settings
from app.core.errors import UnsupportedFileTypeError
from app.domain import FileFormat
from app.readers.base import GeoFileReader
from app.readers.kml import KmlReader
from app.readers.shapefile import ShapefileReader

EXTENSION_BY_FORMAT = {FileFormat.KML: ".kml", FileFormat.SHAPEFILE: ".zip"}
_FORMAT_BY_EXTENSION = {extension: fmt for fmt, extension in EXTENSION_BY_FORMAT.items()}


def format_of(filename: str) -> FileFormat:
    extension = PurePosixPath(filename).suffix.lower()
    if extension not in _FORMAT_BY_EXTENSION:
        raise UnsupportedFileTypeError(
            "Only .kml files and .zip archives containing a shapefile are accepted."
        )
    return _FORMAT_BY_EXTENSION[extension]


def build_readers(settings: Settings) -> dict[FileFormat, GeoFileReader]:
    return {
        FileFormat.KML: KmlReader(),
        FileFormat.SHAPEFILE: ShapefileReader(
            max_uncompressed_bytes=settings.max_archive_uncompressed_bytes,
            max_entries=settings.max_archive_entries,
        ),
    }
