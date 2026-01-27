# Database Migrations - dk-data-FE

This folder contains SQL migrations for the DK Data FE platform.

**Database**: edwards_tavr (different from trials-predictor's pharma_predictor)

## Medallion Architecture Schema

Tables are organized into PostgreSQL schemas:
- `raw.*` - Unprocessed API responses
- `bronze.*` - Source-native typed data
- `silver.*` - Entity-resolved normalized data
- `gold.*` - Pre-aggregated analytics
- `application.*` - User-specific data

**Note**: Some migrations also use `mol_*` prefixed schemas (e.g., `mol_silver`, `mol_bronze`) for molecule-specific tables. This is a legacy naming convention - new migrations should use the standard schema names.

## Migration Order

Run migrations in numerical order. Key migrations:

### Core Tables
- `001_catalog_health_jobs.sql` - Initial catalog and health job tables
- `020_mol_schemas.sql` - Molecule-related schemas and tables
- `021_mol_api_views.sql` - API views for molecule data
- `022_mol_seed_data.sql` - Seed data for testing
- `023_mol_dynamic_sources.sql` - Dynamic data source configuration

### Medallion Architecture
- `028_raw_layer_tables.sql` - Creates raw.* tables
- `029_bronze_layer_tables.sql` - Creates bronze.* tables (CANONICAL)
- `030_silver_layer_tables.sql` - Creates silver.* tables (CANONICAL)

### Gold & Application
- `032_gold_tables.sql` - Gold layer tables
- `033_onboarding_tables.sql` - Data source onboarding
- `034_enable_extensions.sql` - PostgreSQL extensions
- `035_application_schema.sql` - Application layer tables
- `036_sync_scheduler_tables.sql` - Scheduler tables

### Complete Setup
- `050_complete_medallion_sources.sql` - Complete medallion source configuration

## Deprecated Migrations (Do Not Use)

The following migrations use an older naming convention and are superseded:

- `030_bronze_tables.sql` - Use `029_bronze_layer_tables.sql` instead
- `031_silver_tables.sql` - Use `030_silver_layer_tables.sql` instead

## Naming Convention

**Canonical**: Schema-prefixed tables
- `silver.molecules` (NOT `silver_molecules`)
- `gold.molecule_profile` (NOT `gold_molecule_profile`)

**Primary Key**: All tables use `id` as the primary key (UUID)

**Foreign Keys**: Reference other tables using their schema-prefixed name
- `FK → silver.molecules(id)`
