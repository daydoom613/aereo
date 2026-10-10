"""GET /api/files/{id}/measurements/, end to end: file in, measured features out.

The accuracy tests upload shapes whose true size is known because they were built in metres.
"""

import pytest
import shapely
from shapely.geometry import GeometryCollection, LineString, Point, Polygon, box, shape

from app.domain import FileFormat
from app.repositories.file_repository import FileRepository
from tests.support import (
    SQUARE_1KM,
    SQUARE_1KM_AREA,
    UTM_43N,
    kml_document,
    layer,
    placemark,
    reproject,
    shapefile_zip,
    to_wgs84,
)

LINE_5KM = LineString([(500_000, 1_400_000), (503_000, 1_404_000)])
PEG = Point(500_500, 1_400_500)

SURVEY_KML = kml_document(
    placemark(to_wgs84(SQUARE_1KM), name="Field A", placemark_id="pm-1", data={"crop": "ragi"}),
    placemark(to_wgs84(LINE_5KM), name="Flight line"),
    placemark(to_wgs84(PEG), name="Control point"),
)


@pytest.fixture
def measurements(upload, client):
    """Upload a file and return the body of its measurements endpoint."""

    def fetch(filename: str, content: bytes, **params) -> dict:
        file_id = upload(filename, content).json()["id"]
        response = client.get(f"/api/files/{file_id}/measurements/", params=params)
        assert response.status_code == 200, response.text
        return response.json()

    return fetch


# --- accuracy --------------------------------------------------------------------------------


def test_kml_polygon_area_and_line_length_match_the_known_values(measurements):
    area, length, point = (
        item["measurement"] for item in measurements("s.kml", SURVEY_KML)["items"]
    )

    assert area["type"] == "AREA"
    assert area["value"] == pytest.approx(SQUARE_1KM_AREA, rel=1e-6)
    assert area["unit"] == "m2"
    assert area["method"] == "PROJECTED"
    assert area["projected_crs"] == "EPSG:32643"
    assert area["status"] == "MEASURED"

    assert length["type"] == "LENGTH"
    assert length["value"] == pytest.approx(5000.0, rel=1e-6)
    assert length["unit"] == "m"

    assert point == {
        "type": None,
        "value": None,
        "unit": None,
        "method": None,
        "projected_crs": None,
        "status": "NOT_REQUIRED",
        "reason": None,
        "geometry_repaired": False,
    }


def test_shapefile_in_geographic_coordinates_is_projected_before_measuring(measurements):
    archive = shapefile_zip(layer([to_wgs84(SQUARE_1KM)], name=["Field A"]))

    body = measurements("parcels.zip", archive)

    assert body["crs"] == "EPSG:4326"
    assert body["items"][0]["measurement"]["value"] == pytest.approx(SQUARE_1KM_AREA, rel=1e-6)
    assert body["items"][0]["measurement"]["projected_crs"] == "EPSG:32643"


def test_shapefile_already_in_utm_is_measured_exactly(measurements):
    archive = shapefile_zip(layer([SQUARE_1KM], crs=UTM_43N))

    body = measurements("parcels.zip", archive)

    assert body["crs"] == "EPSG:32643"
    assert body["items"][0]["crs"] == "EPSG:32643"
    assert body["items"][0]["measurement"]["value"] == SQUARE_1KM_AREA
    assert body["items"][0]["measurement"]["projected_crs"] == "EPSG:32643"


def test_shapefile_of_lines_reports_length(measurements):
    archive = shapefile_zip(layer([to_wgs84(LINE_5KM)], name=["Flight line"]))

    measurement = measurements("lines.zip", archive)["items"][0]["measurement"]

    assert measurement["type"] == "LENGTH"
    assert measurement["value"] == pytest.approx(5000.0, rel=1e-6)


def test_shapefile_in_web_mercator_is_not_measured_in_web_mercator(measurements):
    in_web_mercator = reproject(SQUARE_1KM, UTM_43N, 3857)
    archive = shapefile_zip(layer([in_web_mercator], crs=3857))

    body = measurements("web_map_export.zip", archive)

    assert body["crs"] == "EPSG:3857"
    assert body["items"][0]["measurement"]["value"] == pytest.approx(SQUARE_1KM_AREA, rel=1e-6)
    assert body["items"][0]["measurement"]["projected_crs"] == "EPSG:32643"


def test_shapefile_without_prj_is_measured_on_the_flagged_assumption(measurements):
    archive = shapefile_zip(layer([to_wgs84(SQUARE_1KM)]), without=(".prj",))

    body = measurements("parcels.zip", archive)

    assert body["items"][0]["measurement"]["value"] == pytest.approx(SQUARE_1KM_AREA, rel=1e-6)


def test_shapefile_without_prj_drawn_in_metres_is_not_measured_as_degrees(upload, client):
    plot_on_a_site_grid = box(10, 10, 60, 50)  # 50 m x 40 m
    archive = shapefile_zip(layer([plot_on_a_site_grid]), without=(".prj",))

    file = upload("plot.zip", archive).json()
    body = client.get(file["links"]["measurements"]).json()

    assert file["status"] == "COMPLETED"
    assert file["crs_assumed"] is True
    assert body["items"][0]["measurement"]["status"] == "UNSUPPORTED"
    assert body["items"][0]["measurement"]["value"] is None
    assert "probably not degrees" in body["items"][0]["measurement"]["reason"]
    assert body["summary"]["total_area_m2"] == 0.0


def test_shapefile_with_an_unknown_crs_completes_but_measures_nothing(upload, client):
    archive = shapefile_zip(layer([SQUARE_1KM], crs=UTM_43N), without=(".prj",))

    file = upload("parcels.zip", archive).json()
    body = client.get(file["links"]["measurements"]).json()

    assert file["status"] == "COMPLETED"
    assert file["crs"] is None
    assert body["items"][0]["measurement"]["status"] == "UNSUPPORTED"
    assert body["items"][0]["measurement"]["reason"] == "unknown CRS"
    assert body["summary"]["unsupported"] == 1


def test_large_feature_is_measured_on_the_ellipsoid_and_says_so(measurements):
    region = box(70.0, 10.0, 80.0, 20.0)

    measurement = measurements("region.kml", kml_document(placemark(region)))["items"][0][
        "measurement"
    ]

    assert measurement["method"] == "GEODESIC"
    assert measurement["projected_crs"] is None
    assert measurement["status"] == "MEASURED"
    assert measurement["value"] == pytest.approx(1.19e12, rel=0.01)


# --- every feature is identified (requirement 3) ---------------------------------------------


def test_each_item_identifies_the_feature(measurements):
    first = measurements("s.kml", SURVEY_KML)["items"][0]

    assert first["feature_index"] == 0
    assert first["source_id"] == "pm-1"
    assert first["geometry_type"] == "Polygon"
    assert first["crs"] == "EPSG:4326"
    assert first["properties"] == {"Name": "Field A", "crop": "ragi"}
    assert first["geometry"]["type"] == "Polygon"
    returned = shapely.force_2d(shape(first["geometry"]))
    assert returned.equals_exact(to_wgs84(SQUARE_1KM), tolerance=1e-12)


def test_feature_indexes_run_from_zero_in_file_order(measurements):
    items = measurements("s.kml", SURVEY_KML)["items"]

    assert [item["feature_index"] for item in items] == [0, 1, 2]
    assert [item["properties"]["Name"] for item in items] == [
        "Field A",
        "Flight line",
        "Control point",
    ]


def test_shapefile_features_carry_their_record_number_and_attributes(measurements):
    archive = shapefile_zip(
        layer([to_wgs84(SQUARE_1KM), to_wgs84(SQUARE_1KM)], name=["A", "B"], plot_no=[41, 42])
    )

    second = measurements("parcels.zip", archive)["items"][1]

    assert second["feature_index"] == 1
    assert second["source_id"] == "1"
    assert second["properties"] == {"name": "B", "plot_no": 42}


# --- unsupported geometries are handled, not fatal (requirement 3) ---------------------------


def test_unsupported_geometries_are_reported_and_the_rest_is_still_measured(measurements):
    bare_ring = (
        "<LinearRing><coordinates>77,13 77.01,13 77.01,13.01 77,13</coordinates></LinearRing>"
    )
    content = kml_document(
        placemark(
            GeometryCollection([Point(77.0, 13.0), LineString([(77.0, 13.0), (77.1, 13.1)])])
        ),
        placemark(name="Ring", geometry_xml=bare_ring),
        placemark(None, name="Note"),
        placemark(to_wgs84(SQUARE_1KM), name="Field A"),
    )

    body = measurements("mixed.kml", content)

    collection, ring, note, field = body["items"]
    assert collection["geometry_type"] == "GeometryCollection"
    assert collection["measurement"]["status"] == "UNSUPPORTED"
    assert "GeometryCollection" in collection["measurement"]["reason"]
    assert ring["geometry"] is None
    assert ring["measurement"]["status"] == "UNSUPPORTED"
    assert note["measurement"]["reason"] == "The feature has no readable geometry."
    assert field["measurement"]["status"] == "MEASURED"
    assert body["summary"]["unsupported"] == 3
    assert body["summary"]["measured"] == 1


def test_self_crossing_polygon_is_repaired_measured_and_flagged(measurements):
    bow_tie = Polygon(
        [(500_000, 1_400_000), (501_000, 1_401_000), (501_000, 1_400_000), (500_000, 1_401_000)]
    )

    measurement = measurements("b.kml", kml_document(placemark(to_wgs84(bow_tie))))["items"][0][
        "measurement"
    ]

    assert measurement["geometry_repaired"] is True
    assert measurement["value"] == pytest.approx(500_000.0, rel=1e-6)


# --- summary and pagination ------------------------------------------------------------------


def test_summary_totals_cover_the_whole_file(measurements):
    summary = measurements("s.kml", SURVEY_KML, limit=1)["summary"]

    assert summary["total_area_m2"] == pytest.approx(SQUARE_1KM_AREA, rel=1e-6)
    assert summary["total_length_m"] == pytest.approx(5000.0, rel=1e-6)
    assert summary == summary | {"measured": 2, "not_required": 1, "unsupported": 0, "failed": 0}


def test_file_with_no_features_has_an_empty_page_and_zero_totals(measurements):
    body = measurements("empty.kml", kml_document())

    assert body["items"] == []
    assert body["pagination"] == {"limit": 100, "offset": 0, "total": 0}
    assert body["summary"] == {
        "total_area_m2": 0.0,
        "total_length_m": 0.0,
        "measured": 0,
        "not_required": 0,
        "unsupported": 0,
        "failed": 0,
    }


def test_limit_and_offset_select_a_page_and_links_lead_to_its_neighbours(upload, client):
    many = kml_document(*[placemark(Point(77.0 + n / 100, 13.0), name=f"P{n}") for n in range(5)])
    file_id = upload("points.kml", many).json()["id"]
    base = f"/api/files/{file_id}/measurements/"

    middle = client.get(base, params={"limit": 2, "offset": 2}).json()

    assert [item["feature_index"] for item in middle["items"]] == [2, 3]
    assert middle["pagination"] == {"limit": 2, "offset": 2, "total": 5}
    assert middle["links"]["self"] == f"{base}?limit=2&offset=2"
    assert middle["links"]["file"] == f"/api/files/{file_id}/"

    first = client.get(middle["links"]["prev"]).json()
    last = client.get(middle["links"]["next"]).json()
    assert [item["feature_index"] for item in first["items"]] == [0, 1]
    assert first["links"]["prev"] is None
    assert [item["feature_index"] for item in last["items"]] == [4]
    assert last["links"]["next"] is None


def test_offset_past_the_end_is_an_empty_page_not_an_error(measurements):
    body = measurements("s.kml", SURVEY_KML, offset=50)

    assert body["items"] == []
    assert body["pagination"]["total"] == 3


@pytest.mark.parametrize(
    "params", [{"limit": 0}, {"limit": 1001}, {"offset": -1}, {"limit": "many"}]
)
def test_out_of_range_paging_is_400_and_names_the_parameter(upload, client, params):
    file_id = upload("s.kml", SURVEY_KML).json()["id"]

    response = client.get(f"/api/files/{file_id}/measurements/", params=params)

    assert response.status_code == 400
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["errors"][0]["field"] == f"query.{next(iter(params))}"


def test_the_largest_page_size_is_accepted(measurements):
    assert measurements("s.kml", SURVEY_KML, limit=1000)["pagination"]["limit"] == 1000


def test_also_works_without_the_trailing_slash(upload, client):
    file_id = upload("s.kml", SURVEY_KML).json()["id"]

    response = client.get(f"/api/files/{file_id}/measurements", follow_redirects=False)

    assert response.status_code == 200


# --- files without measurements --------------------------------------------------------------


def test_unknown_file_is_404(client):
    assert client.get("/api/files/no-such-file/measurements/").status_code == 404


def test_failed_file_is_409_and_carries_the_stored_reason(upload, client):
    failed = upload("survey.kml", SURVEY_KML[:-30]).json()

    response = client.get(failed["links"]["measurements"])

    assert response.status_code == 409
    assert failed["error"] in response.json()["detail"]


def test_file_still_being_processed_is_409(client):
    with client.app.state.session_factory() as session:
        record = FileRepository(session).add_processing("survey.kml", FileFormat.KML, 10)

    response = client.get(f"/api/files/{record.id}/measurements/")

    assert response.status_code == 409
    assert response.json()["detail"] == "The file is still being processed."
