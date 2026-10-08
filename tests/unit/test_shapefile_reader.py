import json
from pathlib import Path

import numpy
import pyogrio
import pytest
import shapely
from shapely.geometry import Point, box

from app.core.errors import GeoFileReadError, UnprocessableUploadError, UnsupportedFileTypeError
from app.domain import GeoDataset
from app.readers.shapefile import ShapefileReader
from tests.support import (
    SQUARE_1KM,
    UTM_43N,
    layer,
    mark_first_entry_encrypted,
    shapefile_parts,
    shapefile_zip,
    understate_size_of,
    zip_of,
)

PARCELS = layer(
    [box(77.0, 13.0, 77.01, 13.01), box(77.02, 13.0, 77.03, 13.01)],
    name=["Field A", "Field B"],
    plot_no=[41, 42],
)
MEBIBYTE = 1024 * 1024


def make_reader(max_uncompressed_bytes: int = 50 * MEBIBYTE, max_entries: int = 100):
    return ShapefileReader(max_uncompressed_bytes=max_uncompressed_bytes, max_entries=max_entries)


def prepare(tmp_path: Path, archive: bytes, reader: ShapefileReader | None = None) -> Path:
    upload = tmp_path / "upload.zip"
    upload.write_bytes(archive)
    return (reader or make_reader()).prepare(upload, tmp_path)


def read(tmp_path: Path, archive: bytes) -> GeoDataset:
    return make_reader().read(prepare(tmp_path, archive))


# --- checking and unpacking the archive ------------------------------------------------------


def test_prepare_unpacks_the_parts_under_fixed_names(tmp_path):
    source = prepare(tmp_path, shapefile_zip(PARCELS, stem="client named this"))

    assert source == tmp_path / "shapefile.shp"
    unpacked = {path.name for path in tmp_path.iterdir()} - {"upload.zip"}
    assert unpacked == {
        "shapefile.shp",
        "shapefile.shx",
        "shapefile.dbf",
        "shapefile.prj",
        "shapefile.cpg",
    }


def test_shapefile_inside_a_folder_is_found(tmp_path):
    dataset = read(tmp_path, shapefile_zip(PARCELS, folder_name="deliverables/2026/"))

    assert len(dataset.features) == 2


def test_part_names_are_matched_without_regard_to_case(tmp_path):
    parts = shapefile_parts(PARCELS)
    shouting = {name.upper(): content for name, content in parts.items()}
    shouting["parcels.dbf"] = shouting.pop("PARCELS.DBF")

    assert len(read(tmp_path, zip_of(shouting)).features) == 2


def test_macos_archive_debris_is_not_mistaken_for_a_second_shapefile(tmp_path):
    entries = shapefile_parts(PARCELS)
    entries["__MACOSX/._parcels.shp"] = b"resource fork"
    entries["._parcels.shp"] = b"resource fork"

    assert len(read(tmp_path, zip_of(entries)).features) == 2


def test_unrelated_files_in_the_archive_are_ignored(tmp_path):
    entries = shapefile_parts(PARCELS)
    entries["readme.txt"] = b"survey notes"
    entries["parcels.shp.xml"] = b"<metadata/>"

    assert len(read(tmp_path, zip_of(entries)).features) == 2


@pytest.mark.parametrize("content", [b"", b"not a zip archive", b"PK\x03\x04 truncated"])
def test_prepare_rejects_content_that_is_not_a_zip(tmp_path, content):
    with pytest.raises(UnsupportedFileTypeError):
        prepare(tmp_path, content)


@pytest.mark.parametrize("missing", [".dbf", ".shx"])
def test_missing_required_part_is_named_in_the_error(tmp_path, missing):
    with pytest.raises(UnprocessableUploadError, match=f"parcels{missing}"):
        prepare(tmp_path, shapefile_zip(PARCELS, without=(missing,)))


def test_archive_without_a_shapefile_is_rejected(tmp_path):
    with pytest.raises(UnprocessableUploadError, match=r"no \.shp"):
        prepare(tmp_path, zip_of({"readme.txt": b"nothing here"}))


def test_archive_with_two_shapefiles_is_rejected(tmp_path):
    entries = shapefile_parts(PARCELS, "parcels") | shapefile_parts(PARCELS, "roads")

    with pytest.raises(UnprocessableUploadError, match="2 shapefiles"):
        prepare(tmp_path, zip_of(entries))


@pytest.mark.parametrize(
    "unsafe_name", ["../outside.txt", "nested/../../outside.txt", "/etc/passwd", "C:/outside.txt"]
)
def test_zip_slip_entry_is_rejected_and_nothing_is_written_outside(tmp_path, unsafe_name):
    workdir = tmp_path / "work"
    workdir.mkdir()
    entries = shapefile_parts(PARCELS) | {unsafe_name: b"escaped"}

    with pytest.raises(UnprocessableUploadError, match="absolute or parent-relative"):
        prepare(workdir, zip_of(entries))

    assert [path.name for path in tmp_path.iterdir()] == ["work"]


def test_archive_with_too_many_entries_is_rejected(tmp_path):
    with pytest.raises(UnprocessableUploadError, match="more than 3 entries"):
        prepare(tmp_path, shapefile_zip(PARCELS), make_reader(max_entries=3))


def test_archive_that_declares_too_much_uncompressed_data_is_rejected(tmp_path):
    entries = shapefile_parts(PARCELS) | {"padding.bin": bytes(2 * MEBIBYTE)}  # zeros: tiny zipped

    with pytest.raises(UnprocessableUploadError, match="too large when uncompressed"):
        prepare(tmp_path, zip_of(entries), make_reader(max_uncompressed_bytes=MEBIBYTE))


def test_entry_larger_than_its_declared_size_is_rejected_as_corrupt(tmp_path):
    # A zip bomb that lies in its header to slip under the size cap.
    parts = shapefile_parts(PARCELS)
    parts["parcels.dbf"] = bytes(2 * MEBIBYTE)
    lying = understate_size_of(zip_of(parts), "parcels.dbf", declared_size=100)

    with pytest.raises(UnprocessableUploadError, match="corrupt"):
        prepare(tmp_path, lying, make_reader(max_uncompressed_bytes=MEBIBYTE))

    assert (tmp_path / "shapefile.dbf").stat().st_size <= 100


def test_encrypted_archive_is_rejected(tmp_path):
    with pytest.raises(UnprocessableUploadError, match="Encrypted"):
        prepare(tmp_path, mark_first_entry_encrypted(shapefile_zip(PARCELS)))


def test_archive_with_damaged_compressed_data_is_rejected_as_corrupt(tmp_path):
    damaged = bytearray(shapefile_zip(layer([box(77.0, 13.0, 77.01, 13.01)] * 200)))
    local_header_and_name = 30 + len("parcels.cpg")
    for offset in range(local_header_and_name + 100, local_header_and_name + 140):
        damaged[offset] ^= 0xFF

    with pytest.raises(UnprocessableUploadError, match="corrupt"):
        prepare(tmp_path, bytes(damaged))


# --- extracting features ---------------------------------------------------------------------


def test_reads_features_with_record_numbers_and_attributes(tmp_path):
    dataset = read(tmp_path, shapefile_zip(PARCELS))

    assert [feature.source_id for feature in dataset.features] == ["0", "1"]
    assert [feature.geometry_type for feature in dataset.features] == ["Polygon", "Polygon"]
    assert dataset.features[1].properties == {"name": "Field B", "plot_no": 42}


def test_crs_comes_from_the_prj(tmp_path):
    dataset = read(tmp_path, shapefile_zip(layer([SQUARE_1KM], crs=UTM_43N)))

    assert dataset.crs.to_epsg() == UTM_43N
    assert dataset.crs_assumed is False


def test_missing_prj_with_degree_like_coordinates_assumes_wgs84_and_says_so(tmp_path):
    dataset = read(tmp_path, shapefile_zip(PARCELS, without=(".prj",)))

    assert dataset.crs.to_epsg() == 4326
    assert dataset.crs_assumed is True


def test_missing_prj_with_coordinates_that_cannot_be_degrees_leaves_the_crs_unknown(tmp_path):
    projected = layer([SQUARE_1KM], crs=UTM_43N)

    dataset = read(tmp_path, shapefile_zip(projected, without=(".prj",)))

    assert dataset.crs is None
    assert dataset.crs_assumed is False


def test_empty_shapefile_is_an_empty_dataset(tmp_path):
    dataset = read(tmp_path, shapefile_zip(layer([], name=[])))

    assert dataset.features == []
    assert dataset.crs.to_epsg() == 4326


def test_empty_shapefile_without_prj_has_an_unknown_crs(tmp_path):
    dataset = read(tmp_path, shapefile_zip(layer([], name=[]), without=(".prj",)))

    assert dataset.features == []
    assert dataset.crs is None


def test_record_without_a_shape_is_kept_as_a_feature_without_geometry(tmp_path):
    dataset = read(tmp_path, shapefile_zip(layer([box(77.0, 13.0, 77.01, 13.01), None], n=[1, 2])))

    assert [feature.geometry_type for feature in dataset.features] == ["Polygon", None]


def test_attribute_values_are_json_safe_and_nulls_are_kept(tmp_path):
    frame = layer(
        [Point(77.0, 13.0), Point(77.1, 13.1)],
        height=[912.5, float("nan")],
        note=["first", None],
        count=[3, 4],
    )

    dataset = read(tmp_path, shapefile_zip(frame))

    assert dataset.features[0].properties == {"height": 912.5, "note": "first", "count": 3}
    assert dataset.features[1].properties == {"height": None, "note": None, "count": 4}
    json.dumps([feature.properties for feature in dataset.features])  # must not raise


def test_dbf_date_field_becomes_iso_8601_text(tmp_path):
    written = tmp_path / "written"
    written.mkdir()
    pyogrio.raw.write(  # GeoPandas cannot write a true Date field, so GDAL is driven directly
        written / "visits.shp",
        geometry=shapely.to_wkb(numpy.array([Point(77.0, 13.0), Point(77.1, 13.1)])),
        field_data=[numpy.array(["2026-01-15", "NaT"], dtype="datetime64[D]")],
        fields=["surveyed"],
        crs="EPSG:4326",
        geometry_type="Point",
    )
    archive = zip_of({part.name: part.read_bytes() for part in written.iterdir()})

    dataset = read(tmp_path, archive)

    assert dataset.features[0].properties == {"surveyed": "2026-01-15T00:00:00"}
    assert dataset.features[1].properties == {"surveyed": None}


def test_unreadable_shp_is_a_read_error_that_does_not_reveal_server_paths(tmp_path):
    entries = shapefile_parts(PARCELS)
    entries["parcels.shp"] = b"this is not a shapefile"
    source = prepare(tmp_path, zip_of(entries))  # a complete archive, so the container is accepted

    with pytest.raises(GeoFileReadError) as failure:
        make_reader().read(source)

    assert str(tmp_path) not in str(failure.value)
    assert tmp_path.as_posix() not in str(failure.value)
