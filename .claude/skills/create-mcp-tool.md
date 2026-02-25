# Create New MCP Data Retrieval Tool

## Trigger
When the user asks to add a new MCP data retrieval tool, external API source, or data pipeline adapter.

## Prerequisites
- Raw table must exist for the source (in `mol_raw` or `raw` schema)
- Bronze SQLMesh model must exist (or be created)
- Silver SQLMesh model must exist (or be created)

## Steps

### 1. Create Adapter File

Create `src/dk_data/services/mcp/adapters/{source_name}.py`:

```python
"""MCP Adapter: {Source Name}

Normalizes {Source API} responses to match {raw_schema}.{raw_table} format.
"""

from .base import BaseAdapter


class Adapter(BaseAdapter):
    """Adapter for {Source Name} API responses."""

    @property
    def source_name(self) -> str:
        return "{source_name}"

    @property
    def raw_table(self) -> str:
        return "{raw_table_name}"

    @property
    def raw_schema(self) -> str:
        return "{mol_raw|raw}"  # mol_raw for molecule-specific, raw for general

    def normalize(self, api_response: dict) -> dict:
        """Normalize API response to match raw table response_body format.

        The output dict must be compatible with the corresponding bronze model's
        response_body JSONB extraction patterns.
        """
        # Extract and normalize fields from api_response
        return {
            # Map API response fields to raw table response_body format
            # Match the field names expected by the bronze SQLMesh model
        }
```

### 2. Register in Tool Registry

Add the tool to `TOOL_REGISTRY` in `src/dk_data/services/mcp/tool_registry.py`:

```python
"{source-name}-search": ToolDefinition(
    name="{source-name}-search",
    description="Search {Source Name} for {description}",
    tier="{direct_query|fetch_filter|supplementary}",
    raw_table="{raw_table_name}",
    raw_schema="{mol_raw|raw}",
    adapter_module="dk_data.services.mcp.adapters.{source_name}",
    api_base_url="{API_BASE_URL}",
    input_schema={
        "type": "object",
        "properties": {
            "drug_name": {"type": "string", "description": "Drug/molecule name"},
        },
        "required": ["drug_name"],
    },
),
```

### 3. Create Adapter Unit Test

Add to `tests/test_mcp_adapters.py`:

```python
class Test{SourceName}Adapter:
    def test_normalize_extracts_key_fields(self):
        from dk_data.services.mcp.adapters.{source_name} import Adapter
        adapter = Adapter()
        mock_response = {
            # Sample API response
        }
        result = adapter.normalize(mock_response)
        assert result.get("{key_field}") is not None

    def test_source_name(self):
        from dk_data.services.mcp.adapters.{source_name} import Adapter
        assert Adapter().source_name == "{source_name}"

    def test_raw_table(self):
        from dk_data.services.mcp.adapters.{source_name} import Adapter
        assert Adapter().raw_table == "{raw_table_name}"
```

### 4. Add Bronze Model Contract Test

Add to `tests/test_bronze_model_contracts.py`:

```python
class TestBronze{SourceName}:
    def test_model_exists(self):
        sql = _read_model_sql("bronze/{source_name}.sql")
        assert sql is not None

    def test_model_kind(self):
        sql = _read_model_sql("bronze/{source_name}.sql")
        block = _extract_model_block(sql)
        assert "INCREMENTAL_BY_TIME_RANGE" in block

    def test_grain(self):
        sql = _read_model_sql("bronze/{source_name}.sql")
        block = _extract_model_block(sql)
        assert "grain" in block.lower()
```

### 5. Update LAYER_MODELS

Add the source to the appropriate layer list in `src/dk_data/ingestion/transform_molecules.py`:

```python
LAYER_MODELS = {
    # ... existing entries ...
    "ip_bronze": [
        # ... add: "bronze.{source_name}",
    ],
    "ip_silver": [
        # ... if silver model exists: "silver.{related_silver}",
    ],
}
```

## Checklist

- [ ] Raw table exists (`{raw_schema}.{raw_table}`)
- [ ] Adapter file created (`src/dk_data/services/mcp/adapters/{source_name}.py`)
- [ ] Adapter implements `normalize()`, `source_name`, `raw_table`, `raw_schema`
- [ ] Tool registered in `TOOL_REGISTRY` with correct tier
- [ ] Adapter unit test created
- [ ] Bronze model contract test added
- [ ] LAYER_MODELS updated in `transform_molecules.py`
- [ ] `sqlmesh plan --no-prompts` compiles without errors
- [ ] Total tool count in `TOOL_REGISTRY` matches expected (currently 28)

## Tier Classification

| Tier | Description | Count |
|------|-------------|-------|
| `direct_query` | Real-time API query, results normalized to raw format | 19 |
| `fetch_filter` | Fetch bulk data, filter client-side | 4 |
| `supplementary` | Context/infrastructure data, less frequently updated | 5 |

## Schema Convention

| Schema | Usage |
|--------|-------|
| `mol_raw` | Molecule-specific data (ClinicalTrials, ChEMBL, OpenFDA, etc.) |
| `raw` | General/cross-cutting data (PubMed, EMA, HTA, SEC, etc.) |
