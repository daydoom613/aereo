import pytest

from app.core.config import Settings
from app.core.errors import UnsupportedFileTypeError
from app.domain import FileFormat
from app.readers.registry import build_readers, format_of


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("survey.kml", FileFormat.KML),
        ("SURVEY.KML", FileFormat.KML),
        ("parcels.zip", FileFormat.SHAPEFILE),
        ("parcels.shp.zip", FileFormat.SHAPEFILE),
    ],
)
def test_format_is_chosen_by_extension(filename, expected):
    assert format_of(filename) is expected


@pytest.mark.parametrize(
    "filename", ["survey.geojson", "parcels.shp", "survey.kmz", "noextension", ""]
)
def test_other_extensions_are_unsupported(filename):
    with pytest.raises(UnsupportedFileTypeError):
        format_of(filename)


def test_there_is_a_reader_for_every_format():
    assert set(build_readers(Settings())) == set(FileFormat)
