# API reference

| Method and path | Purpose |
| --- | --- |
| `POST /api/files/` | Upload and process a file |
| `GET /api/files/{id}/` | Information about an uploaded file |
| `GET /api/files/{id}/measurements/` | Measurements for the features in the file |
| `GET /api/files/` | List uploaded files, newest first |
| `DELETE /api/files/{id}/` | Delete a file and its measurements |
| `GET /health` | Liveness check |

The first three are the brief's, with exactly its paths. List and delete are added so that a file
can be found again without its id, and removed. The same paths without the trailing slash also
work, with no redirect.

This is the full reference; the [README](../README.md#api) has the short tour.
**Every response below was copied from the running service**, using the files in `samples/`. On
Windows PowerShell, use `curl.exe` instead of `curl`.

## Upload a file

`POST /api/files/` takes a multipart form with one field, `file`: a `.kml`, or a `.zip`
containing one shapefile (`.shp`, `.shx`, `.dbf`; `.prj` and `.cpg` if present).

```bash
curl -i -F "file=@samples/survey.kml" http://127.0.0.1:8000/api/files/
```

```http
HTTP/1.1 201 Created
content-type: application/json
location: /api/files/2be4806a-c825-4018-ae15-da3c95d9f5e7/
x-request-id: 57ba587ea1384637917adaa2e9f437bc
```

```json
{
  "id": "2be4806a-c825-4018-ae15-da3c95d9f5e7",
  "filename": "survey.kml",
  "format": "KML",
  "size_bytes": 2407,
  "status": "COMPLETED",
  "feature_count": 7,
  "crs": "EPSG:4326",
  "crs_assumed": false,
  "error": null,
  "created_at": "2026-10-08T15:51:51.612485Z",
  "processed_at": "2026-10-08T15:51:51.644990Z",
  "links": {
    "self": "/api/files/2be4806a-c825-4018-ae15-da3c95d9f5e7/",
    "measurements": "/api/files/2be4806a-c825-4018-ae15-da3c95d9f5e7/measurements/"
  }
}
```

The file is read and measured before the response is sent. **The HTTP status says whether the
upload was accepted; the `status` field says how processing ended** (`COMPLETED` or `FAILED`).

## Get file information

```bash
curl http://127.0.0.1:8000/api/files/2be4806a-c825-4018-ae15-da3c95d9f5e7/
```

Returns the same resource as the upload response. The five fields in the brief's example (`id`,
`filename`, `feature_count`, `crs`, `status`) are always present.

| Field | Meaning |
| --- | --- |
| `status` | `PROCESSING`, `COMPLETED` or `FAILED` |
| `feature_count` | Number of features; `null` until processing succeeds |
| `crs` | The file's CRS as `EPSG:<code>`; `null` if unknown |
| `crs_assumed` | `true` when a shapefile had no `.prj` and EPSG:4326 was assumed |
| `error` | Why processing failed, when `status` is `FAILED` |

## Get measurements

```bash
curl http://127.0.0.1:8000/api/files/2be4806a-c825-4018-ae15-da3c95d9f5e7/measurements/
```

One item per feature. Each carries the feature's index, id, geometry type, geometry, CRS and
properties, together with its measurement. Two of the seven items are shown in full:

```json
{
  "file_id": "2be4806a-c825-4018-ae15-da3c95d9f5e7",
  "crs": "EPSG:4326",
  "summary": {
    "total_area_m2": 187499.999,
    "total_length_m": 1700.0,
    "total_geodesic_area_m2": 187285.37,
    "total_geodesic_length_m": 1699.027,
    "measured": 4,
    "not_required": 2,
    "unsupported": 1,
    "failed": 0
  },
  "pagination": { "limit": 100, "offset": 0, "total": 7 },
  "links": {
    "self": "/api/files/2be4806a-c825-4018-ae15-da3c95d9f5e7/measurements/?limit=100&offset=0",
    "file": "/api/files/2be4806a-c825-4018-ae15-da3c95d9f5e7/",
    "next": null,
    "prev": null
  },
  "items": [
    {
      "feature_index": 0,
      "source_id": "field-a",
      "geometry_type": "Polygon",
      "geometry": {
        "type": "Polygon",
        "coordinates": [[
          [77.584602871, 12.967847203, 0.0],
          [77.584626199, 12.970105574, 0.0],
          [77.58094178, 12.970142157, 0.0],
          [77.580918484, 12.96788378, 0.0],
          [77.584602871, 12.967847203, 0.0]
        ]]
      },
      "crs": "EPSG:4326",
      "properties": { "Name": "Field A", "crop": "ragi", "owner": "Asha" },
      "measurement": {
        "type": "AREA",
        "value": 100000.0,
        "unit": "m2",
        "method": "PROJECTED",
        "projected_crs": "EPSG:32643",
        "geodesic_value": 99885.822,
        "status": "MEASURED",
        "reason": null,
        "geometry_repaired": false
      }
    },
    {
      "feature_index": 6,
      "source_id": "note-1",
      "geometry_type": "GeometryCollection",
      "geometry": { "type": "GeometryCollection", "geometries": ["(a Point and a LineString, omitted here)"] },
      "crs": "EPSG:4326",
      "properties": { "Name": "Access note" },
      "measurement": {
        "type": null,
        "value": null,
        "unit": null,
        "method": null,
        "projected_crs": null,
        "geodesic_value": null,
        "status": "UNSUPPORTED",
        "reason": "A GeometryCollection has no single area or length.",
        "geometry_repaired": false
      }
    }
  ]
}
```

All seven results for `survey.kml`:

| # | `source_id` | Geometry | `value` | `projected_crs` | `geodesic_value` | `status` |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | `field-a` | Polygon | 100000.0 m2 | EPSG:32643 | 99885.822 m2 | MEASURED |
| 1 | `field-b` | Polygon with a hole | 87499.999 m2 | EPSG:32643 | 87399.548 m2 | MEASURED |
| 2 | `line-1` | LineString | 1000.0 m | EPSG:32643 | 999.427 m | MEASURED |
| 3 | `line-2` | LineString | 700.0 m | EPSG:32643 | 699.6 m | MEASURED |
| 4 | `gcp-1` | Point | none | | none | NOT_REQUIRED |
| 5 | `gcp-2` | Point | none | | none | NOT_REQUIRED |
| 6 | `note-1` | GeometryCollection | none | | none | UNSUPPORTED |

**Measurement fields**

| Field | Meaning |
| --- | --- |
| `type` | `AREA` (polygons), `LENGTH` (lines), or `null` |
| `value`, `unit` | The number, rounded to the millimetre, and `m2` or `m` |
| `method` | `PROJECTED` (measured in `projected_crs`) or `GEODESIC` (measured on the WGS 84 ellipsoid) |
| `projected_crs` | The UTM zone the feature was measured in |
| `geodesic_value` | The same measurement on the WGS 84 ellipsoid, in the same unit. This is the figure a GIS shows when it measures on the ellipsoid, as QGIS's `$area` does. Equal to `value` when `method` is `GEODESIC` |
| `status` | `MEASURED`, `NOT_REQUIRED` (points), `UNSUPPORTED`, or `FAILED` |
| `reason` | Why a feature was not measured |
| `geometry_repaired` | `true` when an invalid polygon was repaired before measuring |

**Pagination:** `limit` (default 100, maximum 1000) and `offset`. `summary` always covers the whole
file. With the shapefile sample:

```bash
curl -F "file=@samples/parcels.zip" http://127.0.0.1:8000/api/files/
curl "http://127.0.0.1:8000/api/files/bb1cc07b-8f77-4ab3-8e6a-fe9b88275e2a/measurements/?limit=2&offset=1"
```

```json
{
  "file_id": "bb1cc07b-8f77-4ab3-8e6a-fe9b88275e2a",
  "crs": "EPSG:32643",
  "summary": {
    "total_area_m2": 100000.0,
    "total_length_m": 0.0,
    "total_geodesic_area_m2": 99885.916,
    "total_geodesic_length_m": 0.0,
    "measured": 3,
    "not_required": 0,
    "unsupported": 0,
    "failed": 0
  },
  "pagination": { "limit": 2, "offset": 1, "total": 3 },
  "links": {
    "self": "/api/files/bb1cc07b-8f77-4ab3-8e6a-fe9b88275e2a/measurements/?limit=2&offset=1",
    "file": "/api/files/bb1cc07b-8f77-4ab3-8e6a-fe9b88275e2a/",
    "next": null,
    "prev": "/api/files/bb1cc07b-8f77-4ab3-8e6a-fe9b88275e2a/measurements/?limit=2&offset=0"
  },
  "items": ["(parcels P-102 and P-103, omitted here)"]
}
```

**Filtering, and leaving the geometry out.** Three more query parameters:

| Parameter | Effect |
| --- | --- |
| `geometry_type` | Only features of that type: `Point`, `LineString`, `Polygon`, their `Multi` forms, or `GeometryCollection`. Repeat it to allow several |
| `status` | Only features whose measurement has that status. Repeat it to allow several |
| `include_geometry=false` | Leaves `geometry` out of every item |

`pagination.total` counts the features the filters leave, `summary` still covers the whole file,
and the page links repeat the filters. With `survey.kml`:

```bash
curl "http://127.0.0.1:8000/api/files/{id}/measurements/?geometry_type=Polygon"
curl "http://127.0.0.1:8000/api/files/{id}/measurements/?status=UNSUPPORTED"
curl "http://127.0.0.1:8000/api/files/{id}/measurements/?include_geometry=false"
```

| Request | `pagination.total` | Items |
| --- | --- | --- |
| `?geometry_type=Polygon` | 2 | `field-a`, `field-b` |
| `?status=UNSUPPORTED` | 1 | `note-1` |
| `?geometry_type=Polygon&geometry_type=LineString&status=MEASURED` | 4 | the two fields and the two lines |
| `?include_geometry=false` | 7 | all seven, in 2,793 bytes where the full response is 3,966 |

A feature keeps its `feature_index` whatever the filter leaves around it. Without its geometry an
item has no `geometry` key at all, which keeps it apart from a feature that has no geometry
(`"geometry": null`).

## List files

`GET /api/files/` returns every upload, newest first, including uploads that `FAILED`. Each item
is the same resource `GET /api/files/{id}/` returns. `limit` (default 100, maximum 1000) and
`offset` page through them. With both sample files uploaded:

```bash
curl "http://127.0.0.1:8000/api/files/?limit=1"
```

```json
{
  "pagination": { "limit": 1, "offset": 0, "total": 2 },
  "links": {
    "self": "/api/files/?limit=1&offset=0",
    "next": "/api/files/?limit=1&offset=1",
    "prev": null
  },
  "items": [
    {
      "id": "3b0f3ec1-ee7c-40aa-8f69-20d110e7d54e",
      "filename": "parcels.zip",
      "format": "SHAPEFILE",
      "size_bytes": 1071,
      "status": "COMPLETED",
      "feature_count": 3,
      "crs": "EPSG:32643",
      "crs_assumed": false,
      "error": null,
      "created_at": "2026-10-10T10:03:49.378866Z",
      "processed_at": "2026-10-10T10:03:49.407569Z",
      "links": {
        "self": "/api/files/3b0f3ec1-ee7c-40aa-8f69-20d110e7d54e/",
        "measurements": "/api/files/3b0f3ec1-ee7c-40aa-8f69-20d110e7d54e/measurements/"
      }
    }
  ]
}
```

## Delete a file

`DELETE /api/files/{id}/` removes the file record and every feature stored for it. It answers
204 with no body; the id then answers 404, to a second delete as well.

```bash
curl -i -X DELETE http://127.0.0.1:8000/api/files/3b0f3ec1-ee7c-40aa-8f69-20d110e7d54e/
```

```http
HTTP/1.1 204 No Content
x-request-id: a2149ad6ffa24e0a9ac33944a9252552
```

A file that is still `PROCESSING` cannot be deleted (409): the request that uploaded it is still
writing to it.

## Errors

Every error has one shape, RFC 9457 Problem Details, sent as `application/problem+json`.

```bash
curl -i -F "file=@parcels.zip" http://127.0.0.1:8000/api/files/    # an archive with no .dbf
```

```http
HTTP/1.1 422 Unprocessable Entity
content-type: application/problem+json
```

```json
{
  "type": "about:blank",
  "title": "Unprocessable Content",
  "status": 422,
  "detail": "The archive is missing parcels.dbf, which a shapefile requires.",
  "instance": "/api/files/"
}
```

| Status | When | Example `detail` |
| --- | --- | --- |
| 400 | Malformed request: no `file` field, `limit` or `offset` out of range, an unknown `geometry_type` or `status` | `The request is not valid.` plus an `errors` list naming `query.limit` |
| 404 | Unknown file id or path | `No uploaded file has this id.` |
| 405 | A method the path does not accept | `Method Not Allowed`, with an `Allow` header naming every method it does accept, for example `DELETE, GET` |
| 409 | Measurements requested for a file that is not `COMPLETED`, or a delete while it is `PROCESSING` | `The file could not be processed, so it has no measurements. ...` |
| 413 | Upload larger than the limit | `The upload is larger than the limit of 52428800 bytes.` |
| 415 | Not a `.zip` or `.kml`, or the content is not what the extension claims | `Only .kml files and .zip archives containing a shapefile are accepted.` |
| 422 | A real zip or KML that cannot be accepted | `The archive is missing parcels.dbf, which a shapefile requires.` |
| 500 | Unexpected failure | `An unexpected error occurred.` (the traceback goes to the log, with the request id) |

**An accepted file that cannot be read** is not a 4xx. The upload returns 201 with
`"status": "FAILED"` and the reason, so the record explains what happened:

```json
{
  "id": "1a095c58-5aed-46b8-b285-de40fc301d7c",
  "filename": "survey.kml",
  "status": "FAILED",
  "feature_count": null,
  "crs": null,
  "error": "The file could not be read: ERROR parsing kml upload.kml :unclosed token on line 10 at offset 204"
}
```

(Other fields omitted. `upload.kml` is the fixed name the server stores every KML upload under;
the client's file name is never used as a path.)

Every response carries an `X-Request-ID` header. Send your own and it is kept; the same id is
written on every log line for that request.
