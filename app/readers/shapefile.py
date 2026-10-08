"""Reading a shapefile delivered as a zip archive."""

from __future__ import annotations

import math
import shutil
import zipfile
import zlib
from pathlib import Path, PurePosixPath, PureWindowsPath

import geopandas
from pyproj import CRS

from app.core.errors import UnprocessableUploadError, UnsupportedFileTypeError
from app.domain import GeoDataset, SourceFeature
from app.geometry.projection import WGS84
from app.readers.base import feature_rows, gdal_errors_as_read_errors, read_layer

# The three files the Shapefile specification requires, then the ones it allows.
_REQUIRED_PARTS = (".shp", ".shx", ".dbf")
_OPTIONAL_PARTS = (".prj", ".cpg")
# Parts are extracted under this fixed name, so no name from the archive ever becomes a path.
_EXTRACTED_NAME = "shapefile"
_ENCRYPTED_FLAG = 0x1


class ShapefileReader:
    def __init__(self, max_uncompressed_bytes: int, max_entries: int) -> None:
        self._max_uncompressed_bytes = max_uncompressed_bytes
        self._max_entries = max_entries

    def prepare(self, upload: Path, workdir: Path) -> Path:
        if not zipfile.is_zipfile(upload):
            raise UnsupportedFileTypeError("The file is not a zip archive.")
        try:
            with zipfile.ZipFile(upload) as archive:
                parts = self._shapefile_parts(archive)
                for extension, entry in parts.items():
                    target = workdir / f"{_EXTRACTED_NAME}{extension}"
                    with archive.open(entry) as packed, target.open("wb") as unpacked:
                        shutil.copyfileobj(packed, unpacked)
        except (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError) as error:
            # NotImplementedError is how zipfile reports a compression method it cannot read.
            raise UnprocessableUploadError(
                "The zip archive is corrupt or uses an unsupported compression method."
            ) from error
        return workdir / f"{_EXTRACTED_NAME}.shp"

    def read(self, source: Path) -> GeoDataset:
        with gdal_errors_as_read_errors(source):
            layer = read_layer(source)
        crs, assumed = _declared_or_assumed_crs(layer)
        features = [
            SourceFeature(source_id=str(record_number), geometry=geometry, properties=properties)
            for record_number, geometry, properties in feature_rows(layer)
        ]
        return GeoDataset(features=features, crs=crs, crs_assumed=assumed)

    def _shapefile_parts(self, archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
        """The archive entries that make up its one shapefile, keyed by extension."""
        entries = [entry for entry in archive.infolist() if not entry.is_dir()]
        self._reject_unsafe(entries)

        candidates = [entry for entry in entries if not _is_archive_debris(entry.filename)]
        return _parts_of(_only_shapefile(candidates), candidates)

    def _reject_unsafe(self, entries: list[zipfile.ZipInfo]) -> None:
        if len(entries) > self._max_entries:
            raise UnprocessableUploadError(
                f"The archive has more than {self._max_entries} entries."
            )
        if sum(entry.file_size for entry in entries) > self._max_uncompressed_bytes:
            raise UnprocessableUploadError("The archive is too large when uncompressed.")
        for entry in entries:
            if _escapes_the_archive(entry.filename):
                raise UnprocessableUploadError(
                    "The archive contains an entry with an absolute or parent-relative path."
                )
            if entry.flag_bits & _ENCRYPTED_FLAG:
                raise UnprocessableUploadError("Encrypted archives are not accepted.")


def _only_shapefile(entries: list[zipfile.ZipInfo]) -> zipfile.ZipInfo:
    shapefiles = [entry for entry in entries if _extension(entry.filename) == ".shp"]
    if not shapefiles:
        raise UnprocessableUploadError("The archive contains no .shp file.")
    if len(shapefiles) > 1:
        raise UnprocessableUploadError(
            f"The archive contains {len(shapefiles)} shapefiles. Upload one per archive."
        )
    return shapefiles[0]


def _parts_of(
    shapefile: zipfile.ZipInfo, entries: list[zipfile.ZipInfo]
) -> dict[str, zipfile.ZipInfo]:
    """The entries sharing the .shp's folder and name, keyed by extension."""
    base = _path_without_extension(shapefile.filename)
    parts = {
        _extension(entry.filename): entry
        for entry in entries
        if _path_without_extension(entry.filename) == base
        and _extension(entry.filename) in _REQUIRED_PARTS + _OPTIONAL_PARTS
    }
    for extension in _REQUIRED_PARTS:
        if extension not in parts:
            stem = PurePosixPath(shapefile.filename).stem
            raise UnprocessableUploadError(
                f"The archive is missing {stem}{extension}, which a shapefile requires."
            )
    return parts


def _declared_or_assumed_crs(layer: geopandas.GeoDataFrame) -> tuple[CRS | None, bool]:
    """The CRS from the .prj; without one, WGS 84 if the coordinates could be degrees.

    Returns the CRS and whether it was assumed. Never guesses silently: an assumption is
    reported, and coordinates that cannot be degrees leave the CRS unknown.
    """
    if layer.crs is not None:
        return layer.crs, False
    west, south, east, north = layer.total_bounds
    all_finite = all(math.isfinite(edge) for edge in (west, south, east, north))
    could_be_degrees = all_finite and -180 <= west <= east <= 180 and -90 <= south <= north <= 90
    return (WGS84, True) if could_be_degrees else (None, False)


def _extension(name: str) -> str:
    return PurePosixPath(name).suffix.lower()


def _path_without_extension(name: str) -> str:
    """What the parts of one shapefile share: PARCELS.SHP and parcels.dbf belong together."""
    return str(PurePosixPath(name).with_suffix("")).lower()


def _is_archive_debris(name: str) -> bool:
    """Files macOS adds to zips, which would otherwise look like a second shapefile."""
    path = PurePosixPath(name)
    return "__MACOSX" in path.parts or path.name.startswith("._")


def _escapes_the_archive(name: str) -> bool:
    """True for names that would land outside the extraction directory (zip-slip)."""
    as_posix = PurePosixPath(name.replace("\\", "/"))
    has_drive = bool(PureWindowsPath(name).drive)
    return as_posix.is_absolute() or has_drive or ".." in as_posix.parts
