from pathlib import Path

import pytest
from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Point, Polygon, box

from app.core.errors import GeoFileReadError, UnprocessableUploadError, UnsupportedFileTypeError
from app.domain import GeoDataset
from app.readers.kml import KmlReader
from tests.support import folder, kml_document, kml_file, placemark

PARCEL = box(77.0, 13.0, 77.01, 13.01)
PATH = LineString([(77.0, 13.0), (77.02, 13.0), (77.02, 13.02)])
PEG = Point(77.005, 13.005)


def read(tmp_path: Path, content: bytes) -> GeoDataset:
    upload = tmp_path / "upload.kml"
    upload.write_bytes(content)
    reader = KmlReader()
    return reader.read(reader.prepare(upload, tmp_path))


def prepare(tmp_path: Path, content: bytes) -> Path:
    upload = tmp_path / "upload.kml"
    upload.write_bytes(content)
    return KmlReader().prepare(upload, tmp_path)


# --- checking the container ------------------------------------------------------------------


def test_prepare_accepts_a_kml_document_and_opens_it_in_place(tmp_path):
    assert prepare(tmp_path, kml_document(placemark(PEG))) == tmp_path / "upload.kml"


def test_prepare_accepts_a_namespace_prefixed_root(tmp_path):
    content = b'<kml:kml xmlns:kml="http://www.opengis.net/kml/2.2"><kml:Document/></kml:kml>'

    assert prepare(tmp_path, content) == tmp_path / "upload.kml"


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"this is not xml at all",
        b'<?xml version="1.0"?><gpx version="1.1"></gpx>',
        b"PK\x03\x04 a zip renamed to .kml",
    ],
)
def test_prepare_rejects_content_that_is_not_kml(tmp_path, content):
    with pytest.raises(UnsupportedFileTypeError):
        prepare(tmp_path, content)


def test_prepare_refuses_a_doctype(tmp_path):
    entity_bomb = (
        b'<?xml version="1.0"?>'
        b'<!DOCTYPE kml [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;">]>'
        b'<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>&b;</name></Document></kml>'
    )

    with pytest.raises(UnprocessableUploadError, match="DOCTYPE"):
        prepare(tmp_path, entity_bomb)


# --- extracting features ---------------------------------------------------------------------


def test_reads_each_placemark_with_its_geometry_in_wgs84(tmp_path):
    dataset = read(
        tmp_path,
        kml_document(
            placemark(PARCEL, name="Field A"),
            placemark(PATH, name="Flight line"),
            placemark(PEG, name="Control point"),
        ),
    )

    assert [feature.geometry_type for feature in dataset.features] == [
        "Polygon",
        "LineString",
        "Point",
    ]
    assert dataset.crs.to_epsg() == 4326
    assert dataset.crs_assumed is False
    assert dataset.features[0].geometry.equals(PARCEL)


def test_source_id_is_the_placemark_id_when_there_is_one(tmp_path):
    dataset = read(
        tmp_path,
        kml_document(placemark(PEG, placemark_id="pm-7"), placemark(PEG, name="No id")),
    )

    assert [feature.source_id for feature in dataset.features] == ["pm-7", None]


def test_properties_are_the_name_and_extended_data_only(tmp_path):
    dataset = read(
        tmp_path,
        kml_document(
            placemark(
                PEG, name="Field A", placemark_id="pm-1", data={"crop": "ragi", "owner": "Asha"}
            )
        ),
    )

    assert dataset.features[0].properties == {"Name": "Field A", "crop": "ragi", "owner": "Asha"}


def test_a_field_one_placemark_lacks_is_left_out_not_reported_as_null(tmp_path):
    dataset = read(
        tmp_path,
        kml_document(placemark(PEG, name="A", data={"crop": "ragi"}), placemark(PEG, name="B")),
    )

    assert dataset.features[1].properties == {"Name": "B"}


def test_typed_schema_fields_keep_their_types(tmp_path):
    body = (
        '<Document><Schema name="Parcel" id="ParcelSchema">'
        '<SimpleField type="int" name="plot_no"/><SimpleField type="string" name="owner"/>'
        "</Schema><Placemark><name>Field A</name>"
        '<ExtendedData><SchemaData schemaUrl="#ParcelSchema">'
        '<SimpleData name="plot_no">42</SimpleData><SimpleData name="owner">Asha</SimpleData>'
        "</SchemaData></ExtendedData>"
        "<Point><coordinates>77.0,13.0</coordinates></Point></Placemark></Document>"
    )

    dataset = read(tmp_path, kml_file(body))

    assert dataset.features[0].properties == {"Name": "Field A", "plot_no": 42, "owner": "Asha"}


def test_features_of_every_folder_are_read_including_nested_ones(tmp_path):
    dataset = read(
        tmp_path,
        kml_document(
            folder(
                "Boundaries",
                placemark(PARCEL, name="Field A"),
                folder("North block", placemark(PARCEL, name="Field B")),
            ),
            folder("Flight lines", placemark(PATH, name="Line 1")),
            folder("Empty"),
        ),
    )

    assert sorted(feature.properties["Name"] for feature in dataset.features) == [
        "Field A",
        "Field B",
        "Line 1",
    ]


def test_feature_order_is_the_same_on_every_read(tmp_path):
    content = kml_document(
        folder("One", placemark(PEG, name="a"), placemark(PEG, name="b")),
        folder("Two", placemark(PEG, name="c")),
    )

    first = [feature.properties["Name"] for feature in read(tmp_path, content).features]
    second = [feature.properties["Name"] for feature in read(tmp_path, content).features]

    assert first == second == ["a", "b", "c"]


def test_multigeometry_of_one_type_becomes_a_multi_part_geometry(tmp_path):
    two_parcels = MultiPolygon([PARCEL, box(77.1, 13.0, 77.11, 13.01)])

    dataset = read(tmp_path, kml_document(placemark(two_parcels)))

    assert dataset.features[0].geometry_type == "MultiPolygon"


def test_multigeometry_of_mixed_types_becomes_a_geometry_collection(tmp_path):
    dataset = read(tmp_path, kml_document(placemark(GeometryCollection([PEG, PATH]))))

    assert dataset.features[0].geometry_type == "GeometryCollection"


def test_heights_are_kept_on_the_geometry(tmp_path):
    with_heights = Polygon([(77.0, 13.0, 900.0), (77.01, 13.0, 905.0), (77.01, 13.01, 910.0)])

    dataset = read(tmp_path, kml_document(placemark(with_heights)))

    assert dataset.features[0].geometry.has_z


def test_placemark_without_geometry_is_kept_as_a_feature_without_geometry(tmp_path):
    dataset = read(tmp_path, kml_document(placemark(None, name="Note"), placemark(PEG)))

    assert [feature.geometry_type for feature in dataset.features] == [None, "Point"]


def test_undecodable_geometry_does_not_stop_the_rest_of_the_layer(tmp_path):
    # GDAL hands back a bare LinearRing in a form GEOS cannot decode.
    bare_ring = (
        "<LinearRing><coordinates>77,13 77.01,13 77.01,13.01 77,13</coordinates></LinearRing>"
    )

    dataset = read(
        tmp_path,
        kml_document(placemark(name="Ring", geometry_xml=bare_ring), placemark(PEG, name="Peg")),
    )

    assert [feature.geometry_type for feature in dataset.features] == [None, "Point"]


def test_document_without_placemarks_is_an_empty_dataset(tmp_path):
    assert read(tmp_path, kml_document()).features == []


# --- unreadable content ----------------------------------------------------------------------


def test_truncated_kml_is_a_read_error_that_does_not_reveal_server_paths(tmp_path):
    truncated = kml_document(placemark(PARCEL))[:-40]
    source = prepare(tmp_path, truncated)  # the root is <kml>, so the container is accepted

    with pytest.raises(GeoFileReadError) as failure:
        KmlReader().read(source)

    assert str(tmp_path) not in str(failure.value)
    assert tmp_path.as_posix() not in str(failure.value)
