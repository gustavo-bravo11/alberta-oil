# Geospatial Transform Plan with GeoPolars

## Pipeline Flow

```text
NRCan ArcGIS API
    ↓
Raw GeoJSON
    ↓
GeoPolars validation + transforms
    ↓
GeoParquet
    ↓
PostGIS
```

## Transform Goals

- **Validate CRS** and standardize to `EPSG:4326` for storage and exchange.
- **Validate geometry** so there are no null, empty, or invalid geometries.
- **Normalize geometry types**:
  - pipeline corridors → `MULTIPOLYGON`
  - facilities → `POINT`
- **Preserve source IDs and useful source attributes** for lineage and future reprocessing.
- Add stable analytical identifiers such as:
  - `pipeline_id`
  - `system_name`
  - `geometry_role`
  - `project_status`
  - `source_name`
  - `source_layer_id`
  - `geometry_method`

## Join Strategy

Use `pipeline_id` as the stable key connecting spatial and non-spatial tables:

```text
pipeline_geometry.pipeline_id
        ↕
pipeline_facility.pipeline_id
        ↕
pipeline_flow.pipeline_id
        ↕
pipeline_capacity.pipeline_id
```

Example values:

```text
tmx_existing
tmx_expansion
enbridge_mainline
keystone
```

Do **not** rely on source company names or free-text pipeline names as join keys.

## Curated Spatial Outputs

Recommended transformed outputs:

```text
data/transformed/geospatial/
    pipeline_geometry.parquet
    pipeline_facilities.parquet
```

Use **GeoParquet** as the intermediate spatial format before loading into PostGIS.

## Geometry Modeling Rule

Preserve the NRCan Trans Mountain geometry as a **corridor polygon**.

If a centerline is later derived for visualization or analysis, store it separately and explicitly identify it as derived, for example:

```text
geometry_method = "derived_centerline"
```

Do not overwrite or replace the source corridor geometry with the derived centerline.

## Design Principle

Keep the source geometry and lineage intact, while adding a clean analytical layer that makes future joins and PostGIS queries straightforward.

The final model should distinguish:

```text
source geometry
derived geometry
facilities
flow observations
capacity observations
```

while connecting them through stable analytical identifiers such as `pipeline_id`.
