#!/usr/bin/env python3
"""API Specification Validation Script.

Validates that the PostgreSQL API views match the OpenAPI specification.
"""

import sys
import yaml
from pathlib import Path


def load_openapi_spec(spec_path: str) -> dict:
    """Load OpenAPI specification from YAML file."""
    with open(spec_path, 'r') as f:
        return yaml.safe_load(f)


def get_expected_endpoints(spec: dict) -> dict:
    """Extract expected endpoints and their fields from OpenAPI spec."""
    endpoints = {}

    for path, methods in spec.get('paths', {}).items():
        endpoint_name = path.lstrip('/')

        # Get response schema
        get_method = methods.get('get', {})
        responses = get_method.get('responses', {})
        ok_response = responses.get('200', {})
        content = ok_response.get('content', {})
        json_content = content.get('application/json', {})
        schema = json_content.get('schema', {})

        # Handle array of items
        if schema.get('type') == 'array':
            items_ref = schema.get('items', {}).get('$ref', '')
            schema_name = items_ref.split('/')[-1] if items_ref else None

            # Get schema definition
            if schema_name:
                schema_def = spec.get('components', {}).get('schemas', {}).get(schema_name, {})
                fields = list(schema_def.get('properties', {}).keys())
            else:
                fields = []
        else:
            fields = []

        endpoints[endpoint_name] = {
            'description': get_method.get('summary', ''),
            'parameters': [p.get('name') for p in get_method.get('parameters', [])],
            'expected_fields': fields
        }

    return endpoints


def generate_view_check_sql(endpoints: dict) -> str:
    """Generate SQL to check if views exist and have expected columns."""
    sql_parts = []

    for endpoint, info in endpoints.items():
        view_name = f'api.{endpoint}'
        fields = info['expected_fields']

        # Check view exists
        sql_parts.append(f"""
-- Check {view_name} view
SELECT
    '{endpoint}' as endpoint,
    EXISTS (
        SELECT 1 FROM information_schema.views
        WHERE table_schema = 'api' AND table_name = '{endpoint}'
    ) as view_exists;
""")

        # Check columns
        if fields:
            sql_parts.append(f"""
-- Check columns for {view_name}
SELECT
    '{endpoint}' as endpoint,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'api' AND table_name = '{endpoint}'
ORDER BY ordinal_position;
""")

    return '\n'.join(sql_parts)


def print_validation_report(endpoints: dict):
    """Print a validation report."""
    print("=" * 60)
    print("API Specification Validation Report")
    print("=" * 60)
    print()

    for endpoint, info in endpoints.items():
        print(f"Endpoint: /{endpoint}")
        print(f"  Description: {info['description']}")
        print(f"  Query Parameters: {', '.join(info['parameters']) or 'none'}")
        print(f"  Expected Fields: {len(info['expected_fields'])}")

        if info['expected_fields']:
            for field in info['expected_fields'][:5]:
                print(f"    - {field}")
            if len(info['expected_fields']) > 5:
                print(f"    ... and {len(info['expected_fields']) - 5} more")
        print()

    print("=" * 60)
    print("View-to-Endpoint Mapping")
    print("=" * 60)
    print()
    print("| API Endpoint     | PostgreSQL View      |")
    print("|------------------|----------------------|")
    for endpoint in endpoints:
        print(f"| /{endpoint:<16} | api.{endpoint:<16} |")
    print()


def main():
    """Main entry point."""
    # Find spec file
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent
    spec_path = project_root / 'specs' / '001-tavr-data-infrastructure' / 'contracts' / 'api.yaml'

    if not spec_path.exists():
        print(f"ERROR: OpenAPI spec not found at {spec_path}")
        sys.exit(1)

    print(f"Loading spec from: {spec_path}")
    print()

    # Load and parse spec
    spec = load_openapi_spec(str(spec_path))

    # Extract endpoints
    endpoints = get_expected_endpoints(spec)

    # Print report
    print_validation_report(endpoints)

    # Generate SQL for database validation
    print("=" * 60)
    print("Database Validation SQL")
    print("=" * 60)
    print()
    print("Run the following SQL to validate views exist:")
    print()
    print("-" * 60)
    print(generate_view_check_sql(endpoints))
    print("-" * 60)
    print()

    # Summary
    print("=" * 60)
    print("Validation Summary")
    print("=" * 60)
    print()
    print(f"Total endpoints defined: {len(endpoints)}")
    print(f"Endpoints: {', '.join(['/' + e for e in endpoints.keys()])}")
    print()
    print("API views are defined in: edwards/sql/init_database.sql")
    print("PostgREST config: edwards/postgrest.conf")
    print()
    print("To test the API:")
    print("  1. Start PostgreSQL with init_database.sql")
    print("  2. Run: ./scripts/start_api.sh")
    print("  3. Test: curl http://localhost:3000/targets")
    print()


if __name__ == '__main__':
    main()
