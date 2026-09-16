# Alberta Oil Pipeline Modeling — Recommended Transformation Changes

**STATUS: COMPLETED**

## Goal

Preserve the CER data as faithfully as possible while preparing it for:

- cross-pipeline comparison,
- DuckDB analytics,
- future geospatial modeling,
- and later database loading.

The main principle is to **separate flow observations from capacity observations** rather than forcing them into a single spatial interpretation.

---

## 1. Keep `pipeline_flow` and `pipeline_capacity` as separate outputs

Continue producing two transformed tables:

### `pipeline_flow`

Represents:

> Throughput reported at a specific CER key point for a specific month and product.

This is the table that should drive the future geospatial point layer.

### `pipeline_capacity`

Represents:

> Capacity reported by CER for a pipeline, key point, or system-level scope for a specific month.

Capacity does **not** always correspond directly to the same physical locations where throughput is reported.

Do not force these tables into a one-to-one join.

---

## 2. Change the Enbridge flow filter

The current Enbridge flow logic is:

```python
flow_rows = frame.filter(
    (pl.col("key_point") != "system")
    & pl.col("available_capacity_m3_d").is_not_null()
)
```

This makes capacity availability determine whether a valid flow observation survives.

That removes legitimate throughput observations such as locations where CER reports:

- key point,
- coordinates,
- direction,
- product,
- and throughput,

but does **not** report available capacity.

Instead, flow should be retained based on whether throughput exists.

Recommended logic:

```python
flow_rows = frame.filter(
    (pl.col("key_point") != "system")
    & pl.col("throughput_m3_d").is_not_null()
)
```

Additional source-specific rules can still exclude obvious helper/summary rows if required.

### Why

`pipeline_flow` should answer:

> Where did CER report flow?

It should not answer:

> Where did CER report both flow and capacity?

Capacity belongs in the separate capacity model.

---

## 3. Keep the current Enbridge capacity interpretation explicit

Continue treating `ex-Gretna` as the selected Enbridge Mainline capacity observation if that is the CER benchmark being used.

However, do not imply that this value is a measured capacity for every physical segment of the Enbridge network.

Add an explicit field such as:

```text
capacity_scope
```

Suggested value:

```text
key_point
```

The existing `capacity_basis` should remain:

```text
ex-Gretna
```

This preserves the distinction between:

- **where / on what basis CER reports the capacity**, and
- the broader physical pipeline network.

---

## 4. Preserve committed and uncommitted volumes

The current transform drops the CER committed/uncommitted fields during `base_frame()`.

Retain them.

Normalize them in the same way as the other `1000 m3/d` fields.

Suggested transformed fields:

```text
committed_volume_m3_d
committed_volume_barrels_d
uncommitted_volume_m3_d
uncommitted_volume_barrels_d
```

These should be **nullable**.

Do not fill historical missing values with zero.

`NULL` means:

> CER did not report this breakdown for this observation/time period.

It does **not** mean the volume was zero.

---

## 5. Keep total throughput as the canonical comparable metric

Across pipelines and history, continue using:

```text
total_throughput_m3_d
total_throughput_barrels_d
```

as the main comparable capacity-table throughput metric.

Committed and uncommitted volumes are additional detail.

Conceptually:

```text
total throughput
├── committed volume      (nullable)
└── uncommitted volume    (nullable)
```

Where both components are reported, they should approximately reconcile to total throughput.

Historical periods can therefore still be compared even when the committed/uncommitted split is unavailable.

---

## 6. Add a validation check for committed + uncommitted

Where both fields are available, validate:

```text
committed_volume + uncommitted_volume ≈ total_throughput
```

Allow a small tolerance for CER rounding.

This should be a validation/data-quality rule, not a transformation used to overwrite the reported total.

The reported or existing derived total remains the canonical metric.

---

## 7. Trans Mountain modeling

Current Trans Mountain logic:

1. removes the `system` row from the geographic flow output,
2. sums throughput reported at the non-system key points,
3. reads available capacity from the `system` row,
4. compares the summed throughput with the system capacity.

This interpretation is reasonable given the source structure and should remain unless further raw-data validation contradicts it.

### Keep two concepts separate

The flow table should preserve locations such as:

```text
Burnaby
Sumas
Westridge
```

as individual throughput observations.

The capacity table should retain the system capacity observation with:

```text
capacity_scope = "system"
```

Do **not** assign that system capacity individually to Burnaby, Sumas, or Westridge.

### Committed / uncommitted data

When CER provides the committed and uncommitted breakdown on the system/total row, retain those values in `pipeline_capacity`.

For periods before CER reports them, leave them `NULL`.

---

## 8. Keystone modeling

Keystone can continue to be modeled around its CER key point.

Use:

```text
capacity_scope = "key_point"
```

and retain the corresponding `capacity_basis`.

If committed and uncommitted fields are available for some historical periods, retain them using the same nullable schema as Trans Mountain.

This allows one capacity schema across pipelines without pretending every source has identical reporting.

---

## 9. Recommended `pipeline_capacity` schema

A useful target schema is:

```text
date
pipeline_original
pipeline_standard

capacity_basis_original
capacity_basis_standard
capacity_scope

total_throughput_m3_d
total_throughput_barrels_d

committed_volume_m3_d
committed_volume_barrels_d
uncommitted_volume_m3_d
uncommitted_volume_barrels_d

available_capacity_m3_d
available_capacity_barrels_d
reported_available_capacity_utilization

reason_for_variance
date_transformed
```

Potential `capacity_scope` values:

```text
system
key_point
```

Additional values can be introduced later if the CER data requires them, for example:

```text
segment
facility
```

Do not invent those scopes unless the source semantics support them.

---

## 10. Recommended `pipeline_flow` schema

The existing schema is fundamentally good:

```text
date
pipeline_original
pipeline_standard

key_point_original
key_point_standard

trade_type_original
trade_type_standard
product
direction_of_flow

latitude
longitude

throughput_m3_d
throughput_barrels_d

date_transformed
```

The important change is that inclusion in this table should depend primarily on having a valid throughput observation, **not on having an available-capacity value**.

This table should become the primary factual source for the future geospatial point layer.

---

## 11. Future DuckDB geospatial model

Do not try to turn every throughput observation into continuous flow along the full pipeline geometry.

The eventual model should distinguish:

### Pipeline geometry

The physical route / line geometry.

### Flow observations

Point observations such as:

```text
pipeline
key_point
date
product
throughput
geometry / coordinates
```

### Capacity observations

Observations whose scope may be:

```text
system
key_point
```

A system capacity value should not automatically be attached to every pipeline segment.

---

## 12. Important modeling principle

Avoid assumptions such as:

> Throughput measured at two key points means the same volume flowed continuously through every segment between them.

CER key-point data represents reported observations.

It does not necessarily describe continuous physical flow everywhere along the route.

The map should therefore distinguish between:

- **known pipeline geometry**, and
- **measured/reported throughput observations**.

This keeps the visualization analytically honest while still allowing a rich geospatial experience.

---

## Suggested implementation order

1. Update `base_frame()` to retain committed/uncommitted fields.
2. Normalize those fields into m³/day and barrels/day.
3. Change the Enbridge flow filter from capacity-based to throughput-based.
4. Add committed/uncommitted fields to `CAPACITY_COLUMNS`.
5. Add `capacity_scope`.
6. Populate source-specific scope values:
   - Enbridge: `key_point`
   - Keystone: `key_point`
   - Trans Mountain: `system`
7. Preserve `NULL` where committed/uncommitted values are unavailable.
8. Add validation that committed + uncommitted approximately equals total throughput where both exist.
9. Regenerate `pipeline_flow.csv` and `pipeline_capacity.csv`.
10. Compare old vs new row counts and inspect representative months before loading into DuckDB.

---

## Codex implementation note

Implement these changes conservatively.

Do not redesign unrelated transformation logic.

Preserve the existing source-specific transformations unless a change is explicitly described above.

After implementation, report:

- files changed,
- schema changes,
- row-count differences by pipeline,
- any months where committed + uncommitted does not reconcile with total throughput,
- and any source rows whose interpretation remains ambiguous.
