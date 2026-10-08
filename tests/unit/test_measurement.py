"""Measurement rules and CRS handling, tested on shapes whose true size is known.

Shapes are built in metres in a UTM zone and converted to the CRS under test, so the expected
area or length is known before the code runs.
"""

import pytest
from pyproj import CRS
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
    box,
)

from app.domain import MeasurementMethod, MeasurementStatus, MeasurementType
from app.geometry.geodesic import geodesic_area, geodesic_length
from app.geometry.measurement import FeatureMeasurer
from tests.support import SQUARE_1KM, SQUARE_1KM_AREA, UTM_43N, reproject, to_wgs84

LINE_5KM = LineString([(500_000, 1_400_000), (503_000, 1_404_000)])  # a 3-4-5 triangle's long side


@pytest.fixture
def wgs84_measurer() -> FeatureMeasurer:
    return FeatureMeasurer(CRS.from_epsg(4326))


# --- what gets measured, per geometry type ---------------------------------------------------


def test_polygon_area_from_geographic_coordinates(wgs84_measurer):
    measurement = wgs84_measurer.measure(to_wgs84(SQUARE_1KM))

    assert measurement.status is MeasurementStatus.MEASURED
    assert measurement.type is MeasurementType.AREA
    assert measurement.value == pytest.approx(SQUARE_1KM_AREA, rel=1e-9)
    assert measurement.unit == "m2"
    assert measurement.method is MeasurementMethod.PROJECTED
    assert measurement.projected_crs == "EPSG:32643"
    assert measurement.geometry_repaired is False


def test_linestring_length_from_geographic_coordinates(wgs84_measurer):
    measurement = wgs84_measurer.measure(to_wgs84(LINE_5KM))

    assert measurement.type is MeasurementType.LENGTH
    assert measurement.value == pytest.approx(5000.0, abs=1e-6)
    assert measurement.unit == "m"


def test_polygon_hole_is_excluded_from_the_area(wgs84_measurer):
    hole = box(500_400, 1_400_400, 500_600, 1_400_600)
    with_hole = Polygon(SQUARE_1KM.exterior.coords, [hole.exterior.coords])

    measurement = wgs84_measurer.measure(to_wgs84(with_hole))

    assert measurement.value == pytest.approx(SQUARE_1KM_AREA - 200 * 200, rel=1e-9)


def test_multipolygon_area_sums_its_parts(wgs84_measurer):
    second = box(502_000, 1_400_000, 502_500, 1_400_500)

    measurement = wgs84_measurer.measure(to_wgs84(MultiPolygon([SQUARE_1KM, second])))

    assert measurement.type is MeasurementType.AREA
    assert measurement.value == pytest.approx(SQUARE_1KM_AREA + 500 * 500, rel=1e-9)


def test_multilinestring_length_sums_its_parts(wgs84_measurer):
    second = LineString([(500_000, 1_410_000), (500_000, 1_411_000)])

    measurement = wgs84_measurer.measure(to_wgs84(MultiLineString([LINE_5KM, second])))

    assert measurement.type is MeasurementType.LENGTH
    assert measurement.value == pytest.approx(6000.0, abs=1e-6)


@pytest.mark.parametrize("geometry", [Point(77.0, 13.0), MultiPoint([(77.0, 13.0), (77.1, 13.1)])])
def test_points_need_no_measurement(wgs84_measurer, geometry):
    measurement = wgs84_measurer.measure(geometry)

    assert measurement.status is MeasurementStatus.NOT_REQUIRED
    assert measurement.type is None
    assert measurement.value is None
    assert measurement.unit is None


def test_geometry_collection_is_reported_as_unsupported_not_an_error(wgs84_measurer):
    mixed = GeometryCollection([Point(77.0, 13.0), LineString([(77.0, 13.0), (77.1, 13.1)])])

    measurement = wgs84_measurer.measure(mixed)

    assert measurement.status is MeasurementStatus.UNSUPPORTED
    assert "GeometryCollection" in measurement.reason
    assert measurement.value is None


@pytest.mark.parametrize("geometry", [None, Polygon()])
def test_missing_or_empty_geometry_is_unsupported(wgs84_measurer, geometry):
    measurement = wgs84_measurer.measure(geometry)

    assert measurement.status is MeasurementStatus.UNSUPPORTED
    assert "no readable geometry" in measurement.reason


# --- geometry clean-up -----------------------------------------------------------------------


def test_z_values_are_ignored(wgs84_measurer):
    flat = to_wgs84(SQUARE_1KM)
    with_heights = Polygon(
        [(x, y, 900.0 + i * 25) for i, (x, y) in enumerate(flat.exterior.coords)]
    )

    assert wgs84_measurer.measure(with_heights).value == pytest.approx(SQUARE_1KM_AREA, rel=1e-9)


def test_self_crossing_polygon_is_repaired_and_flagged(wgs84_measurer):
    # A "bow-tie": two triangles of 250,000 m2 each. Unrepaired, its area computes as zero.
    bow_tie = Polygon(
        [
            (500_000, 1_400_000),
            (501_000, 1_401_000),
            (501_000, 1_400_000),
            (500_000, 1_401_000),
        ]
    )

    measurement = wgs84_measurer.measure(to_wgs84(bow_tie))

    assert measurement.status is MeasurementStatus.MEASURED
    assert measurement.geometry_repaired is True
    assert measurement.value == pytest.approx(500_000.0, rel=1e-6)


# --- choosing the projected CRS --------------------------------------------------------------


def test_each_feature_gets_the_utm_zone_it_lies_in(wgs84_measurer):
    west_of_78 = box(77.90, 13.0, 77.91, 13.01)
    east_of_78 = box(78.10, 13.0, 78.11, 13.01)

    assert wgs84_measurer.measure(west_of_78).projected_crs == "EPSG:32643"
    assert wgs84_measurer.measure(east_of_78).projected_crs == "EPSG:32644"


def test_southern_hemisphere_uses_a_south_zone(wgs84_measurer):
    sydney = box(151.20, -33.88, 151.21, -33.87)

    assert wgs84_measurer.measure(sydney).projected_crs == "EPSG:32756"


@pytest.mark.parametrize(
    ("shape_in_metres", "utm_epsg"),
    [
        (SQUARE_1KM, 32643),  # on the central meridian
        (box(680_000, 1_400_000, 681_000, 1_401_000), 32643),  # 180 km east of it
        (box(830_000, 0, 831_000, 1_000), 32643),  # zone edge on the equator: UTM's worst case
        (box(300_000, 6_000_000, 301_000, 6_001_000), 32633),  # 54 N, central Europe
    ],
)
def test_utm_area_agrees_with_the_ellipsoid_within_utm_scale_error(
    wgs84_measurer, shape_in_metres, utm_epsg
):
    on_ellipsoid = to_wgs84(shape_in_metres, utm_epsg)

    measurement = wgs84_measurer.measure(on_ellipsoid)

    assert measurement.method is MeasurementMethod.PROJECTED
    assert measurement.value == pytest.approx(geodesic_area(on_ellipsoid), rel=0.003)


def test_utm_length_agrees_with_the_ellipsoid_within_utm_scale_error(wgs84_measurer):
    on_ellipsoid = to_wgs84(LINE_5KM)

    measurement = wgs84_measurer.measure(on_ellipsoid)

    assert measurement.value == pytest.approx(geodesic_length(on_ellipsoid), rel=0.0015)


# --- source CRS other than WGS 84 ------------------------------------------------------------


def test_file_already_in_its_utm_zone_is_measured_as_is():
    measurement = FeatureMeasurer(CRS.from_epsg(UTM_43N)).measure(SQUARE_1KM)

    assert measurement.value == SQUARE_1KM_AREA  # exact: no transformation happens
    assert measurement.projected_crs == "EPSG:32643"


def test_web_mercator_source_is_reprojected_not_measured_directly():
    in_web_mercator = reproject(SQUARE_1KM, UTM_43N, 3857)
    assert in_web_mercator.area > SQUARE_1KM_AREA * 1.04  # the trap: Mercator inflates area

    measurement = FeatureMeasurer(CRS.from_epsg(3857)).measure(in_web_mercator)

    assert measurement.value == pytest.approx(SQUARE_1KM_AREA, rel=1e-6)
    assert measurement.projected_crs == "EPSG:32643"


def test_source_in_feet_is_reported_in_metres():
    california_zone_3_feet = 2227
    square_in_utm_10n = box(550_000, 4_180_000, 551_000, 4_181_000)
    in_feet = reproject(square_in_utm_10n, 32610, california_zone_3_feet)
    assert in_feet.area > 10_000_000  # square feet

    measurement = FeatureMeasurer(CRS.from_epsg(california_zone_3_feet)).measure(in_feet)

    assert measurement.unit == "m2"
    assert measurement.value == pytest.approx(1_000_000.0, rel=1e-6)
    assert measurement.projected_crs == "EPSG:32610"


def test_geographic_source_on_another_datum():
    nad27 = 4267
    square_in_utm_14n = box(500_000, 4_400_000, 501_000, 4_401_000)
    in_nad27 = reproject(square_in_utm_14n, 32614, nad27)

    measurement = FeatureMeasurer(CRS.from_epsg(nad27)).measure(in_nad27)

    assert measurement.value == pytest.approx(1_000_000.0, rel=1e-5)
    assert measurement.projected_crs == "EPSG:32614"


def test_unknown_crs_measures_nothing_but_still_classifies():
    measurer = FeatureMeasurer(None)

    polygon = measurer.measure(box(0, 0, 10, 10))

    assert polygon.status is MeasurementStatus.UNSUPPORTED
    assert polygon.type is MeasurementType.AREA
    assert polygon.reason == "unknown CRS"
    assert measurer.measure(Point(1, 1)).status is MeasurementStatus.NOT_REQUIRED


def test_local_engineering_crs_is_unsupported():
    site_grid = CRS.from_wkt('LOCAL_CS["site grid",UNIT["metre",1]]')

    measurement = FeatureMeasurer(site_grid).measure(box(0, 0, 10, 10))

    assert measurement.status is MeasurementStatus.UNSUPPORTED
    assert "cannot be related to WGS 84" in measurement.reason


# --- features no single UTM zone fits --------------------------------------------------------


def test_feature_wider_than_one_degree_is_measured_on_the_ellipsoid(wgs84_measurer):
    region = box(70.0, 10.0, 80.0, 20.0)

    measurement = wgs84_measurer.measure(region)

    assert measurement.status is MeasurementStatus.MEASURED
    assert measurement.method is MeasurementMethod.GEODESIC
    assert measurement.projected_crs is None
    assert measurement.unit == "m2"
    assert measurement.value == pytest.approx(geodesic_area(region))
    assert measurement.value == pytest.approx(1.19e12, rel=0.01)  # about 1.19 million km2


def test_long_line_is_measured_on_the_ellipsoid(wgs84_measurer):
    along_the_equator = LineString([(70.0, 0.0), (80.0, 0.0)])

    measurement = wgs84_measurer.measure(along_the_equator)

    assert measurement.method is MeasurementMethod.GEODESIC
    assert measurement.value == pytest.approx(1_113_194.908, abs=0.01)


def test_polar_feature_is_measured_on_the_ellipsoid(wgs84_measurer):
    measurement = wgs84_measurer.measure(box(20.0, 85.0, 20.5, 85.2))

    assert measurement.method is MeasurementMethod.GEODESIC
    assert measurement.value > 0


def test_feature_across_the_antimeridian_is_measured_on_the_ellipsoid(wgs84_measurer):
    across = Polygon([(179.9, 0.0), (-179.9, 0.0), (-179.9, 0.1), (179.9, 0.1)])
    same_shape_at_greenwich = Polygon([(-0.1, 0.0), (0.1, 0.0), (0.1, 0.1), (-0.1, 0.1)])

    measurement = wgs84_measurer.measure(across)

    assert measurement.method is MeasurementMethod.GEODESIC
    assert measurement.value == pytest.approx(geodesic_area(same_shape_at_greenwich), rel=1e-9)


def test_wide_feature_in_a_projected_source_crs_is_measured_on_the_ellipsoid():
    region = box(70.0, 10.0, 80.0, 20.0)
    in_web_mercator = reproject(region, 4326, 3857)

    measurement = FeatureMeasurer(CRS.from_epsg(3857)).measure(in_web_mercator)

    assert measurement.method is MeasurementMethod.GEODESIC
    assert measurement.value == pytest.approx(geodesic_area(region), rel=1e-9)


# --- failures stay inside one feature --------------------------------------------------------


def test_coordinates_outside_the_crs_fail_that_feature_only(wgs84_measurer):
    nonsense = Polygon([(77.0, 9000.0), (77.01, 9000.0), (77.01, 9000.01)])

    measurement = wgs84_measurer.measure(nonsense)

    assert measurement.status is MeasurementStatus.FAILED
    assert measurement.type is MeasurementType.AREA
    assert measurement.value is None
    assert wgs84_measurer.measure(to_wgs84(SQUARE_1KM)).status is MeasurementStatus.MEASURED


def test_unexpected_error_is_contained(wgs84_measurer, monkeypatch):
    def explode(*_args):
        raise RuntimeError("library failure")

    monkeypatch.setattr(wgs84_measurer, "_measure", explode)

    measurement = wgs84_measurer.measure(to_wgs84(SQUARE_1KM))

    assert measurement.status is MeasurementStatus.FAILED
    assert measurement.reason == "The geometry could not be measured."
