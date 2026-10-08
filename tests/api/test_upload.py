"""POST /api/files/: what is accepted, what is rejected, and what is recorded."""

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Point, box
from sqlalchemy import select

from app.core.config import Settings
from app.main import create_app
from app.models import UploadedFile
from tests.support import (
    folder,
    kml_document,
    layer,
    placemark,
    shapefile_parts,
    shapefile_zip,
    zip_of,
)

PARCEL = box(77.0, 13.0, 77.01, 13.01)
SURVEY_KML = kml_document(placemark(PARCEL, name="Field A"), placemark(Point(77.0, 13.0)))
PARCELS_ZIP = shapefile_zip(layer([PARCEL], name=["Field A"]))


def stored_files(client: TestClient) -> list[UploadedFile]:
    with client.app.state.session_factory() as session:
        return list(session.scalars(select(UploadedFile)))


# --- accepted uploads ------------------------------------------------------------------------


def test_kml_upload_is_processed_and_returned_as_a_created_resource(upload):
    response = upload("survey.kml", SURVEY_KML)

    body = response.json()
    assert response.status_code == 201
    assert response.headers["location"] == f"/api/files/{body['id']}/"
    assert body["filename"] == "survey.kml"
    assert body["format"] == "KML"
    assert body["status"] == "COMPLETED"
    assert body["feature_count"] == 2
    assert body["crs"] == "EPSG:4326"
    assert body["crs_assumed"] is False
    assert body["error"] is None
    assert body["size_bytes"] == len(SURVEY_KML)


def test_zipped_shapefile_upload_is_processed(upload):
    response = upload("parcels.zip", PARCELS_ZIP)

    body = response.json()
    assert response.status_code == 201
    assert body["format"] == "SHAPEFILE"
    assert body["status"] == "COMPLETED"
    assert body["feature_count"] == 1
    assert body["crs"] == "EPSG:4326"


def test_upload_path_also_works_without_the_trailing_slash(client):
    response = client.post(
        "/api/files", files={"file": ("survey.kml", SURVEY_KML)}, follow_redirects=False
    )

    assert response.status_code == 201


def test_extension_is_matched_without_regard_to_case(upload):
    assert upload("SURVEY.KML", SURVEY_KML).status_code == 201


def test_file_with_no_features_completes_with_a_count_of_zero(upload):
    body = upload("empty.kml", kml_document(folder("Nothing here"))).json()

    assert body["status"] == "COMPLETED"
    assert body["feature_count"] == 0


def test_client_filename_is_stored_without_its_path(upload):
    body = upload("C:\\Users\\surveyor\\..\\..\\secret\\survey.kml", SURVEY_KML).json()

    assert body["filename"] == "survey.kml"


def test_shapefile_without_prj_is_flagged_as_an_assumed_crs(upload):
    body = upload("parcels.zip", shapefile_zip(layer([PARCEL]), without=(".prj",))).json()

    assert body["crs"] == "EPSG:4326"
    assert body["crs_assumed"] is True


# --- rejected uploads: a 4xx, and nothing stored ---------------------------------------------


@pytest.mark.parametrize("filename", ["survey.geojson", "parcels.shp", "survey.kmz", "survey"])
def test_unsupported_extension_is_415(upload, client, filename):
    response = upload(filename, SURVEY_KML)

    assert response.status_code == 415
    assert stored_files(client) == []


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("survey.kml", b"plain text, not XML"),
        ("survey.kml", b'<?xml version="1.0"?><gpx></gpx>'),
        ("survey.kml", PARCELS_ZIP),
        ("parcels.zip", SURVEY_KML),
        ("parcels.zip", b""),
    ],
)
def test_content_that_does_not_match_the_extension_is_415(upload, client, filename, content):
    response = upload(filename, content)

    assert response.status_code == 415
    assert stored_files(client) == []


def test_archive_missing_a_required_part_is_422_and_names_it(upload, client):
    response = upload("parcels.zip", shapefile_zip(layer([PARCEL]), without=(".dbf",)))

    assert response.status_code == 422
    assert "parcels.dbf" in response.json()["detail"]
    assert stored_files(client) == []


def test_archive_with_two_shapefiles_is_422(upload):
    both = shapefile_parts(layer([PARCEL]), "parcels") | shapefile_parts(layer([PARCEL]), "roads")

    response = upload("both.zip", zip_of(both))

    assert response.status_code == 422
    assert "2 shapefiles" in response.json()["detail"]


def test_zip_slip_archive_is_422(upload):
    hostile = shapefile_parts(layer([PARCEL])) | {"../../outside.txt": b"escaped"}

    assert upload("parcels.zip", zip_of(hostile)).status_code == 422


def test_kml_with_a_doctype_is_422(upload):
    with_doctype = (
        b'<!DOCTYPE kml [<!ENTITY a "aaaa">]><kml><Document><name>&a;</name></Document></kml>'
    )

    response = upload("survey.kml", with_doctype)

    assert response.status_code == 422
    assert "DOCTYPE" in response.json()["detail"]


def test_request_without_a_file_is_400_and_names_the_field(client):
    response = client.post("/api/files/")

    body = response.json()
    assert response.status_code == 400
    assert body["errors"] == [{"field": "body.file", "message": "Field required"}]


# --- the size limit --------------------------------------------------------------------------


@pytest.fixture
def small_limit_client(settings: Settings):
    limited = settings.model_copy(update={"max_upload_bytes": 2_000})
    with TestClient(create_app(limited)) as test_client:
        yield test_client


def test_upload_over_the_limit_is_413(small_limit_client):
    oversized = kml_document(*[placemark(PARCEL, name=f"Field {n}") for n in range(40)])
    assert len(oversized) > 2_000

    response = small_limit_client.post("/api/files/", files={"file": ("big.kml", oversized)})

    assert response.status_code == 413
    assert response.headers["content-type"] == "application/problem+json"
    assert "2000 bytes" in response.json()["detail"]
    assert stored_files(small_limit_client) == []


def test_chunked_upload_over_the_limit_is_413_even_without_a_declared_length(small_limit_client):
    def body_in_chunks():
        yield b'--b\r\nContent-Disposition: form-data; name="file"; filename="big.kml"\r\n\r\n'
        for _ in range(10):
            yield b"x" * 500
        yield b"\r\n--b--\r\n"

    response = small_limit_client.post(
        "/api/files/",
        content=body_in_chunks(),
        headers={"content-type": "multipart/form-data; boundary=b"},
    )

    assert "content-length" not in response.request.headers
    assert response.status_code == 413
    assert response.headers["content-type"] == "application/problem+json"


def test_upload_under_the_limit_is_accepted(small_limit_client):
    small = kml_document(placemark(Point(77.0, 13.0)))
    assert len(small) < 1_500

    response = small_limit_client.post("/api/files/", files={"file": ("small.kml", small)})

    assert response.status_code == 201


# --- accepted, but the content cannot be read ------------------------------------------------


def test_unreadable_kml_is_stored_as_failed_with_a_reason(upload, client):
    truncated = SURVEY_KML[:-30]

    response = upload("survey.kml", truncated)

    body = response.json()
    assert response.status_code == 201
    assert body["status"] == "FAILED"
    assert body["feature_count"] is None
    assert body["error"].startswith("The file could not be read:")
    assert body["processed_at"] is not None
    assert client.get(response.headers["location"]).json()["status"] == "FAILED"


def test_unreadable_shapefile_is_stored_as_failed_without_leaking_server_paths(upload):
    broken = shapefile_parts(layer([PARCEL])) | {"parcels.shp": b"this is not a shapefile"}

    body = upload("parcels.zip", zip_of(broken)).json()

    assert body["status"] == "FAILED"
    assert "upload-" not in body["error"]  # the temporary directory's name
    assert "\\" not in body["error"]
    assert "/" not in body["error"]


def test_unexpected_error_is_a_500_without_internal_detail_and_the_file_is_marked_failed(
    upload, client, monkeypatch
):
    def explode(*_args, **_kwargs):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr("app.services.file_service.FeatureMeasurer", explode)

    response = upload("survey.kml", SURVEY_KML)

    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"
    assert "secret internal detail" not in response.text
    assert response.json()["detail"] == "An unexpected error occurred."
    assert response.headers["x-request-id"]
    [record] = stored_files(client)
    assert record.status == "FAILED"
    assert record.error == "An unexpected error occurred while processing the file."
