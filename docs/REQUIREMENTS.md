# Requirements checklist

Source of truth: the assignment document, *Geospatial File Measurement API*. Each item below quotes
or closely paraphrases it. A box is ticked only when the item is implemented **and** has a passing
test; the two lines under each item say where.

Status: design phase. Nothing is implemented yet.

## Problem statement

> Build a backend service using either Django or FastAPI that accepts a geospatial file, processes
> the features within it, and returns measurement information. The service should accept either
> Shapefile or KML. The objective is to evaluate your ability to build a clean backend API, work
> with geospatial data, handle file processing, and write production-quality Python code. You are
> free to make architectural and implementation decisions beyond the minimum requirements.

## Minimum requirements

- [ ] **R1 Backend framework.** Django + Django REST Framework, or FastAPI.
  - Implemented in: pending
  - Tested by: pending
- [ ] **R2 File upload.** An API endpoint that accepts a geospatial file, `POST /api/files/`, accepting:
  - [ ] a `.zip` containing a Shapefile
    - Implemented in: pending
    - Tested by: pending
  - [ ] a `.kml`
    - Implemented in: pending
    - Tested by: pending
- [ ] **R3 File processing.** After upload, read the geospatial data and extract its features. For
  every feature identify at minimum:
  - [ ] Feature ID/index
  - [ ] Geometry type
  - [ ] Geometry
  - [ ] CRS
  - [ ] Properties/attributes
    - Implemented in: pending
    - Tested by: pending
- [ ] **R3a Unsupported geometry.** If a geometry type is not supported for measurement
  calculation, the API handles it gracefully rather than crashing.
  - Implemented in: pending
  - Tested by: pending
- [ ] **R4 Measurements** for supported geometries:
  - [ ] Polygon: area
  - [ ] LineString: length
  - [ ] Point: no measurement required
    - Implemented in: pending
    - Tested by: pending
- [ ] **R5 CRS handling.**
  - [ ] Files with geographic coordinates (for example EPSG:4326) are handled correctly.
  - [ ] Area and distance are never calculated directly in latitude/longitude degrees.
  - [ ] Geometry is transformed to an appropriate projected coordinate system before measuring.
  - [ ] The strategy for selecting the projected CRS is our own and is documented.
    - Implemented in: pending
    - Tested by: pending
- [ ] **R6 API design.** At minimum:
  - [ ] `POST /api/files/` uploads and processes a file.
    - Implemented in: pending
    - Tested by: pending
  - [ ] `GET /api/files/{id}/` returns information about the uploaded file. The document's example:
    `{"id": "abc123", "filename": "survey.kml", "feature_count": 120, "crs": "EPSG:4326", "status": "COMPLETED"}`
    - Implemented in: pending
    - Tested by: pending
  - [ ] `GET /api/files/{id}/measurements/` returns measurements for the features in the file.
    - Implemented in: pending
    - Tested by: pending
- [ ] **R7 Documentation.** A `README.md` containing:
  - [ ] Setup: how to run the application locally.
  - [ ] API: the available endpoints and example requests/responses.
  - [ ] Architecture: application structure, file-processing flow, measurement calculation flow, CRS handling.
  - [ ] Design Decisions: important technical decisions and alternatives considered.
- [ ] **R8 Submission.**
  - [ ] A public GitHub repository, link shared.
  - [ ] The README mentions learnings and future scope.

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
