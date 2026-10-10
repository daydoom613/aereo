"""DELETE /api/files/{id}/"""

from shapely.geometry import Point, box
from sqlalchemy import func, select

from app.domain import FileFormat
from app.models import Feature
from app.repositories.file_repository import FileRepository
from tests.support import kml_document, placemark

SURVEY_KML = kml_document(placemark(box(77.0, 13.0, 77.01, 13.01)), placemark(Point(77.0, 13.0)))


def stored_features(client, file_id: str) -> int:
    with client.app.state.session_factory() as session:
        return session.scalar(
            select(func.count()).select_from(Feature).where(Feature.file_id == file_id)
        )


def test_deleted_file_is_gone_with_its_measurements(upload, client):
    file_id = upload("survey.kml", SURVEY_KML).json()["id"]
    assert stored_features(client, file_id) == 2

    response = client.delete(f"/api/files/{file_id}/")

    assert response.status_code == 204
    assert response.content == b""
    assert "content-type" not in response.headers
    assert client.get(f"/api/files/{file_id}/").status_code == 404
    assert client.get(f"/api/files/{file_id}/measurements/").status_code == 404
    assert client.get("/api/files/").json()["items"] == []
    assert stored_features(client, file_id) == 0


def test_other_files_are_left_alone(upload, client):
    kept = upload("kept.kml", SURVEY_KML).json()
    removed = upload("removed.kml", SURVEY_KML).json()

    client.delete(f"/api/files/{removed['id']}/")

    assert client.get(kept["links"]["self"]).json() == kept
    assert client.get(kept["links"]["measurements"]).json()["pagination"]["total"] == 2
    assert [item["id"] for item in client.get("/api/files/").json()["items"]] == [kept["id"]]


def test_failed_file_can_be_deleted(upload, client):
    failed = upload("broken.kml", SURVEY_KML[:-30]).json()
    assert failed["status"] == "FAILED"

    assert client.delete(failed["links"]["self"]).status_code == 204
    assert client.get(failed["links"]["self"]).status_code == 404


def test_unknown_id_is_404(client):
    response = client.delete("/api/files/3f1c9a52-6f0e-4b61-9d3e-0c2f6a1b7e44/")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["detail"] == "No uploaded file has this id."


def test_deleting_twice_is_404_the_second_time(upload, client):
    file_id = upload("survey.kml", SURVEY_KML).json()["id"]

    assert client.delete(f"/api/files/{file_id}/").status_code == 204
    assert client.delete(f"/api/files/{file_id}/").status_code == 404


def test_file_still_being_processed_is_409_and_is_kept(client):
    with client.app.state.session_factory() as session:
        file_id = FileRepository(session).add_processing("survey.kml", FileFormat.KML, 10).id

    response = client.delete(f"/api/files/{file_id}/")

    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    assert "still being processed" in response.json()["detail"]
    assert client.get(f"/api/files/{file_id}/").json()["status"] == "PROCESSING"


def test_also_works_without_the_trailing_slash(upload, client):
    file_id = upload("survey.kml", SURVEY_KML).json()["id"]

    response = client.delete(f"/api/files/{file_id}", follow_redirects=False)

    assert response.status_code == 204
