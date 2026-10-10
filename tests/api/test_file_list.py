"""GET /api/files/"""

import pytest
from shapely.geometry import Point

from tests.support import kml_document, placemark

POINT_KML = kml_document(placemark(Point(77.0, 13.0)))


def test_no_uploads_is_an_empty_page(client):
    response = client.get("/api/files/")

    assert response.status_code == 200
    assert response.json() == {
        "pagination": {"limit": 100, "offset": 0, "total": 0},
        "links": {"self": "/api/files/?limit=100&offset=0", "next": None, "prev": None},
        "items": [],
    }


def test_lists_every_upload_newest_first(upload, client):
    first = upload("first.kml", POINT_KML).json()
    second = upload("second.kml", POINT_KML).json()

    body = client.get("/api/files/").json()

    assert [item["filename"] for item in body["items"]] == ["second.kml", "first.kml"]
    assert body["pagination"]["total"] == 2
    # Each item is the same resource the file's own URL returns.
    assert body["items"] == [second, first]
    assert client.get(body["items"][0]["links"]["self"]).json() == second


def test_a_failed_upload_is_listed_with_its_error(upload, client):
    upload("broken.kml", POINT_KML[:-30])

    [item] = client.get("/api/files/").json()["items"]

    assert item["status"] == "FAILED"
    assert item["error"].startswith("The file could not be read")


def test_limit_and_offset_select_a_page_and_links_lead_to_its_neighbours(upload, client):
    for number in range(5):
        upload(f"{number}.kml", POINT_KML)

    middle = client.get("/api/files/", params={"limit": 2, "offset": 2}).json()

    assert [item["filename"] for item in middle["items"]] == ["2.kml", "1.kml"]
    assert middle["pagination"] == {"limit": 2, "offset": 2, "total": 5}
    assert middle["links"]["self"] == "/api/files/?limit=2&offset=2"

    newer = client.get(middle["links"]["prev"]).json()
    older = client.get(middle["links"]["next"]).json()
    assert [item["filename"] for item in newer["items"]] == ["4.kml", "3.kml"]
    assert newer["links"]["prev"] is None
    assert [item["filename"] for item in older["items"]] == ["0.kml"]
    assert older["links"]["next"] is None


def test_offset_past_the_end_is_an_empty_page_not_an_error(upload, client):
    upload("only.kml", POINT_KML)

    body = client.get("/api/files/", params={"offset": 50}).json()

    assert body["items"] == []
    assert body["pagination"]["total"] == 1


@pytest.mark.parametrize(
    "params", [{"limit": 0}, {"limit": 1001}, {"offset": -1}, {"limit": "many"}]
)
def test_out_of_range_paging_is_400_and_names_the_parameter(client, params):
    response = client.get("/api/files/", params=params)

    assert response.status_code == 400
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["errors"][0]["field"] == f"query.{next(iter(params))}"


def test_also_works_without_the_trailing_slash(upload, client):
    upload("only.kml", POINT_KML)

    response = client.get("/api/files", follow_redirects=False)

    assert response.status_code == 200
    assert response.json()["pagination"]["total"] == 1
