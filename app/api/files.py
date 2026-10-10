"""The three endpoints of the assignment, and two that complete the resource: list and delete.

Each route is registered twice: with the trailing slash the brief specifies (the documented
form), and without it, so that a missing slash is served directly instead of being redirected.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Response, UploadFile

from app.api.dependencies import FileServiceDependency
from app.api.errors import status_title
from app.api.presenters import (
    FILES_PATH,
    file_path,
    file_response,
    files_response,
    measurements_response,
)
from app.domain import FeatureFilter, GeometryType, MeasurementStatus
from app.schemas.files import FileResponse, FilesResponse, MeasurementsResponse
from app.schemas.problem import ProblemDetails

router = APIRouter(prefix=FILES_PATH, tags=["files"])

DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 1000
Limit = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]
Offset = Annotated[int, Query(ge=0)]


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


@router.get("", include_in_schema=False)
@router.get("/", summary="List uploaded files", responses=_problems(400))
def list_files(
    service: FileServiceDependency, limit: Limit = DEFAULT_PAGE_SIZE, offset: Offset = 0
) -> FilesResponse:
    """Every uploaded file, newest first. `limit` and `offset` page through `items`."""
    return files_response(service.files(limit, offset), limit, offset)


@router.get("/{file_id}", include_in_schema=False)
@router.get(
    "/{file_id}/", summary="Get information about an uploaded file", responses=_problems(404)
)
def get_file(file_id: str, service: FileServiceDependency) -> FileResponse:
    return file_response(service.get(file_id))


@router.delete("/{file_id}", status_code=204, include_in_schema=False)
@router.delete(
    "/{file_id}/",
    status_code=204,
    summary="Delete an uploaded file and its measurements",
    responses=_problems(404, 409),
)
def delete_file(file_id: str, service: FileServiceDependency) -> Response:
    """A file that is still being processed cannot be deleted: 409."""
    service.delete(file_id)
    # Returned explicitly: the default response class would label the empty body as JSON.
    return Response(status_code=204)


@router.get("/{file_id}/measurements", include_in_schema=False, response_model_exclude_unset=True)
@router.get(
    "/{file_id}/measurements/",
    summary="Get the measurements of a file's features",
    responses=_problems(400, 404, 409),
    # An item's geometry is left unset, and so out of the response, when the request declines it.
    response_model_exclude_unset=True,
)
def get_measurements(
    file_id: str,
    service: FileServiceDependency,
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
    geometry_type: Annotated[
        list[GeometryType] | None,
        Query(description="Only features of this geometry type. Repeat it to allow several."),
    ] = None,
    status: Annotated[
        list[MeasurementStatus] | None,
        Query(description="Only features with this measurement status. Repeat it for several."),
    ] = None,
    include_geometry: Annotated[
        bool, Query(description="`false` leaves `geometry` out of every item.")
    ] = True,
) -> MeasurementsResponse:
    """One item per feature: its index, id, geometry, CRS and properties, with its measurement.

    Polygons report area in square metres and lines report length in metres. `limit` and
    `offset` page through `items`. `geometry_type` and `status` narrow `items`, and
    `pagination.total` counts what they leave; `summary` always covers the whole file.
    """
    # dict.fromkeys drops a value given twice and keeps the order they were given in.
    feature_filter = FeatureFilter(
        geometry_types=tuple(dict.fromkeys(geometry_type or ())),
        statuses=tuple(dict.fromkeys(status or ())),
    )
    page = service.measurements(file_id, limit, offset, feature_filter, include_geometry)
    return measurements_response(page, limit, offset, feature_filter, include_geometry)
