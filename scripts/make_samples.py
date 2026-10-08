"""Regenerate the files in samples/.

Every shape is drawn in metres in WGS 84 / UTM zone 43N, near Bengaluru, so its true grid size
is known: the README compares the API's answers against these numbers.

    python scripts/make_samples.py
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterable
from pathlib import Path
from tempfile import TemporaryDirectory

import geopandas
import shapely
from pyproj import Transformer
from shapely.geometry import LineString, Point, Polygon, box
from shapely.geometry.base import BaseGeometry

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
UTM_43N = 32643
# South-west corner of the site, in UTM 43N metres (about 77.59 E, 12.97 N).
X0, Y0 = 780_000, 1_435_000

_TO_WGS84 = Transformer.from_crs(UTM_43N, 4326, always_xy=True)


def site(x: float, y: float) -> tuple[float, float]:
    return X0 + x, Y0 + y


def lonlat(geometry: BaseGeometry) -> BaseGeometry:
    return shapely.transform(geometry, _TO_WGS84.transform, interleaved=False)


def coordinates(points: Iterable[tuple[float, ...]]) -> str:
    text = " ".join(f"{lon:.9f},{lat:.9f},0" for lon, lat in points)
    return f"<coordinates>{text}</coordinates>"


def polygon_kml(polygon: Polygon) -> str:
    def ring(points: Iterable[tuple[float, ...]]) -> str:
        return f"<LinearRing>{coordinates(points)}</LinearRing>"

    holes = "".join(
        f"<innerBoundaryIs>{ring(hole.coords)}</innerBoundaryIs>" for hole in polygon.interiors
    )
    return (
        f"<Polygon><outerBoundaryIs>{ring(polygon.exterior.coords)}</outerBoundaryIs>"
        f"{holes}</Polygon>"
    )


def placemark(placemark_id: str, name: str, geometry_kml: str, **data: str) -> str:
    fields = "".join(f'<Data name="{k}"><value>{v}</value></Data>' for k, v in data.items())
    extended = f"<ExtendedData>{fields}</ExtendedData>" if fields else ""
    return (
        f'    <Placemark id="{placemark_id}"><name>{name}</name>{extended}'
        f"{geometry_kml}</Placemark>\n"
    )


def write_survey_kml() -> None:
    field_a = lonlat(box(*site(0, 0), *site(400, 250)))  # 400 m x 250 m = 100,000 m2
    pond = box(*site(600, 100), *site(650, 150))
    field_b = lonlat(  # 300 m x 300 m less a 50 m x 50 m pond = 87,500 m2
        Polygon(box(*site(500, 0), *site(800, 300)).exterior.coords, [pond.exterior.coords])
    )
    line_1 = lonlat(LineString([site(0, 400), site(1000, 400)]))  # 1,000 m
    line_2 = lonlat(LineString([site(0, 500), site(300, 500), site(300, 900)]))  # 300 + 400 m
    gcp_1, gcp_2 = lonlat(Point(site(0, 0))), lonlat(Point(site(800, 300)))
    note_point = lonlat(Point(site(900, 0)))
    note_line = lonlat(LineString([site(900, 0), site(950, 50)]))

    def point_kml(point: Point) -> str:
        return f"<Point>{coordinates(point.coords)}</Point>"

    def line_kml(line: LineString) -> str:
        return f"<LineString>{coordinates(line.coords)}</LineString>"

    body = (
        "  <Folder><name>Boundaries</name>\n"
        + placemark("field-a", "Field A", polygon_kml(field_a), crop="ragi", owner="Asha")
        + placemark("field-b", "Field B", polygon_kml(field_b), crop="maize", owner="Ravi")
        + "  </Folder>\n  <Folder><name>Flight lines</name>\n"
        + placemark("line-1", "Line 1", line_kml(line_1), altitude_m="120")
        + placemark("line-2", "Line 2", line_kml(line_2), altitude_m="120")
        + "  </Folder>\n  <Folder><name>Ground control</name>\n"
        + placemark("gcp-1", "GCP 1", point_kml(gcp_1))
        + placemark("gcp-2", "GCP 2", point_kml(gcp_2))
        + placemark(
            "note-1",
            "Access note",
            f"<MultiGeometry>{point_kml(note_point)}{line_kml(note_line)}</MultiGeometry>",
        )
        + "  </Folder>\n"
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<kml xmlns="http://www.opengis.net/kml/2.2">\n<Document>\n'
        f"  <name>Sample drone survey</name>\n{body}</Document>\n</kml>\n"
    )
    (SAMPLES / "survey.kml").write_text(document, encoding="utf-8", newline="\n")


def write_parcels_zip() -> None:
    parcels = geopandas.GeoDataFrame(
        {
            "parcel_id": ["P-101", "P-102", "P-103"],
            "land_use": ["residential", "commercial", "open space"],
            "floors": [2, 5, 0],
        },
        geometry=[
            box(*site(0, 0), *site(100, 100)),  # 10,000 m2
            box(*site(150, 0), *site(400, 120)),  # 30,000 m2
            Polygon([site(0, 200), site(300, 200), site(0, 600)]),  # right triangle, 60,000 m2
        ],
        crs=UTM_43N,
    )
    buffer = io.BytesIO()
    with TemporaryDirectory() as directory:
        parcels.to_file(Path(directory) / "parcels.shp", engine="pyogrio")
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for part in sorted(Path(directory).iterdir()):
                archive.write(part, part.name)
    (SAMPLES / "parcels.zip").write_bytes(buffer.getvalue())


if __name__ == "__main__":
    SAMPLES.mkdir(exist_ok=True)
    write_survey_kml()
    write_parcels_zip()
    print(f"Wrote {SAMPLES / 'survey.kml'} and {SAMPLES / 'parcels.zip'}")
