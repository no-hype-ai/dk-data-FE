"""
Clinical Endpoints Ontology Loader.

Centralized loader for clinical endpoints ontology that provides:
- Disease-specific endpoint definitions and validation rules
- ICD-10 codes for all supported indications
- FDA-recommended endpoints and MCID values
- Drug-specific expected efficacy ranges
- Cross-indication global endpoints

This module follows the same pattern as OntologyLoader but is specifically
designed for clinical trial endpoints rather than general indication mappings.

Usage:
    from services.ground_truth.clinical_endpoints_loader import (
        get_clinical_endpoints_ontology,
        ClinicalEndpointsOntology,
    )

    ontology = get_clinical_endpoints_ontology()

    # Get endpoints for an indication
    endpoints = ontology.get_indication_endpoints("atopic_dermatitis")

    # Check if an endpoint is valid for an indication
    is_valid = ontology.is_valid_endpoint("EASI", "atopic_dermatitis")

    # Get expected value range
    range_info = ontology.get_endpoint_value_range("EASI", "atopic_dermatitis")

    # Get ICD-10 codes
    icd_codes = ontology.get_icd10_codes("atopic_dermatitis")
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml
from loguru import logger


@dataclass
class EndpointInfo:
    """Information about a clinical endpoint."""
    name: str
    full_name: str
    description: str = ""
    score_range: Optional[Tuple[float, float]] = None
    higher_is_worse: bool = True
    unit: str = "points"
    clinically_meaningful_change: Optional[float] = None
    fda_recommended: bool = False
    aliases: List[str] = field(default_factory=list)
    response_thresholds: Dict[str, str] = field(default_factory=dict)
    typical_efficacy_ranges: Dict[str, Tuple[float, float]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "full_name": self.full_name,
            "description": self.description,
            "score_range": list(self.score_range) if self.score_range else None,
            "higher_is_worse": self.higher_is_worse,
            "unit": self.unit,
            "clinically_meaningful_change": self.clinically_meaningful_change,
            "fda_recommended": self.fda_recommended,
            "aliases": self.aliases,
            "response_thresholds": self.response_thresholds,
        }


@dataclass
class ICD10CodeInfo:
    """Information about an ICD-10 code."""
    code: str
    description: str
    is_primary: bool = False
    effective_date: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "description": self.description,
            "is_primary": self.is_primary,
        }


class ClinicalEndpointsOntology:
    """
    Loads and provides access to clinical endpoints ontology.

    This class provides a comprehensive interface for accessing:
    - Indication-specific clinical endpoints
    - ICD-10 code mappings
    - Validation rules for clinical values
    - Drug-specific expected ranges
    - Clinically meaningful differences (MCID)
    """

    DEFAULT_CONFIG_PATH = "config/clinical_endpoints_ontology.yaml"

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the ontology loader.

        Args:
            config_path: Path to YAML config file. If None, uses default location.
        """
        if config_path:
            self._config_path = Path(config_path)
        else:
            self._config_path = self._find_config_path()

        self._ontology: Dict[str, Any] = {}
        self._loaded = False

        # Caches for efficient lookups
        self._indication_alias_map: Dict[str, str] = {}  # alias -> canonical name
        self._endpoint_name_map: Dict[str, str] = {}  # uppercase name -> original name

    def _find_config_path(self) -> Path:
        """Find the config file path."""
        # Try relative to this file
        current_dir = Path(__file__).parent

        # Go up to backend root (ground_truth -> services -> src -> backend)
        backend_root = current_dir.parent.parent.parent
        config_path = backend_root / "config" / "clinical_endpoints_ontology.yaml"

        if config_path.exists():
            return config_path

        # Try from current working directory
        cwd_path = Path.cwd() / "config" / "clinical_endpoints_ontology.yaml"
        if cwd_path.exists():
            return cwd_path

        # Try environment variable
        env_path = os.environ.get("CLINICAL_ENDPOINTS_CONFIG_PATH")
        if env_path and Path(env_path).exists():
            return Path(env_path)

        # Default to backend config
        return config_path

    def load(self, force_reload: bool = False) -> "ClinicalEndpointsOntology":
        """
        Load ontology from YAML file.

        Args:
            force_reload: If True, reload even if already loaded.

        Returns:
            Self for method chaining.
        """
        if self._loaded and not force_reload:
            return self

        logger.info(f"Loading clinical endpoints ontology from {self._config_path}")

        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                self._ontology = yaml.safe_load(f)
        except FileNotFoundError:
            logger.warning(f"Ontology config not found at {self._config_path}, using defaults")
            self._ontology = self._get_default_ontology()
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse ontology config: {e}")
            self._ontology = self._get_default_ontology()

        # Build lookup caches
        self._build_caches()
        self._loaded = True

        logger.info(
            f"Loaded clinical endpoints ontology v{self._ontology.get('version', 'unknown')}: "
            f"{len(self._ontology.get('indications', {}))} indications, "
            f"{len(self._ontology.get('global_endpoints', {}))} global endpoints"
        )

        return self

    def _get_default_ontology(self) -> Dict[str, Any]:
        """Return minimal default ontology."""
        return {
            "version": "1.0.0-default",
            "indications": {},
            "global_endpoints": {},
            "units": {},
            "validation_rules": {},
            "drug_expected_ranges": {},
        }

    def _build_caches(self) -> None:
        """Build lookup caches for efficient querying."""
        # Build indication alias map
        self._indication_alias_map = {}
        for ind_name, ind_data in self._ontology.get("indications", {}).items():
            # Map canonical name
            self._indication_alias_map[ind_name.lower()] = ind_name
            self._indication_alias_map[ind_name.lower().replace("_", " ")] = ind_name

            # Map aliases
            for alias in ind_data.get("aliases", []):
                self._indication_alias_map[alias.lower()] = ind_name

        # Build endpoint name map
        self._endpoint_name_map = {}
        for ind_name, ind_data in self._ontology.get("indications", {}).items():
            for ep_type in ["primary_endpoints", "secondary_endpoints", "durability_endpoints", "safety_endpoints"]:
                for ep_name, ep_data in ind_data.get(ep_type, {}).items():
                    self._endpoint_name_map[ep_name.upper()] = ep_name
                    # Also map aliases
                    for alias in ep_data.get("aliases", []) if isinstance(ep_data, dict) else []:
                        self._endpoint_name_map[alias.upper().replace("-", "_")] = ep_name

        # Add global endpoints
        for ep_name in self._ontology.get("global_endpoints", {}).keys():
            self._endpoint_name_map[ep_name.upper()] = ep_name

    def _ensure_loaded(self) -> None:
        """Ensure ontology is loaded."""
        if not self._loaded:
            self.load()

    @property
    def version(self) -> str:
        """Get ontology version."""
        self._ensure_loaded()
        return self._ontology.get("version", "unknown")

    @property
    def indications(self) -> List[str]:
        """Get list of all supported indications."""
        self._ensure_loaded()
        return list(self._ontology.get("indications", {}).keys())

    # =========================================================================
    # INDICATION LOOKUPS
    # =========================================================================

    def resolve_indication(self, indication: str) -> Optional[str]:
        """
        Resolve an indication name or alias to canonical form.

        Args:
            indication: Indication name, alias, or abbreviation

        Returns:
            Canonical indication name or None if not found
        """
        self._ensure_loaded()

        # Normalize input
        ind_lower = indication.lower().strip()
        ind_normalized = ind_lower.replace(" ", "_").replace("-", "_")

        # Try direct lookup
        if ind_normalized in self._indication_alias_map:
            return self._indication_alias_map[ind_normalized]

        # Try with spaces
        if ind_lower in self._indication_alias_map:
            return self._indication_alias_map[ind_lower]

        # Partial match
        for alias, canonical in self._indication_alias_map.items():
            if ind_lower in alias or alias in ind_lower:
                return canonical

        return None

    def get_indication_data(self, indication: str) -> Dict[str, Any]:
        """
        Get all data for an indication.

        Args:
            indication: Indication name or alias

        Returns:
            Full indication data dictionary
        """
        self._ensure_loaded()

        canonical = self.resolve_indication(indication)
        if canonical:
            return self._ontology.get("indications", {}).get(canonical, {})

        return {}

    def get_indication_endpoints(self, indication: str) -> Dict[str, Any]:
        """
        Get all endpoints for an indication.

        Args:
            indication: Indication name or alias

        Returns:
            Dictionary of primary and secondary endpoints
        """
        ind_data = self.get_indication_data(indication)
        if not ind_data:
            return {}

        return {
            "primary": ind_data.get("primary_endpoints", {}),
            "secondary": ind_data.get("secondary_endpoints", {}),
            "durability": ind_data.get("durability_endpoints", {}),
            "safety": ind_data.get("safety_endpoints", {}),
        }

    # =========================================================================
    # ENDPOINT LOOKUPS
    # =========================================================================

    def get_endpoint_info(
        self,
        endpoint: str,
        indication: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get information about a specific endpoint.

        Args:
            endpoint: Endpoint name or alias
            indication: Optional indication to narrow search

        Returns:
            Endpoint data dictionary or None
        """
        self._ensure_loaded()

        endpoint_upper = endpoint.upper().replace("-", "_").replace(" ", "_")

        # If indication specified, search there first
        if indication:
            ind_data = self.get_indication_data(indication)
            if ind_data:
                for ep_type in ["primary_endpoints", "secondary_endpoints", "durability_endpoints"]:
                    for ep_name, ep_data in ind_data.get(ep_type, {}).items():
                        if ep_name.upper() == endpoint_upper:
                            return ep_data
                        if isinstance(ep_data, dict):
                            aliases = [a.upper() for a in ep_data.get("aliases", [])]
                            if endpoint_upper in aliases:
                                return ep_data

        # Search all indications
        for ind_name, ind_data in self._ontology.get("indications", {}).items():
            for ep_type in ["primary_endpoints", "secondary_endpoints"]:
                for ep_name, ep_data in ind_data.get(ep_type, {}).items():
                    if ep_name.upper() == endpoint_upper:
                        return ep_data

        # Check global endpoints
        for ep_name, ep_data in self._ontology.get("global_endpoints", {}).items():
            if ep_name.upper() == endpoint_upper:
                return ep_data

        return None

    def get_valid_endpoints_for_indication(self, indication: str) -> Set[str]:
        """
        Get all valid endpoint names for an indication.

        Args:
            indication: Indication name or alias

        Returns:
            Set of valid endpoint names (uppercase)
        """
        self._ensure_loaded()

        endpoints = set()
        ind_data = self.get_indication_data(indication)

        if ind_data:
            for ep_type in ["primary_endpoints", "secondary_endpoints", "durability_endpoints"]:
                for ep_name, ep_data in ind_data.get(ep_type, {}).items():
                    endpoints.add(ep_name.upper())
                    # Add aliases
                    if isinstance(ep_data, dict):
                        for alias in ep_data.get("aliases", []):
                            endpoints.add(alias.upper())

        # Add global endpoints
        for ep_name in self._ontology.get("global_endpoints", {}).keys():
            endpoints.add(ep_name.upper())

        return endpoints

    def is_valid_endpoint(self, endpoint: str, indication: str) -> bool:
        """
        Check if an endpoint is valid for an indication.

        Args:
            endpoint: Endpoint name
            indication: Indication name

        Returns:
            True if valid endpoint for indication
        """
        valid_endpoints = self.get_valid_endpoints_for_indication(indication)
        endpoint_upper = endpoint.upper().replace("-", "_").replace(" ", "_")
        return endpoint_upper in valid_endpoints

    def get_endpoint_score_range(
        self,
        endpoint: str,
        indication: Optional[str] = None
    ) -> Optional[Tuple[float, float]]:
        """
        Get the valid score range for an endpoint.

        Args:
            endpoint: Endpoint name
            indication: Optional indication

        Returns:
            Tuple of (min, max) or None
        """
        ep_info = self.get_endpoint_info(endpoint, indication)
        if ep_info and "score_range" in ep_info:
            return tuple(ep_info["score_range"])
        return None

    def get_mcid(
        self,
        endpoint: str,
        indication: Optional[str] = None
    ) -> Optional[float]:
        """
        Get the minimum clinically important difference for an endpoint.

        Args:
            endpoint: Endpoint name
            indication: Optional indication

        Returns:
            MCID value or None
        """
        ep_info = self.get_endpoint_info(endpoint, indication)
        if ep_info:
            return ep_info.get("clinically_meaningful_change")

        # Check MCID section
        mcid_data = self._ontology.get("clinically_meaningful_differences", {})
        for category, endpoints in mcid_data.items():
            endpoint_upper = endpoint.upper()
            for ep_name, ep_mcid in endpoints.items():
                if ep_name.upper() == endpoint_upper:
                    if isinstance(ep_mcid, dict):
                        return ep_mcid.get("MCID") or ep_mcid.get("mcid")
                    return ep_mcid

        return None

    # =========================================================================
    # ICD-10 LOOKUPS
    # =========================================================================

    def get_icd10_codes(self, indication: str) -> List[ICD10CodeInfo]:
        """
        Get ICD-10 codes for an indication.

        Args:
            indication: Indication name or alias

        Returns:
            List of ICD10CodeInfo objects
        """
        self._ensure_loaded()

        ind_data = self.get_indication_data(indication)
        if not ind_data:
            return []

        codes = []
        icd10_data = ind_data.get("icd10", {})

        # Handle new format with nested codes
        if isinstance(icd10_data, dict):
            primary = icd10_data.get("primary", "")

            # Add specific codes
            for code_info in icd10_data.get("specific_codes", []):
                codes.append(ICD10CodeInfo(
                    code=code_info.get("code", ""),
                    description=code_info.get("description", ""),
                    is_primary=code_info.get("code", "").startswith(primary.split(",")[0].strip()) if primary else False,
                ))

            # Add related codes
            for code_info in icd10_data.get("related_codes", []):
                codes.append(ICD10CodeInfo(
                    code=code_info.get("code", ""),
                    description=code_info.get("description", ""),
                    is_primary=False,
                ))

        # Handle old format (list of codes)
        elif isinstance(icd10_data, list):
            for code in icd10_data:
                codes.append(ICD10CodeInfo(code=code, description="", is_primary=len(codes) == 0))

        return codes

    def get_primary_icd10_code(self, indication: str) -> Optional[str]:
        """
        Get the primary ICD-10 code for an indication.

        Args:
            indication: Indication name or alias

        Returns:
            Primary ICD-10 code or None
        """
        ind_data = self.get_indication_data(indication)
        if not ind_data:
            return None

        icd10_data = ind_data.get("icd10", {})

        if isinstance(icd10_data, dict):
            return icd10_data.get("primary", "").split(",")[0].strip()
        elif isinstance(icd10_data, list) and icd10_data:
            return icd10_data[0]

        return None

    # =========================================================================
    # VALIDATION RULES
    # =========================================================================

    def get_validation_rules(self) -> Dict[str, Any]:
        """Get all validation rules."""
        self._ensure_loaded()
        return self._ontology.get("validation_rules", {})

    def get_drug_expected_ranges(
        self,
        drug: str,
        indication: str
    ) -> Dict[str, Any]:
        """
        Get expected efficacy ranges for a drug in an indication.

        Args:
            drug: Drug name
            indication: Indication name

        Returns:
            Dictionary of expected ranges
        """
        self._ensure_loaded()

        drug_lower = drug.lower()
        canonical_ind = self.resolve_indication(indication)

        drug_data = self._ontology.get("drug_expected_ranges", {}).get(drug_lower, {})
        if canonical_ind:
            return drug_data.get("indications", {}).get(canonical_ind, {})

        return {}

    def validate_value_in_range(
        self,
        endpoint: str,
        value: float,
        indication: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate that a value is within expected range for an endpoint.

        Args:
            endpoint: Endpoint name
            value: Value to validate
            indication: Optional indication

        Returns:
            Tuple of (is_valid, message if invalid)
        """
        score_range = self.get_endpoint_score_range(endpoint, indication)
        if score_range:
            min_val, max_val = score_range
            if value < min_val or value > max_val:
                return False, f"Value {value} outside expected range [{min_val}, {max_val}] for {endpoint}"

        return True, None

    # =========================================================================
    # PATTERN GENERATION
    # =========================================================================

    def get_endpoint_patterns(self, indication: str) -> List[Dict[str, Any]]:
        """
        Generate regex patterns for extracting endpoints from text.

        Args:
            indication: Indication name

        Returns:
            List of pattern dictionaries with 'pattern', 'endpoint', 'type'
        """
        self._ensure_loaded()

        patterns = []
        endpoints = self.get_indication_endpoints(indication)

        for ep_type, ep_dict in endpoints.items():
            for ep_name, ep_data in ep_dict.items():
                if not isinstance(ep_data, dict):
                    continue

                # Get all names for this endpoint
                names = [ep_name]
                names.extend(ep_data.get("aliases", []))

                for name in names:
                    # Normalize name for pattern
                    name_pattern = re.escape(name.lower()).replace(r"\_", r"[\s_-]*")

                    # Response rate pattern (e.g., "EASI-75: 65%")
                    patterns.append({
                        "pattern": rf"{name_pattern}[\s:=]*(\d+(?:\.\d+)?)\s*%",
                        "endpoint": ep_name,
                        "type": ep_type.replace("_endpoints", ""),
                        "value_type": "percentage",
                    })

                    # Score pattern (e.g., "EASI score of 15.2")
                    if ep_data.get("score_range"):
                        patterns.append({
                            "pattern": rf"{name_pattern}[\s:]*(score\s+)?(?:of\s+)?(\d+(?:\.\d+)?)",
                            "endpoint": ep_name,
                            "type": ep_type.replace("_endpoints", ""),
                            "value_type": "score",
                        })

        return patterns

    def get_indication_keywords(self, indication: str) -> List[str]:
        """
        Get keywords for identifying an indication in text.

        Args:
            indication: Indication name

        Returns:
            List of keywords (name, aliases, endpoint names)
        """
        self._ensure_loaded()

        keywords = []
        ind_data = self.get_indication_data(indication)

        if ind_data:
            # Add indication name and aliases
            canonical = self.resolve_indication(indication)
            if canonical:
                keywords.append(canonical.replace("_", " "))
            keywords.extend(ind_data.get("aliases", []))

            # Add primary endpoint names
            for ep_name in ind_data.get("primary_endpoints", {}).keys():
                keywords.append(ep_name.lower())

        return keywords

    # =========================================================================
    # REGULATORY REFERENCES
    # =========================================================================

    def get_fda_guidance_reference(self, indication: str) -> Optional[str]:
        """
        Get FDA guidance reference for an indication.

        Args:
            indication: Indication name

        Returns:
            FDA guidance reference string or None
        """
        ind_data = self.get_indication_data(indication)
        return ind_data.get("fda_guidance_reference")

    def get_regulatory_references(self) -> Dict[str, Any]:
        """Get all regulatory references."""
        self._ensure_loaded()
        return self._ontology.get("regulatory_references", {})


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_clinical_endpoints_ontology: Optional[ClinicalEndpointsOntology] = None


def get_clinical_endpoints_ontology(
    config_path: Optional[str] = None,
    force_reload: bool = False
) -> ClinicalEndpointsOntology:
    """
    Get or create the clinical endpoints ontology singleton.

    Args:
        config_path: Optional path to config file
        force_reload: Force reload the ontology

    Returns:
        ClinicalEndpointsOntology instance
    """
    global _clinical_endpoints_ontology

    if _clinical_endpoints_ontology is None or force_reload:
        _clinical_endpoints_ontology = ClinicalEndpointsOntology(config_path)
        _clinical_endpoints_ontology.load()

    return _clinical_endpoints_ontology


def reset_clinical_endpoints_ontology() -> None:
    """Reset the singleton (mainly for testing)."""
    global _clinical_endpoints_ontology
    _clinical_endpoints_ontology = None
