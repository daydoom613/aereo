"""Geodesic results are checked against values known independently of pyproj."""

import math

import pytest
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Polygon, box

from app.geometry.geodesic import geodesic_area, geodesic_length

WGS84_SEMI_MAJOR_AXIS = 6_378_137.0
WGS84_FLATTENING = 1 / 298.257223563
# Published length of a WGS 84 meridian from the equator to the pole.
WGS84_QUARTER_MERIDIAN = 10_001_965.729


def wgs84_surface_area() -> float:
    """Closed-form surface area of the WGS 84 ellipsoid."""
    eccentricity = math.sqrt(WGS84_FLATTENING * (2 - WGS84_FLATTENING))
    polar_term = (1 - eccentricity**2) / eccentricity * math.atanh(eccentricity)
    return 2 * math.pi * WGS84_SEMI_MAJOR_AXIS**2 * (1 + polar_term)


def test_length_of_a_meridian_from_equator_to_pole():
    meridian = LineString([(77.0, 0.0), (77.0, 90.0)])

    assert geodesic_length(meridian) == pytest.approx(WGS84_QUARTER_MERIDIAN, abs=0.01)


def test_length_along_the_equator_is_radius_times_angle():
    arc = LineString([(0.0, 0.0), (10.0, 0.0)])

    assert geodesic_length(arc) == pytest.approx(
        WGS84_SEMI_MAJOR_AXIS * math.radians(10), abs=0.001
    )


def test_length_of_a_multilinestring_sums_its_parts():
    first = LineString([(0.0, 0.0), (10.0, 0.0)])
    second = LineString([(20.0, 0.0), (30.0, 0.0)])

    assert geodesic_length(MultiLineString([first, second])) == pytest.approx(
        2 * geodesic_length(first)
    )


def test_area_between_two_meridians_from_equator_to_pole():
    # Ten degrees of longitude out of 360, and the northern half of the ellipsoid only.
    wedge = Polygon([(0.0, 0.0), (10.0, 0.0), (10.0, 90.0), (0.0, 90.0)])

    assert geodesic_area(wedge) == pytest.approx(wgs84_surface_area() * 10 / 360 / 2, rel=1e-9)


def test_hole_is_subtracted_whichever_way_its_ring_is_wound():
    outer = [(77.0, 13.0), (77.01, 13.0), (77.01, 13.01), (77.0, 13.01)]
    hole = [(77.004, 13.004), (77.006, 13.004), (77.006, 13.006), (77.004, 13.006)]
    expected = geodesic_area(Polygon(outer)) - geodesic_area(Polygon(hole))

    assert geodesic_area(Polygon(outer, [hole])) == pytest.approx(expected)
    assert geodesic_area(Polygon(outer, [hole[::-1]])) == pytest.approx(expected)
    assert geodesic_area(Polygon(outer[::-1], [hole])) == pytest.approx(expected)


def test_area_of_a_multipolygon_sums_its_parts():
    first = box(77.0, 13.0, 77.01, 13.01)
    second = box(77.1, 13.0, 77.11, 13.01)

    assert geodesic_area(MultiPolygon([first, second])) == pytest.approx(
        geodesic_area(first) + geodesic_area(second)
    )


def test_area_across_the_antimeridian_matches_the_same_shape_elsewhere():
    # The ellipsoid is symmetric in longitude, so a box centred on 180 equals one centred on 0.
    across = Polygon([(179.0, 0.0), (-179.0, 0.0), (-179.0, 1.0), (179.0, 1.0)])
    at_greenwich = Polygon([(-1.0, 0.0), (1.0, 0.0), (1.0, 1.0), (-1.0, 1.0)])

    assert geodesic_area(across) == pytest.approx(geodesic_area(at_greenwich), rel=1e-9)
