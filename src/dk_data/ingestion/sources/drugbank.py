"""DrugBank Data Loader.

Feature: 011-datasource-integration
Task: Phase 6 / US4 — credential-gated source (DrugBank)

Loads validated DrugBank drug records into mol_raw.drugbank with
upsert semantics (ON CONFLICT DO UPDATE on drugbank_id).

Target table: mol_raw.drugbank (see migration 063_drugbank_raw_table.sql)
"""

import json
import logging
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from ..utils.database import get_connection
from ..utils.validators import DrugBankRecord

logger = logging.getLogger(__name__)

# Batch commit interval
BATCH_SIZE = 500


def load_drugbank_data(
    records: List[Dict[str, Any]],
    source_hash: Optional[str] = None,
    source_file: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> Dict[str, Any]:
    """Load DrugBank records into mol_raw.drugbank.

    Validates each record using Pydantic and performs an upsert:
    INSERT ... ON CONFLICT (drugbank_id) DO UPDATE.

    Args:
        records: List of normalized drug record dicts from DrugBankFetcher.
        source_hash: Hash of the fetch batch for lineage tracking.
        source_file: Source file identifier.
        batch_size: Number of records to commit at once.

    Returns:
        Dictionary with:
            - status: 'success' or 'failed'
            - records_inserted: number of records upserted
            - records_failed: number of records that failed validation
            - errors: list of first 10 error details
    """
    if not records:
        logger.warning("No DrugBank records to load")
        return {
            "status": "success",
            "records_fetched": 0,
            "records_inserted": 0,
            "records_updated": 0,
            "errors": [],
        }

    logger.info("Loading %d DrugBank records into mol_raw.drugbank", len(records))

    records_inserted = 0
    records_failed = 0
    errors: List[Dict[str, Any]] = []

    with get_connection() as conn:
        with conn.cursor() as cur:
            for idx, raw_record in enumerate(records):
                try:
                    # Validate with Pydantic
                    record = DrugBankRecord(**raw_record)

                    # Serialize JSONB fields
                    def _to_json(v: Any) -> Optional[str]:
                        return json.dumps(v) if v is not None else None

                    cur.execute(
                        """
                        INSERT INTO mol_raw.drugbank (
                            drugbank_id, name, description, cas_number,
                            drug_type, state, groups,
                            categories, targets, enzymes, carriers, transporters,
                            indication, pharmacodynamics, mechanism_of_action,
                            absorption, protein_binding, metabolism, half_life,
                            route_of_elimination, clearance, volume_of_distribution,
                            toxicity, atc_codes, pathways, drug_interactions,
                            food_interactions,
                            synonyms, external_identifiers,
                            patents, international_brands,
                            monoisotopic_mass, unii,
                            smiles, inchi, inchi_key, molecular_formula, molecular_weight,
                            calculated_properties, experimental_properties,
                            classification,
                            _source_file, _source_hash
                        ) VALUES (
                            %s, %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s, %s,
                            %s,
                            %s, %s,
                            %s, %s,
                            %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s,
                            %s,
                            %s, %s
                        )
                        ON CONFLICT (drugbank_id) DO UPDATE SET
                            name = EXCLUDED.name,
                            description = EXCLUDED.description,
                            cas_number = EXCLUDED.cas_number,
                            drug_type = EXCLUDED.drug_type,
                            state = EXCLUDED.state,
                            groups = EXCLUDED.groups,
                            categories = EXCLUDED.categories,
                            targets = EXCLUDED.targets,
                            enzymes = EXCLUDED.enzymes,
                            carriers = EXCLUDED.carriers,
                            transporters = EXCLUDED.transporters,
                            indication = EXCLUDED.indication,
                            pharmacodynamics = EXCLUDED.pharmacodynamics,
                            mechanism_of_action = EXCLUDED.mechanism_of_action,
                            absorption = EXCLUDED.absorption,
                            protein_binding = EXCLUDED.protein_binding,
                            metabolism = EXCLUDED.metabolism,
                            half_life = EXCLUDED.half_life,
                            route_of_elimination = EXCLUDED.route_of_elimination,
                            clearance = EXCLUDED.clearance,
                            volume_of_distribution = EXCLUDED.volume_of_distribution,
                            toxicity = EXCLUDED.toxicity,
                            atc_codes = EXCLUDED.atc_codes,
                            pathways = EXCLUDED.pathways,
                            drug_interactions = EXCLUDED.drug_interactions,
                            food_interactions = EXCLUDED.food_interactions,
                            synonyms = EXCLUDED.synonyms,
                            external_identifiers = EXCLUDED.external_identifiers,
                            patents = EXCLUDED.patents,
                            international_brands = EXCLUDED.international_brands,
                            monoisotopic_mass = EXCLUDED.monoisotopic_mass,
                            unii = EXCLUDED.unii,
                            smiles = EXCLUDED.smiles,
                            inchi = EXCLUDED.inchi,
                            inchi_key = EXCLUDED.inchi_key,
                            molecular_formula = EXCLUDED.molecular_formula,
                            molecular_weight = EXCLUDED.molecular_weight,
                            calculated_properties = EXCLUDED.calculated_properties,
                            experimental_properties = EXCLUDED.experimental_properties,
                            classification = EXCLUDED.classification,
                            _source_file = EXCLUDED._source_file,
                            _source_hash = EXCLUDED._source_hash,
                            _loaded_at = NOW()
                        """,
                        (
                            record.drugbank_id,
                            record.name,
                            record.description,
                            record.cas_number,
                            getattr(record, "drug_type", None),
                            getattr(record, "state", None),
                            _to_json(getattr(record, "groups", None)),
                            record.categories if record.categories else None,
                            _to_json(getattr(record, "targets", None)),
                            _to_json(getattr(record, "enzymes", None)),
                            _to_json(getattr(record, "carriers", None)),
                            _to_json(getattr(record, "transporters", None)),
                            record.indication,
                            record.pharmacodynamics,
                            getattr(record, "mechanism_of_action", None),
                            getattr(record, "absorption", None),
                            getattr(record, "protein_binding", None),
                            getattr(record, "metabolism", None),
                            getattr(record, "half_life", None),
                            getattr(record, "route_of_elimination", None),
                            getattr(record, "clearance", None),
                            getattr(record, "volume_of_distribution", None),
                            getattr(record, "toxicity", None),
                            _to_json(getattr(record, "atc_codes", None)),
                            _to_json(getattr(record, "pathways", None)),
                            _to_json(getattr(record, "drug_interactions", None)),
                            _to_json(getattr(record, "food_interactions", None)),
                            _to_json(getattr(record, "synonyms", None)),
                            _to_json(getattr(record, "external_identifiers", None)),
                            _to_json(getattr(record, "patents", None)),
                            _to_json(getattr(record, "international_brands", None)),
                            getattr(record, "monoisotopic_mass", None),
                            getattr(record, "unii", None),
                            getattr(record, "smiles", None),
                            getattr(record, "inchi", None),
                            getattr(record, "inchi_key", None),
                            getattr(record, "molecular_formula", None),
                            str(getattr(record, "molecular_weight", None)) if getattr(record, "molecular_weight", None) is not None else None,
                            _to_json(getattr(record, "calculated_properties", None)),
                            _to_json(getattr(record, "experimental_properties", None)),
                            _to_json(getattr(record, "classification", None)),
                            source_file or "drugbank_xml",
                            source_hash,
                        ),
                    )
                    records_inserted += 1

                    if records_inserted % batch_size == 0:
                        conn.commit()
                        logger.debug("Committed batch: %d records so far", records_inserted)

                except ValidationError as e:
                    records_failed += 1
                    errors.append({
                        "index": idx,
                        "drugbank_id": raw_record.get("drugbank_id"),
                        "error": str(e),
                        "type": "validation",
                    })
                    if records_failed <= 5:
                        logger.warning(
                            "Validation error at index %d: %s", idx, e
                        )

                except Exception as e:
                    conn.rollback()
                    records_failed += 1
                    errors.append({
                        "index": idx,
                        "drugbank_id": raw_record.get("drugbank_id"),
                        "error": str(e),
                        "type": "database",
                    })
                    logger.error("Database error at index %d: %s", idx, e)

            # Final commit
            conn.commit()

    logger.info(
        "DrugBank load complete: %d upserted, %d failed",
        records_inserted,
        records_failed,
    )

    return {
        "status": "success" if records_inserted > 0 or records_failed == 0 else "failed",
        "records_fetched": len(records),
        "records_inserted": records_inserted,
        "records_updated": 0,
        "errors": errors[:10],
    }
