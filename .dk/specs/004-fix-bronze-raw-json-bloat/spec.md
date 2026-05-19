# Feature: Fix Bronze Raw JSON Storage Bloat

## Summary

Two bronze-layer data transformation models unnecessarily store the entire raw API response in every unnested row, causing ~19 GB of redundant storage. The fix replaces the full response with only the individual element relevant to each row, matching the pattern already used by 19 other bronze models.

## User Scenarios & Testing

### US-1: Eliminate redundant storage in bronze rxnorm model (P1)

**As a** data platform operator, **I want** each unnested bronze row to store only its own data element, **so that** the rxnorm bronze table shrinks from ~19 GB to ~1 MB of raw JSON storage.

**Acceptance Scenarios:**

```gherkin
Given the rxnorm bronze model processes bulk API responses containing thousands of concepts
When a minConceptGroup response is unnested into individual concept rows
Then each row's raw_json column contains only that concept's JSON fragment, not the entire API response

Given the rxnorm bronze model processes relatedGroup responses
When concept properties are unnested from nested arrays
Then each row's raw_json contains only its own concept property JSON

Given the rxnorm bronze model processes idGroup or properties responses
When a single-concept response is processed
Then raw_json contains only the relevant JSON fragment (idGroup or properties object)
```

**Edge Cases:**
- Rows that were already processed under the old schema still link back to full response via raw_id
- NULL raw_json values should remain NULL (not replaced with empty fragments)

### US-2: Eliminate redundant storage in bronze purple_book model (P1)

**As a** data platform operator, **I want** each unnested purple book product row to store only its own product JSON, **so that** the purple_book bronze table eliminates redundant copies of the full API response per product.

**Acceptance Scenarios:**

```gherkin
Given the purple_book bronze model processes API responses containing multiple BLA products
When the _normalized_products array is unnested into individual product rows
Then each row's raw_json column contains only that product's JSON fragment

Given a purple_book response contains 200 products
When the model runs
Then total raw_json storage for that batch is ~200x smaller than before
```

**Edge Cases:**
- Products with missing fields should still store their individual JSON fragment
- The raw_source_id column continues to link back to the full response in mol_raw

### US-3: Verify no downstream breakage (P2)

**As a** data platform operator, **I want** confirmation that no downstream model reads raw_json from the affected bronze tables, **so that** the schema change causes zero breakage.

**Acceptance Scenarios:**

```gherkin
Given the raw_json column type changes from full-response to element-level JSON
When silver and gold models that depend on these bronze tables run
Then all downstream models produce identical output (they don't reference raw_json)
```

## Requirements

### Functional Requirements

- **FR-001**: The rxnorm bronze model must store element-level JSON in raw_json for all four format handlers (idGroup, properties, minConceptGroup, relatedGroup)
- **FR-002**: The purple_book bronze model must store the individual product JSON in raw_json instead of the full response_body
- **FR-003**: The raw_id / raw_source_id column must continue to reference the original raw table row for full-response access
- **FR-004**: No downstream silver or gold model may break as a result of this change
- **FR-005**: The fix must follow the same pattern used by the 19 other bronze models that already store element-level raw_json

### Key Entities

| Entity | Description | Key Attributes |
|--------|-------------|----------------|
| Bronze rxnorm row | One RxNorm concept | rxcui, name, tty, raw_json (element), raw_id |
| Bronze purple_book row | One BLA product | bla_number, product_number, raw_json (element), raw_source_id |

## Success Criteria

- **SC-001**: The rxnorm bronze raw_json column stores element-level JSON (~50 bytes average) instead of full response (~1 MB)
- **SC-002**: The purple_book bronze raw_json column stores product-level JSON instead of full response
- **SC-003**: Zero downstream model failures after the change
- **SC-004**: Storage reduction of >99% on raw_json for both affected tables

## Assumptions

- The raw_json column is not read by any downstream silver/gold model (confirmed by audit of all 21 bronze models and their dependents)
- The raw_id / raw_source_id column provides sufficient linkage to the full response when needed
- SQLMesh will handle the schema evolution on the next incremental run (INCREMENTAL_BY_UNIQUE_KEY will upsert with the new smaller raw_json)
- Existing rows with bloated raw_json will be replaced as new data is ingested or when a full refresh is triggered
