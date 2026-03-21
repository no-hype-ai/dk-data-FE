"""Targeting Data Importer.

Loads targeting data from CSV files into the targeting schema tables.
Supports biome_relationships, sales_coverage, champions, emr_systems, and financial_details.

Feature: 002-tavr-targeting-tool
"""

import hashlib
import logging
from pathlib import Path
from typing import Optional, Any

import pandas as pd

from ..utils.database import get_cursor, get_connection

logger = logging.getLogger(__name__)

# ============================================================================
# T010: CSV Column Mappings
# ============================================================================

# Targeting CSV columns to database table column mappings
BIOME_COLUMNS = {
    'Medicare ID': 'hospital_id',
    'Current Biome Client': 'is_current_client',
    'Active Biome Echo Surveillance': 'echo_surveillance_active',
    'Current Biome Analytics': 'analytics_active',
    'Pilot 1.0 Site': 'workflow_active',  # Note: Pilot 1.0 indicates workflow
    'Contract Type': 'contract_type',
    'Phase 2 Tokens Needed': 'phase_2_tokens_needed',
    'Speed of Contracting': 'contracting_speed',
}

SALES_COLUMNS = {
    'Medicare ID': 'hospital_id',
    'RD': 'regional_director',
    'AVP': 'area_vp',
    'Expressed Interest': 'expressed_interest',
}

CHAMPION_COLUMNS = {
    'Medicare ID': 'hospital_id',
    'Clinical Champion': 'clinical_champion',
    'Admin Champion': 'admin_champion',
}

EMR_COLUMNS = {
    'Medicare ID': 'hospital_id',
    'EMR': 'primary_emr',
}

# Valid values for enum fields
VALID_PILOT_PHASES = {'Pilot 1.0', 'Phase 2', None, ''}
VALID_CONTRACT_TYPES = {'Amendment', 'New', 'TBA', None, ''}
VALID_CONTRACTING_SPEEDS = {'Fast', 'Medium', 'Slow', None, ''}
VALID_ENGAGEMENT_LEVELS = {'None', 'Passive', 'Interested', 'Advocating'}


def calculate_file_hash(filepath: str) -> str:
    """Calculate MD5 hash of a file for deduplication."""
    hash_md5 = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def parse_boolean(value: Any) -> bool:
    """Parse various boolean representations to Python bool."""
    if pd.isna(value) or value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().upper() in ('Y', 'YES', 'TRUE', '1', 'X')
    return bool(value)


def parse_integer(value: Any) -> Optional[int]:
    """Parse integer with None handling."""
    if pd.isna(value) or value is None or value == '':
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def clean_string(value: Any) -> Optional[str]:
    """Clean string values, returning None for empty/NA values."""
    if pd.isna(value) or value is None:
        return None
    value = str(value).strip()
    return value if value and value.lower() not in ('nan', 'none', '#ref!', '') else None


# ============================================================================
# T011: Hospital ID Matching
# ============================================================================

def validate_hospital_id(hospital_id: str) -> bool:
    """
    Validate that hospital_id exists in mart.dim_hospital.

    Args:
        hospital_id: Medicare provider ID to validate.

    Returns:
        True if hospital exists, False otherwise.
    """
    if not hospital_id:
        return False

    with get_cursor() as cur:
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM mart.dim_hospital
                WHERE hospital_id = %s
            )
        """, (hospital_id,))
        return cur.fetchone()[0]


def get_matching_hospital_ids(hospital_ids: list[str]) -> set[str]:
    """
    Get set of hospital_ids that exist in mart.dim_hospital.

    Args:
        hospital_ids: List of Medicare provider IDs to check.

    Returns:
        Set of valid hospital IDs.
    """
    if not hospital_ids:
        return set()

    with get_cursor() as cur:
        cur.execute("""
            SELECT hospital_id FROM mart.dim_hospital
            WHERE hospital_id = ANY(%s)
        """, (hospital_ids,))
        return {row[0] for row in cur.fetchall()}


# ============================================================================
# T012: Validation and Error Handling
# ============================================================================

class ImportValidationError(Exception):
    """Raised when import validation fails."""
    pass


class ImportResult:
    """Container for import operation results."""

    def __init__(self):
        self.records_processed = 0
        self.records_inserted = 0
        self.records_updated = 0
        self.records_skipped = 0
        self.records_failed = 0
        self.errors: list[dict] = []
        self.warnings: list[dict] = []

    def add_error(self, row_id: Any, field: str, message: str):
        """Add an error to the result."""
        self.errors.append({
            'row_id': row_id,
            'field': field,
            'message': message
        })
        self.records_failed += 1

    def add_warning(self, row_id: Any, field: str, message: str):
        """Add a warning to the result."""
        self.warnings.append({
            'row_id': row_id,
            'field': field,
            'message': message
        })

    def to_dict(self) -> dict:
        """Convert result to dictionary."""
        return {
            'records_processed': self.records_processed,
            'records_inserted': self.records_inserted,
            'records_updated': self.records_updated,
            'records_skipped': self.records_skipped,
            'records_failed': self.records_failed,
            'errors': self.errors[:20],
            'warnings': self.warnings[:20],
            'error_count': len(self.errors),
            'warning_count': len(self.warnings),
        }


def validate_pilot_phase(value: Any) -> Optional[str]:
    """Validate and normalize pilot_phase value."""
    value = clean_string(value)
    if value is None or value == '':
        return None
    # Check if it's a 'Y' for Pilot 1.0
    if value.upper() == 'Y':
        return 'Pilot 1.0'
    if value in VALID_PILOT_PHASES:
        return value
    return None


def validate_contract_type(value: Any) -> Optional[str]:
    """Validate and normalize contract_type value."""
    value = clean_string(value)
    if value is None or value == '':
        return None
    if value in VALID_CONTRACT_TYPES:
        return value
    return None


def validate_contracting_speed(value: Any) -> Optional[str]:
    """Validate and normalize contracting_speed value."""
    value = clean_string(value)
    if value is None or value == '':
        return None
    if value in VALID_CONTRACTING_SPEEDS:
        return value
    return None


def validate_engagement_level(value: Any) -> str:
    """Validate and normalize engagement_level value."""
    value = clean_string(value)
    if value is None or value == '' or value not in VALID_ENGAGEMENT_LEVELS:
        return 'None'
    return value


# ============================================================================
# T015-T018: Biome Relationships Import
# ============================================================================

def import_biome_relationships(
    df: pd.DataFrame,
    result: ImportResult,
    dry_run: bool = False,
    updated_by: str = 'targeting_import'
) -> None:
    """
    Import biome_relationships data from DataFrame.

    Args:
        df: DataFrame with targeting data.
        result: ImportResult to track results.
        dry_run: If True, validate but don't insert.
        updated_by: User identifier for audit trail.
    """
    logger.info("Importing biome_relationships data")

    records = []
    for idx, row in df.iterrows():
        hospital_id = clean_string(row.get('Medicare ID'))
        if not hospital_id:
            result.add_warning(idx, 'Medicare ID', 'Missing hospital ID')
            continue

        # Parse Pilot 1.0 Site column - if 'Y', it's a pilot site
        pilot_site_raw = clean_string(row.get('Pilot 1.0 Site'))
        is_pilot = parse_boolean(pilot_site_raw)

        record = {
            'hospital_id': hospital_id,
            'is_current_client': parse_boolean(row.get('Current Biome Client')),
            'echo_surveillance_active': parse_boolean(row.get('Active Biome Echo Surveillance')),
            'workflow_active': is_pilot,  # Pilot 1.0 indicates workflow engagement
            'analytics_active': parse_boolean(row.get('Current Biome Analytics')),
            'pilot_phase': 'Pilot 1.0' if is_pilot else None,
            'contract_type': validate_contract_type(row.get('Contract Type')),
            'phase_2_tokens_needed': parse_integer(row.get('Phase 2 Tokens Needed')),
            'contracting_speed': validate_contracting_speed(row.get('Speed of Contracting')),
            '_updated_by': updated_by,
        }
        records.append(record)

    if dry_run:
        logger.info(f"DRY RUN: Would insert/update {len(records)} biome_relationships records")
        result.records_processed += len(records)
        return

    # Upsert records
    with get_connection() as conn:
        with conn.cursor() as cur:
            for record in records:
                try:
                    cur.execute("""
                        INSERT INTO targeting.biome_relationships (
                            hospital_id, is_current_client, echo_surveillance_active,
                            workflow_active, analytics_active, pilot_phase,
                            contract_type, phase_2_tokens_needed, contracting_speed,
                            _updated_by, _updated_at
                        ) VALUES (
                            %(hospital_id)s, %(is_current_client)s, %(echo_surveillance_active)s,
                            %(workflow_active)s, %(analytics_active)s, %(pilot_phase)s,
                            %(contract_type)s, %(phase_2_tokens_needed)s, %(contracting_speed)s,
                            %(_updated_by)s, NOW()
                        )
                        ON CONFLICT (hospital_id) DO UPDATE SET
                            is_current_client = EXCLUDED.is_current_client,
                            echo_surveillance_active = EXCLUDED.echo_surveillance_active,
                            workflow_active = EXCLUDED.workflow_active,
                            analytics_active = EXCLUDED.analytics_active,
                            pilot_phase = EXCLUDED.pilot_phase,
                            contract_type = EXCLUDED.contract_type,
                            phase_2_tokens_needed = EXCLUDED.phase_2_tokens_needed,
                            contracting_speed = EXCLUDED.contracting_speed,
                            _updated_by = EXCLUDED._updated_by,
                            _updated_at = NOW()
                    """, record)
                    result.records_inserted += 1
                except Exception as e:
                    result.add_error(record['hospital_id'], 'biome_relationships', str(e))
                    logger.error(f"Error inserting biome record for {record['hospital_id']}: {e}")

            conn.commit()

    result.records_processed += len(records)
    logger.info(f"Imported {result.records_inserted} biome_relationships records")


# ============================================================================
# T026-T029: Sales Coverage Import
# ============================================================================

def import_sales_coverage(
    df: pd.DataFrame,
    result: ImportResult,
    dry_run: bool = False
) -> None:
    """
    Import sales_coverage data from DataFrame.

    Args:
        df: DataFrame with targeting data.
        result: ImportResult to track results.
        dry_run: If True, validate but don't insert.
    """
    logger.info("Importing sales_coverage data")

    records = []
    for idx, row in df.iterrows():
        hospital_id = clean_string(row.get('Medicare ID'))
        if not hospital_id:
            continue

        record = {
            'hospital_id': hospital_id,
            'regional_director': clean_string(row.get('RD')),
            'area_vp': clean_string(row.get('AVP')),
            'expressed_interest': parse_boolean(row.get('Expressed Interest')),
        }
        records.append(record)

    if dry_run:
        logger.info(f"DRY RUN: Would insert/update {len(records)} sales_coverage records")
        return

    with get_connection() as conn:
        with conn.cursor() as cur:
            for record in records:
                try:
                    cur.execute("""
                        INSERT INTO targeting.sales_coverage (
                            hospital_id, regional_director, area_vp,
                            expressed_interest, _updated_at
                        ) VALUES (
                            %(hospital_id)s, %(regional_director)s, %(area_vp)s,
                            %(expressed_interest)s, NOW()
                        )
                        ON CONFLICT (hospital_id) DO UPDATE SET
                            regional_director = EXCLUDED.regional_director,
                            area_vp = EXCLUDED.area_vp,
                            expressed_interest = EXCLUDED.expressed_interest,
                            _updated_at = NOW()
                    """, record)
                except Exception as e:
                    result.add_error(record['hospital_id'], 'sales_coverage', str(e))

            conn.commit()

    logger.info(f"Imported {len(records)} sales_coverage records")


# ============================================================================
# T030-T033: Champions Import
# ============================================================================

def import_champions(
    df: pd.DataFrame,
    result: ImportResult,
    dry_run: bool = False
) -> None:
    """
    Import champions data from DataFrame.

    Args:
        df: DataFrame with targeting data.
        result: ImportResult to track results.
        dry_run: If True, validate but don't insert.
    """
    logger.info("Importing champions data")

    records = []
    for idx, row in df.iterrows():
        hospital_id = clean_string(row.get('Medicare ID'))
        if not hospital_id:
            continue

        # Clinical Champion
        clinical_champion = clean_string(row.get('Clinical Champion'))
        if clinical_champion:
            records.append({
                'hospital_id': hospital_id,
                'champion_type': 'Clinical',
                'champion_name': clinical_champion,
                'engagement_level': 'None',  # Default, can be updated later
            })

        # Administrative Champion
        admin_champion = clean_string(row.get('Admin Champion'))
        if admin_champion:
            records.append({
                'hospital_id': hospital_id,
                'champion_type': 'Administrative',
                'champion_name': admin_champion,
                'engagement_level': 'None',
            })

    if dry_run:
        logger.info(f"DRY RUN: Would insert/update {len(records)} champion records")
        return

    with get_connection() as conn:
        with conn.cursor() as cur:
            for record in records:
                try:
                    # Use INSERT with ON CONFLICT for the unique constraint
                    cur.execute("""
                        INSERT INTO targeting.champions (
                            hospital_id, champion_type, champion_name,
                            engagement_level, _created_at, _updated_at
                        ) VALUES (
                            %(hospital_id)s, %(champion_type)s, %(champion_name)s,
                            %(engagement_level)s, NOW(), NOW()
                        )
                        ON CONFLICT (hospital_id, champion_type, champion_name)
                        WHERE champion_name IS NOT NULL
                        DO UPDATE SET
                            _updated_at = NOW()
                    """, record)
                except Exception as e:
                    result.add_error(
                        record['hospital_id'],
                        'champions',
                        f"{record['champion_type']}: {str(e)}"
                    )

            conn.commit()

    logger.info(f"Imported {len(records)} champion records")


# ============================================================================
# T034-T035: EMR Systems Import
# ============================================================================

def import_emr_systems(
    df: pd.DataFrame,
    result: ImportResult,
    dry_run: bool = False
) -> None:
    """
    Import emr_systems data from DataFrame.

    Args:
        df: DataFrame with targeting data.
        result: ImportResult to track results.
        dry_run: If True, validate but don't insert.
    """
    logger.info("Importing emr_systems data")

    records = []
    for idx, row in df.iterrows():
        hospital_id = clean_string(row.get('Medicare ID'))
        if not hospital_id:
            continue

        primary_emr = clean_string(row.get('EMR'))
        if not primary_emr:
            continue

        record = {
            'hospital_id': hospital_id,
            'primary_emr': primary_emr,
        }
        records.append(record)

    if dry_run:
        logger.info(f"DRY RUN: Would insert/update {len(records)} emr_systems records")
        return

    with get_connection() as conn:
        with conn.cursor() as cur:
            for record in records:
                try:
                    cur.execute("""
                        INSERT INTO targeting.emr_systems (
                            hospital_id, primary_emr, _updated_at
                        ) VALUES (
                            %(hospital_id)s, %(primary_emr)s, NOW()
                        )
                        ON CONFLICT (hospital_id) DO UPDATE SET
                            primary_emr = EXCLUDED.primary_emr,
                            _updated_at = NOW()
                    """, record)
                except Exception as e:
                    result.add_error(record['hospital_id'], 'emr_systems', str(e))

            conn.commit()

    logger.info(f"Imported {len(records)} emr_systems records")


# ============================================================================
# Main Import Function
# ============================================================================

def load_targeting_csv(
    filepath: str,
    dry_run: bool = False,
    skip_validation: bool = False,
    updated_by: str = 'targeting_import'
) -> dict:
    """
    Load targeting data from CSV file into targeting schema tables.

    Args:
        filepath: Path to the targeting CSV file.
        dry_run: If True, validate but don't insert.
        skip_validation: If True, skip hospital_id validation.
        updated_by: User identifier for audit trail.

    Returns:
        Dictionary with import statistics.
    """
    logger.info(f"Loading targeting data from {filepath}")

    source_file = Path(filepath).name
    source_hash = calculate_file_hash(filepath)

    # Read CSV file - skip first row (header grouping row)
    df = pd.read_csv(filepath, header=1, dtype={'Medicare ID': str})
    logger.info(f"Read {len(df)} rows from {source_file}")

    # Filter out rows without Medicare ID
    df = df[df['Medicare ID'].notna() & (df['Medicare ID'] != '')]
    logger.info(f"Found {len(df)} rows with valid Medicare ID")

    result = ImportResult()

    # Validate hospital IDs exist in mart.dim_hospital
    if not skip_validation:
        hospital_ids = df['Medicare ID'].tolist()
        valid_ids = get_matching_hospital_ids(hospital_ids)
        invalid_ids = set(hospital_ids) - valid_ids
        if invalid_ids:
            logger.warning(f"Found {len(invalid_ids)} hospital IDs not in mart.dim_hospital")
            for invalid_id in list(invalid_ids)[:10]:
                result.add_warning(invalid_id, 'Medicare ID', 'Hospital ID not found in mart.dim_hospital')

    # Import each table
    import_biome_relationships(df, result, dry_run, updated_by)
    import_sales_coverage(df, result, dry_run)
    import_champions(df, result, dry_run)
    import_emr_systems(df, result, dry_run)

    # Update data catalog
    if not dry_run:
        update_targeting_data_catalog(source_file, source_hash, result)

    return {
        'status': 'success' if result.records_failed == 0 else 'partial',
        'source_file': source_file,
        'source_hash': source_hash,
        'dry_run': dry_run,
        **result.to_dict()
    }


def update_targeting_data_catalog(source_file: str, source_hash: str, result: ImportResult) -> None:
    """Update meta.ops_data_sources with targeting import results."""
    try:
        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO meta.ops_data_sources (
                    source_name, source_type, source_url,
                    last_successful_refresh, last_refresh_status, record_count
                ) VALUES (
                    'targeting_csv', 'manual', %s,
                    NOW(), 'success', %s
                )
                ON CONFLICT (source_name) DO UPDATE SET
                    last_successful_refresh = NOW(),
                    last_refresh_status = 'success',
                    record_count = EXCLUDED.record_count
            """, (source_file, result.records_processed))
    except Exception as e:
        logger.warning(f"Could not update data catalog: {e}")


# ============================================================================
# CLI Entry Point
# ============================================================================

def main():
    """CLI entry point for targeting data import."""
    import argparse

    parser = argparse.ArgumentParser(description='Load targeting data from CSV')
    parser.add_argument('filepath', help='Path to targeting CSV file')
    parser.add_argument('--dry-run', action='store_true', help='Validate without inserting')
    parser.add_argument('--skip-validation', action='store_true', help='Skip hospital ID validation')
    parser.add_argument('--updated-by', default='targeting_import', help='User identifier for audit')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    result = load_targeting_csv(
        filepath=args.filepath,
        dry_run=args.dry_run,
        skip_validation=args.skip_validation,
        updated_by=args.updated_by
    )

    import json
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
