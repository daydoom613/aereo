"""The three endpoints of the assignment.

Each route is registered twice: with the trailing slash the brief specifies (the documented
form), and without it, so that a missing slash is served directly instead of being redirected.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Response, UploadFile

from app.api.dependencies import FileServiceDependency
from app.api.errors import status_title
from app.api.presenters import FILES_PATH, file_path, file_response, measurements_response
from app.schemas.files import FileResponse, MeasurementsResponse
from app.schemas.problem import ProblemDetails

router = APIRouter(prefix=FILES_PATH, tags=["files"])

DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 1000


def _problems(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI entries for the error statuses a route can return."""
    return {
        status: {"model": ProblemDetails, "description": status_title(status)}
        for status in statuses
    }


@router.post("", status_code=201, include_in_schema=False)
@router.post(
    "/",
    status_code=201,
    summary="Upload and process a geospatial file",
    responses=_problems(400, 413, 415, 422),
)
def upload_file(
    file: UploadFile, response: Response, service: FileServiceDependency
) -> FileResponse:
    """Accepts a `.kml` file, or a `.zip` containing one shapefile (`.shp`, `.shx`, `.dbf`).

    The file is read and every feature measured before the response is sent. The response
    status says whether the upload was accepted; the `status` field says how processing ended.
    """
    record = service.upload(file.filename, file.file)
    response.headers["Location"] = file_path(record.id)
    return file_response(record)


@router.get("/{file_id}", include_in_schema=False)
@router.get(
    "/{file_id}/", summary="Get information about an uploaded file", responses=_problems(404)
)
def get_file(file_id: str, service: FileServiceDependency) -> FileResponse:
    return file_response(service.get(file_id))


@router.get("/{file_id}/measurements", include_in_schema=False)
@router.get(
    "/{file_id}/measurements/",
    summary="Get the measurements of a file's features",
    responses=_problems(400, 404, 409),
)
def get_measurements(
    file_id: str,
    service: FileServiceDependency,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MeasurementsResponse:
    """One item per feature: its index, id, geometry, CRS and properties, with its measurement.

    Polygons report area in square metres and lines report length in metres. `summary` covers
    the whole file; `limit` and `offset` page through `items`.
    """
    return measurements_response(service.measurements(file_id, limit, offset), limit, offset)
