import pytest
from pyproj import CRS
from pyproj.aoi import AreaOfInterest
from pyproj.database import query_utm_crs_info

from app.geometry.projection import LonLatBox, crs_label, utm_epsg_code


@pytest.mark.parametrize(
    ("longitude", "latitude", "expected"),
    [
        (77.59, 12.97, 32643),  # Bengaluru
        (78.47, 17.38, 32644),  # Hyderabad, one zone east
        (-122.42, 37.77, 32610),  # San Francisco
        (-0.13, 51.51, 32630),  # London, just west of Greenwich
        (0.0, 0.0, 32631),  # the equator counts as north
        (151.21, -33.87, 32756),  # Sydney, southern hemisphere
        (-180.0, 10.0, 32601),
        (179.99, 10.0, 32660),
        (180.0, 10.0, 32601),  # 180 is the same meridian as -180
    ],
)
def test_utm_epsg_code_for_known_places(longitude, latitude, expected):
    assert utm_epsg_code(longitude, latitude) == expected


def test_utm_epsg_code_agrees_with_the_proj_database():
    # Mid-zone longitudes only: on an exact zone boundary both neighbouring zones are valid.
    for longitude in range(-177, 180, 6):
        for latitude in (-79, -45, -1, 1, 45, 83):
            point = AreaOfInterest(longitude, latitude, longitude, latitude)
            from_database = query_utm_crs_info(datum_name="WGS 84", area_of_interest=point)
            assert utm_epsg_code(longitude, latitude) == int(from_database[0].code)


def test_small_box_fits_one_utm_zone_and_uses_the_zone_of_its_centre():
    box = LonLatBox(west=77.0, south=13.0, east=77.01, north=13.01)

    assert box.fits_one_utm_zone()
    assert box.utm_epsg_code() == 32643


def test_box_straddling_a_zone_boundary_still_fits_and_takes_its_centre_zone():
    box = LonLatBox(west=77.95, south=13.0, east=78.07, north=13.1)

    assert box.fits_one_utm_zone()
    assert box.utm_epsg_code() == 32644


@pytest.mark.parametrize(
    ("box", "why"),
    [
        (LonLatBox(70.0, 10.0, 71.5, 11.0), "wider than one degree"),
        (LonLatBox(179.5, 0.0, -179.5, 1.0), "crosses the antimeridian"),
        (LonLatBox(20.0, 83.5, 20.5, 84.5), "north of the UTM limit"),
        (LonLatBox(20.0, -80.5, 20.5, -79.5), "south of the UTM limit"),
    ],
)
def test_box_that_no_single_utm_zone_fits(box, why):
    assert not box.fits_one_utm_zone(), why


def test_box_exactly_one_degree_wide_still_fits():
    assert LonLatBox(77.0, 13.0, 78.0, 13.5).fits_one_utm_zone()


def test_box_with_a_non_finite_edge_is_not_finite():
    assert LonLatBox(77.0, 13.0, 77.1, 13.1).is_finite
    assert not LonLatBox(77.0, 13.0, float("inf"), 13.1).is_finite


def test_crs_label_prefers_the_epsg_code():
    esri_prj = (
        'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],'
        'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
    )

    assert crs_label(CRS.from_epsg(32643)) == "EPSG:32643"
    assert crs_label(CRS.from_wkt(esri_prj)) == "EPSG:4326"


def test_crs_label_falls_back_to_the_definition_and_passes_none_through():
    custom = CRS.from_proj4("+proj=laea +lat_0=13 +lon_0=77 +datum=WGS84 +units=m")

    assert "laea" in crs_label(custom)
    assert crs_label(None) is None
