"""The error format, request ids, the health check and the generated API documentation."""

import io
import json
import logging

from shapely.geometry import Point

from app.core.logging import JsonFormatter, request_id_var
from tests.support import kml_document, placemark


def test_errors_are_problem_details(client):
    response = client.get("/api/files/no-such-file/")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "about:blank",
        "title": "Not Found",
        "status": 404,
        "detail": "No uploaded file has this id.",
        "instance": "/api/files/no-such-file/",
    }


def test_unknown_path_uses_the_same_error_format(client):
    response = client.get("/api/nothing-here/")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["title"] == "Not Found"


def test_wrong_method_uses_the_same_error_format_and_lists_what_is_allowed(client):
    response = client.delete("/api/files/")

    assert response.status_code == 405
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["allow"] == "POST"


def test_status_titles_follow_the_current_http_standard(upload):
    response = upload("parcels.zip", b"PK\x05\x06" + bytes(18))  # a valid, empty zip archive

    assert response.status_code == 422
    assert response.json()["title"] == "Unprocessable Content"


def test_every_response_carries_a_request_id(client):
    generated = client.get("/health").headers["x-request-id"]

    assert len(generated) == 32
    assert client.get("/health").headers["x-request-id"] != generated


def test_a_request_id_sent_by_the_client_is_kept(client):
    response = client.get("/api/files/missing/", headers={"X-Request-ID": "trace-42.a_b"})

    assert response.headers["x-request-id"] == "trace-42.a_b"


def test_an_unsafe_request_id_is_replaced(client):
    response = client.get("/health", headers={"X-Request-ID": 'bad"id with spaces'})

    assert response.headers["x-request-id"] != 'bad"id with spaces'
    assert len(response.headers["x-request-id"]) == 32


def test_log_lines_are_json_with_the_request_id_and_extra_fields():
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "file %s", ("done",), None)
    record.file_id = "abc"
    token = request_id_var.set("req-1")
    try:
        entry = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)

    assert entry["message"] == "file done"
    assert entry["level"] == "INFO"
    assert entry["request_id"] == "req-1"
    assert entry["file_id"] == "abc"
    assert entry["time"].endswith("+00:00")


def test_processing_a_file_is_logged_with_its_id_and_the_request_id(upload):
    captured = io.StringIO()
    handler = logging.StreamHandler(captured)
    handler.setFormatter(JsonFormatter())
    logging.getLogger("app").addHandler(handler)
    try:
        response = upload("p.kml", kml_document(placemark(Point(77.0, 13.0))))
    finally:
        logging.getLogger("app").removeHandler(handler)

    entries = [json.loads(line) for line in captured.getvalue().splitlines()]
    [processed] = [entry for entry in entries if entry["message"] == "file processed"]
    assert processed["file_id"] == response.json()["id"]
    assert processed["feature_count"] == 1
    assert processed["request_id"] == response.headers["x-request-id"]


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_documents_exactly_the_paths_of_the_brief(client):
    schema = client.get("/openapi.json").json()

    assert sorted(schema["paths"]) == [
        "/api/files/",
        "/api/files/{file_id}/",
        "/api/files/{file_id}/measurements/",
        "/health",
    ]
    assert "post" in schema["paths"]["/api/files/"]
    assert client.get("/docs").status_code == 200
