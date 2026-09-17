# Alberta Oil Load and Map Next Steps

Date: 2026-09-16

## Today's completed work

The extract, validation, and transform layers are ready to become the source
for a database load.

- Validators are separated by source in `a_0_pipeline_validation.py`,
  `b_0_production_validation.py`, and `c_0_rail_validation.py`.
- Orchestrator task names are source-based to match transforms:
  `validate.pipeline`, `validate.production`, and `validate.rail`. Stage
  prefixes stay in validator filenames only.
- `full` validates every source before transforming. Validators run in parallel.
- Pipeline stages 1 then 2 remain sequential; that branch runs in parallel
  with production and rail transforms.
- All task execution now uses consistent `Starting:` and `Completed:` output.
- Shared validation-history and source-metadata writes are safe for concurrent
  tasks.
- Unparseable rail update dates fall back to the final day of the most recent
  data month, with a warning and an `ASSUMED:` source label.
- The obsolete Keystone reconciliation exception console message was removed.
- Trans Mountain capacity remains system-scoped. Its total flow is the sum of
  non-system key-point observations, and the capacity must not be assigned to
  an arbitrary map point.
- 26 tests pass.

Relevant commits:

- `098e1af` - validation orchestration and transforms
- `dd6e467` - validation and orchestration tests
- `b77d7a6` - completed implementation briefs

## Current outputs

`project/data/transformed/` contains:

- `pipeline_flow.csv`: monthly key-point flow observations, including source
  coordinates.
- `pipeline_capacity.csv`: monthly capacity observations with `capacity_basis`
  and `capacity_scope` (`key_point` or `system`).
- `western_canada_estimated_production.csv`: production by month, oil type, and
  constraint category.
- `monthly_rail_exports.csv`: monthly crude-by-rail exports.
- `source_metadata.csv`: report dates and workbook lineage.

Raw inputs, validated inputs, quarantined rows, validation reports, and the
retrieval log remain the audit trail.

## Recommended architecture

Use PostgreSQL with PostGIS for the published data store, then expose it via a
read-only API to a MapLibre GL JS web map.

```text
CER files -> extract -> validate -> transform -> PostgreSQL/PostGIS
                                                    |
                                                    v
                                             read-only API -> web map/charts
```

MapLibre avoids a proprietary map token and can render GeoJSON or vector tiles.
Choose the web framework and hosting only after the local database/API contract
works.

## Work required before a public map

### Database foundation

The Compose file is a starting point, not a runnable database platform. First:

1. Use a PostGIS-enabled PostgreSQL image.
2. Correct `POSGRES_*`/`POSTGREST_PASSWORD` environment-variable typos and the
   duplicated Flyway container name.
3. Add a database health check and make Flyway wait for it.
4. Add `project/db/migrations/` and a baseline Flyway migration.
5. Add a Python PostgreSQL driver and document the Compose workflow.

### Load schema and loader

Create a small query-oriented schema:

- `pipeline` and `pipeline_location` for stable identities and key-point
  geometry.
- `pipeline_flow_monthly` at the observation grain: date, pipeline, key point,
  product, direction, and trade type.
- `pipeline_capacity_monthly` at date, pipeline, and capacity-basis grain;
  retain capacity scope and never invent a point for system capacity.
- `production_monthly`, `rail_exports_monthly`, `source_metadata`, and a
  run/lineage table.
- `pipeline_route` for authoritative route-line geometry and its licence.

Use natural unique keys and upserts or replace-by-run semantics so a repeated
successful run cannot duplicate facts. Add loaders as `load.pipeline`,
`load.production`, and `load.rail` only after the migration exists.

Test loading against a temporary PostGIS database: required columns, row-count
reconciliation, repeat-run idempotency, transaction rollback, geometry validity,
and source-date freshness.

### Geometry and map integrity

The source coordinates support a key-point map, but they do not prove the line
route between points. Before publishing lines:

1. Select an authoritative, redistributable route dataset for the three CER
   pipelines.
2. Record source, licence, attribution, retrieval date, and publication rights.
3. Store routes separately as PostGIS lines. Do not join points with lines
   unless clearly labelled schematic.
4. Match key points to normalized locations and flag duplicates, unmatched
   locations, and implausible coordinates.
5. Render system capacity as a pipeline-level metric or line style, never a
   point measurement.

### API and first map

The first API should offer pipelines/routes, flow by month and filters,
capacity by month and pipeline, production/rail time series, and latest source
metadata. Return explicit freshness dates.

The minimum public map should include routes, clickable key-point flow circles,
a month selector, pipeline/product/direction filters, a scope-aware capacity
panel, source attribution, and an accessible non-map table or chart.

Do not depict a point observation as flow along the whole route, and do not
depict system capacity as a key-point reading.

## Proposed implementation order

1. Repair Compose and add PostGIS plus the baseline Flyway migration.
2. Confirm database grain, keys, retention, and source-revision policy.
3. Implement and integration-test the fact loaders locally.
4. Register load tasks and add load after transform in `full`.
5. Acquire and quality-check route geometry.
6. Build the read-only API and test map queries.
7. Build a local MapLibre prototype, then choose hosting, deployment,
   monitoring, backups, and scheduled refresh behaviour.

## Decisions needed

- Which public route-geometry source and licence are acceptable?
- Should the initial release cover only the three CER pipelines?
- What hosting environment and budget should the site use?
- How often should production refresh, and should a failed refresh retain the
  last successful published data?
- Should historical source revisions overwrite facts or remain versioned by run?
