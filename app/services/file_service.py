"""Uploading a geospatial file, and reading back what was found in it."""

from __future__ import annotations

import logging
import shutil
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from tempfile import TemporaryDirectory
from typing import BinaryIO

from app.core.errors import FileNotReadyError, GeoFileReadError, UploadedFileNotFoundError
from app.domain import FeatureFilter, FileFormat, FileStatus, MeasurementSummary
from app.geometry.measurement import FeatureMeasurer
from app.geometry.projection import crs_label
from app.models import Feature, UploadedFile
from app.readers.base import GeoFileReader
from app.readers.registry import EXTENSION_BY_FORMAT, format_of
from app.repositories.file_repository import FileRepository

logger = logging.getLogger(__name__)

_MAX_FILENAME_LENGTH = 255
_UNNAMED_UPLOAD = "upload"
_UNEXPECTED_FAILURE = "An unexpected error occurred while processing the file."


@dataclass(frozen=True)
class FilePage:
    """One page of uploaded files, with the number of files there are in all."""

    files: Sequence[UploadedFile]
    total: int


@dataclass(frozen=True)
class MeasurementPage:
    """One page of a file's measured features, with totals for the whole file.

    `matching` is the number of features that pass the request's filter, over every page.
    """

    file: UploadedFile
    summary: MeasurementSummary
    features: Sequence[Feature]
    matching: int


class FileService:
    def __init__(
        self, repository: FileRepository, readers: Mapping[FileFormat, GeoFileReader]
    ) -> None:
        self._repository = repository
        self._readers = readers

    def upload(self, client_filename: str | None, content: BinaryIO) -> UploadedFile:
        """Check, record, read and measure an upload.

        Raises an AppError if the upload is rejected; nothing is stored then. Once the upload
        is accepted a record always exists, and its status says how processing ended.
        """
        filename = _display_name(client_filename)
        file_format = format_of(filename)
        reader = self._readers[file_format]

        # ignore_cleanup_errors: on Windows a file GDAL has only just closed can briefly resist
        # deletion. That must not turn a successful upload into an error.
        with TemporaryDirectory(prefix="upload-", ignore_cleanup_errors=True) as directory:
            workdir = Path(directory)
            # Fixed names only: nothing the client sent is ever used as a path.
            upload_path = workdir / f"upload{EXTENSION_BY_FORMAT[file_format]}"
            with upload_path.open("wb") as saved:
                shutil.copyfileobj(content, saved)
            source = reader.prepare(upload_path, workdir)

            record = self._repository.add_processing(
                filename, file_format, upload_path.stat().st_size
            )
            self._process(record, reader, source)
        return record

    def get(self, file_id: str) -> UploadedFile:
        record = self._repository.get(file_id)
        if record is None:
            raise UploadedFileNotFoundError("No uploaded file has this id.")
        return record

    def files(self, limit: int, offset: int) -> FilePage:
        return FilePage(
            files=self._repository.files(limit, offset), total=self._repository.count_files()
        )

    def delete(self, file_id: str) -> None:
        record = self.get(file_id)
        if record.status is FileStatus.PROCESSING:
            # The request that uploaded it is still writing to this record.
            raise FileNotReadyError(
                "The file is still being processed. It can be deleted once that has ended."
            )
        self._repository.remove(record)
        logger.info("file deleted", extra={"file_id": file_id})

    def measurements(
        self,
        file_id: str,
        limit: int,
        offset: int,
        feature_filter: FeatureFilter,
        include_geometry: bool,
    ) -> MeasurementPage:
        record = self.get(file_id)
        if record.status is FileStatus.FAILED:
            raise FileNotReadyError(
                f"The file could not be processed, so it has no measurements. {record.error}"
            )
        if record.status is not FileStatus.COMPLETED:
            raise FileNotReadyError("The file is still being processed.")
        return MeasurementPage(
            file=record,
            summary=self._repository.summary(file_id),
            features=self._repository.features(
                file_id, limit, offset, feature_filter, include_geometry
            ),
            matching=self._repository.count_features(file_id, feature_filter),
        )

    def _process(self, record: UploadedFile, reader: GeoFileReader, source: Path) -> None:
        started = time.perf_counter()
        try:
            dataset = reader.read(source)
            measurer = FeatureMeasurer(dataset.crs, dataset.crs_assumed)
            measured = [
                (feature, measurer.measure(feature.geometry)) for feature in dataset.features
            ]
            self._repository.complete(record, crs_label(dataset.crs), dataset.crs_assumed, measured)
        except GeoFileReadError as error:
            self._repository.fail(record, str(error))
            logger.warning("file could not be read", extra={"file_id": record.id})
            return
        except Exception:
            # A bug or an outage, not a bad file. Leave a truthful record, then let it surface.
            self._repository.fail(record, _UNEXPECTED_FAILURE)
            raise
        logger.info(
            "file processed",
            extra={
                "file_id": record.id,
                "format": record.format.value,
                "feature_count": record.feature_count,
                "duration_ms": round((time.perf_counter() - started) * 1000),
            },
        )


def _display_name(client_filename: str | None) -> str:
    """The client's file name, reduced to something safe to store and show.

    It is never used as a path. The Windows path class is used because it treats both / and \\
    as separators, so a full path sent by any client is cut down to its last component.
    """
    name = PureWindowsPath(client_filename or "").name
    printable = "".join(character for character in name if character.isprintable()).strip()
    return printable[-_MAX_FILENAME_LENGTH:] or _UNNAMED_UPLOAD
