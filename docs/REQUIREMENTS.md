# Requirements checklist

Source of truth: the assignment document, *Geospatial File Measurement API*. Each item below quotes
or closely paraphrases it. A box is ticked only when the item is implemented **and** has a passing
test; the lines under each item say where. Test references are `file::test name`.

Status: every requirement is implemented and tested. One submission step is open: the repository
has to be made public (see R8).

## Problem statement

> Build a backend service using either Django or FastAPI that accepts a geospatial file, processes
> the features within it, and returns measurement information. The service should accept either
> Shapefile or KML. The objective is to evaluate your ability to build a clean backend API, work
> with geospatial data, handle file processing, and write production-quality Python code. You are
> free to make architectural and implementation decisions beyond the minimum requirements.

## Minimum requirements

- [x] **R1 Backend framework.** Django + Django REST Framework, or FastAPI.
  - Implemented in: `app/main.py` (FastAPI, `create_app`)
  - Tested by: `tests/api/test_errors_and_docs.py::test_openapi_documents_exactly_the_paths_of_the_brief`
- [x] **R2 File upload.** An API endpoint that accepts a geospatial file, `POST /api/files/`, accepting:
  - [x] a `.zip` containing a Shapefile
    - Implemented in: `app/api/files.py` (`upload_file`), `app/readers/shapefile.py` (`ShapefileReader.prepare`)
    - Tested by: `tests/api/test_upload.py::test_zipped_shapefile_upload_is_processed`
  - [x] a `.kml`
    - Implemented in: `app/api/files.py` (`upload_file`), `app/readers/kml.py` (`KmlReader.prepare`)
    - Tested by: `tests/api/test_upload.py::test_kml_upload_is_processed_and_returned_as_a_created_resource`
- [x] **R3 File processing.** After upload, read the geospatial data and extract its features. For
  every feature identify at minimum:
  - [x] Feature ID/index: `feature_index` (0-based across the file) and `source_id` (the file's own id)
  - [x] Geometry type: `geometry_type`
  - [x] Geometry: `geometry`, a GeoJSON geometry object in the file's CRS
  - [x] CRS: `crs`
  - [x] Properties/attributes: `properties`
    - Implemented in: `app/readers/kml.py` and `app/readers/shapefile.py` (`read`), `app/readers/base.py`
      (`feature_rows`), `app/domain.py` (`SourceFeature`), `app/api/presenters.py` (`_feature_measurement`)
    - Tested by: `tests/api/test_measurements.py::test_each_item_identifies_the_feature`,
      `::test_feature_indexes_run_from_zero_in_file_order`,
      `::test_shapefile_features_carry_their_record_number_and_attributes`
- [x] **R3a Unsupported geometry.** If a geometry type is not supported for measurement
  calculation, the API handles it gracefully rather than crashing.
  - Implemented in: `app/geometry/measurement.py` (`FeatureMeasurer.measure`), `app/readers/base.py`
    (`read_layer`, `on_invalid="ignore"`)
  - Tested by: `tests/api/test_measurements.py::test_unsupported_geometries_are_reported_and_the_rest_is_still_measured`,
    `tests/unit/test_measurement.py::test_geometry_collection_is_reported_as_unsupported_not_an_error`,
    `::test_unexpected_error_is_contained`
- [x] **R4 Measurements** for supported geometries:
  - [x] Polygon: area
  - [x] LineString: length
  - [x] Point: no measurement required
    - Implemented in: `app/geometry/measurement.py`, `app/geometry/geodesic.py`
    - Tested by: `tests/api/test_measurements.py::test_kml_polygon_area_and_line_length_match_the_known_values`,
      `::test_shapefile_of_lines_reports_length`,
      `tests/unit/test_measurement.py::test_polygon_hole_is_excluded_from_the_area`,
      `::test_points_need_no_measurement`
- [x] **R5 CRS handling.**
  - [x] Files with geographic coordinates (for example EPSG:4326) are handled correctly.
    - Tested by: `tests/api/test_measurements.py::test_shapefile_in_geographic_coordinates_is_projected_before_measuring`,
      `tests/unit/test_measurement.py::test_polygon_area_from_geographic_coordinates`
  - [x] Area and distance are never calculated directly in latitude/longitude degrees.
    - Implemented in: `app/geometry/measurement.py` (`FeatureMeasurer._measure`: every path either
      projects to UTM or measures on the ellipsoid)
    - Tested by: `tests/unit/test_measurement.py::test_utm_area_agrees_with_the_ellipsoid_within_utm_scale_error`,
      `tests/unit/test_geodesic.py::test_length_of_a_meridian_from_equator_to_pole`
  - [x] Geometry is transformed to an appropriate projected coordinate system before measuring.
    - Implemented in: `app/geometry/projection.py` (`utm_epsg_code`, `LonLatBox`)
    - Tested by: `tests/unit/test_projection.py::test_utm_epsg_code_for_known_places`,
      `::test_utm_epsg_code_agrees_with_the_proj_database`,
      `tests/unit/test_measurement.py::test_each_feature_gets_the_utm_zone_it_lies_in`,
      `::test_web_mercator_source_is_reprojected_not_measured_directly`
  - [x] The strategy for selecting the projected CRS is our own and is documented.
    - Documented in: `README.md` (CRS handling), `docs/DECISIONS.md` (D8)
- [x] **R6 API design.** At minimum:
  - [x] `POST /api/files/` uploads and processes a file.
    - Implemented in: `app/api/files.py` (`upload_file`), `app/services/file_service.py` (`FileService.upload`)
    - Tested by: `tests/api/test_upload.py` (27 tests)
  - [x] `GET /api/files/{id}/` returns information about the uploaded file, with at least `id`,
    `filename`, `feature_count`, `crs` and `status`.
    - Implemented in: `app/api/files.py` (`get_file`), `app/api/presenters.py` (`file_response`)
    - Tested by: `tests/api/test_file_info.py::test_returns_the_fields_the_brief_requires`
  - [x] `GET /api/files/{id}/measurements/` returns measurements for the features in the file.
    - Implemented in: `app/api/files.py` (`get_measurements`), `app/api/presenters.py` (`measurements_response`)
    - Tested by: `tests/api/test_measurements.py` (26 tests)
- [x] **R7 Documentation.** A `README.md` containing:
  - [x] Setup: how to run the application locally.
  - [x] API: the available endpoints and example requests/responses (copied from the running service).
  - [x] Architecture: application structure, file-processing flow, measurement calculation flow, CRS handling.
  - [x] Design Decisions: important technical decisions and alternatives considered.
- [ ] **R8 Submission.**
  - [ ] A public GitHub repository, link shared. *The code is pushed to
    https://github.com/daydoom613/aereo. The repository is private at the time of writing and must
    be made public before the link is shared.*
  - [x] The README mentions learnings and future scope.

## Readings of ambiguous text

Recorded in full in [DECISIONS.md](DECISIONS.md); listed here so the checklist is read the same way
by everyone.

| Text in the document | Reading used |
| --- | --- |
| "accept either Shapefile or KML" | Both are supported. |
| "Polygon", "LineString", "Point" | Their multi-part forms (MultiPolygon, MultiLineString, MultiPoint) are treated the same way. |
| "Feature ID/index" | Both: a 0-based index across the whole file, and the file's own identifier when it has one. |
| "Transform the geometry to an appropriate projected coordinate system" | Done for every feature that one projected CRS can represent accurately. See D8 for the features that none can. |
| The `GET /api/files/{id}/` example | The five fields shown are always present. Further fields are added, none removed or renamed. |
| Paths with trailing slashes | Kept exactly. The same paths without the slash also work, without a redirect. |

## Exit-gate checks

Run on 2026-10-08, before the checklist was ticked.

| Check | How | Result |
| --- | --- | --- |
| Tests | `pytest --cov=app` | 213 passed, 99% coverage |
| Lint and types | `ruff check .`, `ruff format --check .`, `mypy` (strict) | Clean |
| Clean clone | A fresh `git clone`, installed with `pip install -e ".[dev]"` inside a `python:3.12-slim` container, then lint, mypy and tests | 213 passed on Linux, 99.6% coverage |
| Docker | Image built from the clean clone; both sample files uploaded to the running container | Both `COMPLETED`; container health check `healthy`; runs as a non-root user |
| Every endpoint, live | curl against the running container: upload, file info, measurements, pagination, and the 400, 404, 409, 413, 415 and 422 responses | As documented in the README, which quotes these responses |
| Accuracy | Sample results compared with the sizes the shapes were drawn at, and with `pyproj.Geod` | Equal to the drawn sizes to the millimetre; +0.114% (area) from the ellipsoid, which is the UTM scale factor at that site |
| Load | A shapefile of 20,000 polygons through the API | Processed in 1.84 s; summed area exactly 50,000,000.0 m2 |
| Brief re-read | The assignment text checked line by line against the running service | Every item met; R8 needs the repository made public |
| CI on GitHub | The workflow in `.github/workflows/ci.yml` | Not verified from here: the repository is private. Both of its jobs were reproduced locally (rows 3 and 4). |
