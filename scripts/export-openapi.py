#!/usr/bin/env python3
"""
Export OpenAPI specification from the DK Data Platform API.

Usage:
    python scripts/export-openapi.py [--output docs/openapi.json]

This script imports the FastAPI app and exports its OpenAPI schema
without needing to run the server.
"""

import argparse
import json
import sys
from pathlib import Path

# Add the src directory to the path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


def export_openapi(output_path: str = "docs/openapi.json") -> None:
    """Export the OpenAPI specification to a JSON file."""
    try:
        # Import the FastAPI app
        from dk_data.ingestion.batch.api import app

        # Get the OpenAPI schema
        openapi_schema = app.openapi()

        # Update metadata
        openapi_schema["info"]["title"] = "DK Data Platform API"
        openapi_schema["info"]["description"] = """
## DK Data Platform API

A comprehensive API for drug/molecule data aggregation, entity resolution, and analytics.

### Features

- **Molecule Search**: Fuzzy search across 18+ data sources
- **Entity Resolution**: Automatic identifier detection and cross-reference
- **Data Ingestion**: Trigger and monitor batch data sync jobs
- **Pipeline Monitoring**: Track ingestion status and data quality
- **Gold Layer Access**: Query aggregated molecule profiles

### Authentication

Production endpoints require JWT bearer tokens. Development endpoints may allow anonymous access.

### Rate Limits

- Standard: 100 requests/minute
- Batch operations: 10 requests/minute
"""
        openapi_schema["info"]["version"] = "1.0.0"
        openapi_schema["info"]["contact"] = {
            "name": "DK Data Platform Team",
            "email": "data-platform@datakinetic.io"
        }

        # Add servers
        openapi_schema["servers"] = [
            {"url": "https://data.behaviorlabs.ai", "description": "Production"},
            {"url": "https://data-staging.behaviorlabs.ai", "description": "Staging"},
            {"url": "http://localhost:8000", "description": "Local Development"},
        ]

        # Ensure output directory exists
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Write the schema
        with open(output_file, "w") as f:
            json.dump(openapi_schema, f, indent=2, default=str)

        print(f"OpenAPI specification exported to: {output_file}")
        print(f"  - Paths: {len(openapi_schema.get('paths', {}))}")
        print(f"  - Schemas: {len(openapi_schema.get('components', {}).get('schemas', {}))}")

    except ImportError as e:
        print(f"Error importing FastAPI app: {e}")
        print("\nTo export the OpenAPI spec, ensure all dependencies are installed:")
        print("  pip install -r src/dk_data/requirements.txt")
        sys.exit(1)
    except Exception as e:
        print(f"Error exporting OpenAPI: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Export OpenAPI specification from DK Data Platform API"
    )
    parser.add_argument(
        "--output", "-o",
        default="docs/openapi.json",
        help="Output file path (default: docs/openapi.json)"
    )
    args = parser.parse_args()

    export_openapi(args.output)


if __name__ == "__main__":
    main()
