"""Expected failures. Each one maps to a single HTTP status; one handler renders them all."""

from __future__ import annotations


class AppError(Exception):
    status_code = 500

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class UnsupportedFileTypeError(AppError):
    """The upload is not a .zip or .kml, or its content is not what its extension claims."""

    status_code = 415


class UnprocessableUploadError(AppError):
    """A real zip or KML that cannot be accepted: unsafe, incomplete or ambiguous."""

    status_code = 422


class UploadedFileNotFoundError(AppError):
    status_code = 404


class FileNotReadyError(AppError):
    """The file exists, but its current status does not allow the request.

    A file that was not processed successfully has no measurements; a file still being
    processed cannot be deleted.
    """

    status_code = 409


class GeoFileReadError(Exception):
    """An accepted upload whose content could not be read.

    Not an HTTP error: the service records it on the file, which becomes FAILED.
    """
