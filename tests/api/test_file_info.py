"""GET /api/files/{id}/"""

from datetime import datetime

from fastapi.testclient import TestClient
from shapely.geometry import Point, box

from app.domain import FileFormat
from app.main import create_app
from app.repositories.file_repository import FileRepository
from tests.support import kml_document, placemark

SURVEY_KML = kml_document(placemark(box(77.0, 13.0, 77.01, 13.01)), placemark(Point(77.0, 13.0)))


def test_returns_the_fields_the_brief_requires(upload, client):
    file_id = upload("survey.kml", SURVEY_KML).json()["id"]

    response = client.get(f"/api/files/{file_id}/")

    body = response.json()
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    # The brief's example: {"id", "filename", "feature_count", "crs", "status"}
    assert body["id"] == file_id
    assert body["filename"] == "survey.kml"
    assert body["feature_count"] == 2
    assert body["crs"] == "EPSG:4326"
    assert body["status"] == "COMPLETED"


def test_links_lead_to_the_file_and_its_measurements(upload, client):
    body = upload("survey.kml", SURVEY_KML).json()

    assert client.get(body["links"]["self"]).json()["id"] == body["id"]
    assert client.get(body["links"]["measurements"]).json()["file_id"] == body["id"]


def test_timestamps_are_utc_and_ordered(upload):
    body = upload("survey.kml", SURVEY_KML).json()

    assert body["created_at"].endswith("Z")
    assert body["processed_at"].endswith("Z")
    assert datetime.fromisoformat(body["created_at"]) <= datetime.fromisoformat(
        body["processed_at"]
    )


def test_also_works_without_the_trailing_slash(upload, client):
    file_id = upload("survey.kml", SURVEY_KML).json()["id"]

    response = client.get(f"/api/files/{file_id}", follow_redirects=False)

    assert response.status_code == 200
    assert response.json()["id"] == file_id


def test_is_idempotent(upload, client):
    file_id = upload("survey.kml", SURVEY_KML).json()["id"]

    assert (
        client.get(f"/api/files/{file_id}/").json() == client.get(f"/api/files/{file_id}/").json()
    )


def test_unknown_id_is_404(client):
    response = client.get("/api/files/3f1c9a52-6f0e-4b61-9d3e-0c2f6a1b7e44/")

    assert response.status_code == 404
    assert response.json()["detail"] == "No uploaded file has this id."


def test_malformed_id_is_404_not_a_validation_error(client):
    assert client.get("/api/files/abc123/").status_code == 404


def test_file_left_processing_by_a_stopped_process_is_failed_at_startup(settings):
    with (
        TestClient(create_app(settings)) as stopped,
        stopped.app.state.session_factory() as session,
    ):
        file_id = FileRepository(session).add_processing("survey.kml", FileFormat.KML, 10).id

    with TestClient(create_app(settings)) as restarted:
        body = restarted.get(f"/api/files/{file_id}/").json()
        measurements = restarted.get(f"/api/files/{file_id}/measurements/")

    assert body["status"] == "FAILED"
    assert body["error"] == "Processing was interrupted before it finished. Upload the file again."
    assert body["processed_at"] is not None
    assert measurements.status_code == 409
