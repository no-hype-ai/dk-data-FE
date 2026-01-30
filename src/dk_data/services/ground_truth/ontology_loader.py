"""
Ontology Mappings Loader.

Loads and provides access to ontology mappings from YAML configuration,
with optional dynamic resolution via WHO ICD API.

This centralizes all indication, ICD-10, abbreviation, and pharmacologic
class mappings for use by the indication ontology and resolver services.

The loader supports two modes:
1. Static mode: Uses only YAML-configured mappings (default)
2. Dynamic mode: Falls back to WHO ICD API for unknown indications

To enable dynamic WHO ICD resolution, set:
- WHO_ICD_CLIENT_ID and WHO_ICD_CLIENT_SECRET environment variables
- Or call enable_dynamic_resolution() after initialization
"""

import asyncio
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from loguru import logger


@dataclass
class OntologyMappings:
    """Container for all ontology mappings."""

    version: str = "1.0.0"
    last_updated: str = ""

    # Abbreviations: abbreviation -> expanded form
    abbreviations: Dict[str, str] = field(default_factory=dict)

    # ICD-10 mappings: indication -> (code, chapter)
    indication_to_icd10: Dict[str, Tuple[str, str]] = field(default_factory=dict)

    # FDA EPC to indications: epc_class -> list of indications
    fda_epc_to_indications: Dict[str, List[str]] = field(default_factory=dict)

    # MOA to indications: moa -> list of indications
    biologic_moa_to_indications: Dict[str, List[str]] = field(default_factory=dict)

    # Reverse lookups (built on load)
    _indication_to_epc: Dict[str, List[str]] = field(default_factory=dict)
    _indication_to_moa: Dict[str, List[str]] = field(default_factory=dict)
    _icd10_chapter_to_indications: Dict[str, List[str]] = field(default_factory=dict)


class OntologyLoader:
    """
    Loads and provides access to ontology mappings.

    Supports both static YAML-based lookups and dynamic WHO ICD API resolution.

    Usage:
        loader = OntologyLoader()
        mappings = loader.load()

        # Get ICD-10 code (static)
        code, chapter = mappings.indication_to_icd10.get("rheumatoid arthritis", (None, None))

        # Expand abbreviation
        expanded = mappings.abbreviations.get("RA", "RA")

        # Get indications for EPC class
        indications = mappings.fda_epc_to_indications.get("Tumor Necrosis Factor Blocker [EPC]", [])

        # Dynamic resolution (async)
        code_info = await loader.resolve_icd10_dynamic("some rare disease")
    """

    DEFAULT_CONFIG_PATH = "config/ontology_mappings.yaml"

    def __init__(
        self,
        config_path: Optional[str] = None,
        enable_who_icd: bool = True,
    ):
        """
        Initialize the loader.

        Args:
            config_path: Path to YAML config file. If None, uses default location.
            enable_who_icd: Whether to enable WHO ICD API for dynamic resolution.
        """
        if config_path:
            self._config_path = Path(config_path)
        else:
            # Find config relative to this file or project root
            self._config_path = self._find_config_path()

        self._mappings: Optional[OntologyMappings] = None
        self._loaded = False

        # WHO ICD API integration
        self._who_icd_enabled = enable_who_icd
        self._who_icd_client = None
        self._who_icd_initialized = False

        # Dynamic resolution cache (in-memory, avoids repeated API calls)
        self._dynamic_cache: Dict[str, Tuple[str, str]] = {}

    def _find_config_path(self) -> Path:
        """Find the config file path."""
        # Try relative to this file
        current_dir = Path(__file__).parent

        # Go up to backend root
        backend_root = current_dir.parent.parent.parent
        config_path = backend_root / "config" / "ontology_mappings.yaml"

        if config_path.exists():
            return config_path

        # Try from current working directory
        cwd_path = Path.cwd() / "config" / "ontology_mappings.yaml"
        if cwd_path.exists():
            return cwd_path

        # Try environment variable
        env_path = os.environ.get("ONTOLOGY_CONFIG_PATH")
        if env_path and Path(env_path).exists():
            return Path(env_path)

        # Default to backend config
        return config_path

    def load(self, force_reload: bool = False) -> OntologyMappings:
        """
        Load ontology mappings from YAML file.

        Args:
            force_reload: If True, reload even if already loaded.

        Returns:
            OntologyMappings instance with all mappings.
        """
        if self._loaded and not force_reload and self._mappings:
            return self._mappings

        logger.info(f"Loading ontology mappings from {self._config_path}")

        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except FileNotFoundError:
            logger.warning(f"Ontology config not found at {self._config_path}, using empty mappings")
            self._mappings = OntologyMappings()
            self._loaded = True
            return self._mappings
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse ontology config: {e}")
            self._mappings = OntologyMappings()
            self._loaded = True
            return self._mappings

        # Parse the YAML data
        self._mappings = self._parse_mappings(data)
        self._build_reverse_lookups()
        self._loaded = True

        logger.info(
            f"Loaded ontology mappings: "
            f"{len(self._mappings.abbreviations)} abbreviations, "
            f"{len(self._mappings.indication_to_icd10)} ICD-10 codes, "
            f"{len(self._mappings.fda_epc_to_indications)} EPC classes, "
            f"{len(self._mappings.biologic_moa_to_indications)} MOA classes"
        )

        return self._mappings

    def _parse_mappings(self, data: Dict[str, Any]) -> OntologyMappings:
        """Parse YAML data into OntologyMappings."""
        mappings = OntologyMappings(
            version=data.get("version", "1.0.0"),
            last_updated=data.get("last_updated", ""),
        )

        # Parse abbreviations (case-insensitive keys for lookup)
        raw_abbrevs = data.get("abbreviations", {})
        for abbrev, expansion in raw_abbrevs.items():
            # Store both original case and lowercase for flexible lookup
            mappings.abbreviations[abbrev] = expansion
            mappings.abbreviations[abbrev.lower()] = expansion

        # Parse ICD-10 mappings
        raw_icd10 = data.get("indication_to_icd10", {})
        for indication, code_data in raw_icd10.items():
            if isinstance(code_data, list) and len(code_data) >= 2:
                mappings.indication_to_icd10[indication.lower()] = (code_data[0], code_data[1])
            elif isinstance(code_data, str):
                # Just code, no chapter
                mappings.indication_to_icd10[indication.lower()] = (code_data, "")

        # Parse FDA EPC mappings
        raw_epc = data.get("fda_epc_to_indications", {})
        for epc_class, indications in raw_epc.items():
            if isinstance(indications, list):
                mappings.fda_epc_to_indications[epc_class] = indications

        # Parse MOA mappings
        raw_moa = data.get("biologic_moa_to_indications", {})
        for moa, indications in raw_moa.items():
            if isinstance(indications, list):
                mappings.biologic_moa_to_indications[moa.lower()] = indications

        return mappings

    def _build_reverse_lookups(self) -> None:
        """Build reverse lookup dictionaries for efficient querying."""
        if not self._mappings:
            return

        # Build indication -> EPC reverse lookup
        for epc_class, indications in self._mappings.fda_epc_to_indications.items():
            for indication in indications:
                ind_lower = indication.lower()
                if ind_lower not in self._mappings._indication_to_epc:
                    self._mappings._indication_to_epc[ind_lower] = []
                self._mappings._indication_to_epc[ind_lower].append(epc_class)

        # Build indication -> MOA reverse lookup
        for moa, indications in self._mappings.biologic_moa_to_indications.items():
            for indication in indications:
                ind_lower = indication.lower()
                if ind_lower not in self._mappings._indication_to_moa:
                    self._mappings._indication_to_moa[ind_lower] = []
                self._mappings._indication_to_moa[ind_lower].append(moa)

        # Build ICD-10 chapter -> indications lookup
        for indication, (code, chapter) in self._mappings.indication_to_icd10.items():
            if chapter:
                if chapter not in self._mappings._icd10_chapter_to_indications:
                    self._mappings._icd10_chapter_to_indications[chapter] = []
                self._mappings._icd10_chapter_to_indications[chapter].append(indication)

    @property
    def mappings(self) -> OntologyMappings:
        """Get loaded mappings, loading if necessary."""
        if not self._loaded:
            self.load()
        return self._mappings or OntologyMappings()

    def get_abbreviation(self, abbrev: str) -> str:
        """
        Get expanded form of an abbreviation.

        Args:
            abbrev: Abbreviation to expand

        Returns:
            Expanded form, or original if not found
        """
        mappings = self.mappings
        return mappings.abbreviations.get(abbrev, mappings.abbreviations.get(abbrev.lower(), abbrev))

    def get_icd10_code(self, indication: str) -> Optional[Tuple[str, str]]:
        """
        Get ICD-10 code for an indication.

        Args:
            indication: Indication name

        Returns:
            Tuple of (code, chapter) or None if not found
        """
        mappings = self.mappings
        ind_lower = indication.lower().strip()

        # Direct lookup
        if ind_lower in mappings.indication_to_icd10:
            return mappings.indication_to_icd10[ind_lower]

        # Partial match
        for key, value in mappings.indication_to_icd10.items():
            if key in ind_lower or ind_lower in key:
                return value

        return None

    def get_indications_for_chapter(self, chapter: str) -> List[str]:
        """
        Get all indications for an ICD-10 chapter.

        Args:
            chapter: Single letter ICD-10 chapter code

        Returns:
            List of indication names
        """
        mappings = self.mappings
        return mappings._icd10_chapter_to_indications.get(chapter.upper(), [])

    def get_indications_for_epc(self, epc_class: str) -> List[str]:
        """
        Get indications for an FDA EPC class.

        Args:
            epc_class: FDA EPC class string

        Returns:
            List of indication strings
        """
        mappings = self.mappings

        # Exact match
        if epc_class in mappings.fda_epc_to_indications:
            return mappings.fda_epc_to_indications[epc_class]

        # Partial match
        epc_lower = epc_class.lower().replace(" [epc]", "")
        for key, indications in mappings.fda_epc_to_indications.items():
            key_lower = key.lower().replace(" [epc]", "")
            if epc_lower in key_lower or key_lower in epc_lower:
                return indications

        return []

    def get_epc_for_indication(self, indication: str) -> List[str]:
        """
        Get FDA EPC classes that treat an indication.

        Args:
            indication: Indication name

        Returns:
            List of EPC class strings
        """
        mappings = self.mappings
        ind_lower = indication.lower().strip()

        # Direct lookup
        if ind_lower in mappings._indication_to_epc:
            return mappings._indication_to_epc[ind_lower]

        # Partial match
        matching = []
        for key, epcs in mappings._indication_to_epc.items():
            if ind_lower in key or key in ind_lower:
                matching.extend(epcs)

        return list(set(matching))

    def get_indications_for_moa(self, moa: str) -> List[str]:
        """
        Get indications for a mechanism of action.

        Args:
            moa: MOA string

        Returns:
            List of indication strings
        """
        mappings = self.mappings
        moa_lower = moa.lower().strip()

        # Exact match
        if moa_lower in mappings.biologic_moa_to_indications:
            return mappings.biologic_moa_to_indications[moa_lower]

        # Partial match
        for key, indications in mappings.biologic_moa_to_indications.items():
            if moa_lower in key or key in moa_lower:
                return indications

        return []

    def get_moa_for_indication(self, indication: str) -> List[str]:
        """
        Get MOAs that treat an indication.

        Args:
            indication: Indication name

        Returns:
            List of MOA strings
        """
        mappings = self.mappings
        ind_lower = indication.lower().strip()

        # Direct lookup
        if ind_lower in mappings._indication_to_moa:
            return mappings._indication_to_moa[ind_lower]

        # Partial match
        matching = []
        for key, moas in mappings._indication_to_moa.items():
            if ind_lower in key or key in ind_lower:
                matching.extend(moas)

        return list(set(matching))

    def is_biologic_indication(self, indication: str) -> bool:
        """
        Check if an indication is commonly treated by biologics.

        Args:
            indication: Indication name

        Returns:
            True if biologics commonly treat this indication
        """
        return len(self.get_moa_for_indication(indication)) > 0

    def expand_abbreviations(self, text: str) -> str:
        """
        Expand all abbreviations in text.

        Args:
            text: Text that may contain abbreviations

        Returns:
            Text with abbreviations expanded
        """
        import re

        mappings = self.mappings
        result = text

        for abbrev, expansion in mappings.abbreviations.items():
            # Only match whole words, case-insensitive
            pattern = rf'\b{re.escape(abbrev)}\b'
            result = re.sub(pattern, expansion, result, flags=re.IGNORECASE)

        return result

    # =========================================================================
    # WHO ICD API Dynamic Resolution
    # =========================================================================

    async def _ensure_who_icd_client(self) -> bool:
        """Ensure WHO ICD client is initialized."""
        if not self._who_icd_enabled:
            return False

        if self._who_icd_initialized:
            return self._who_icd_client is not None

        try:
            from ..external_apis.who_icd_client import WHOICDClient

            # Check if credentials are available
            client_id = os.getenv("WHO_ICD_CLIENT_ID")
            client_secret = os.getenv("WHO_ICD_CLIENT_SECRET")

            if not client_id or not client_secret:
                logger.debug(
                    "WHO ICD API credentials not configured - using static mappings only. "
                    "Set WHO_ICD_CLIENT_ID and WHO_ICD_CLIENT_SECRET for dynamic resolution."
                )
                self._who_icd_initialized = True
                return False

            self._who_icd_client = WHOICDClient()
            success = await self._who_icd_client.initialize()
            self._who_icd_initialized = True

            if success:
                logger.info("WHO ICD API enabled for dynamic ICD code resolution")
            else:
                logger.warning("WHO ICD API initialization failed - using static mappings only")
                self._who_icd_client = None

            return success

        except ImportError:
            logger.debug("WHO ICD client not available")
            self._who_icd_initialized = True
            return False
        except Exception as e:
            logger.warning(f"WHO ICD client initialization error: {e}")
            self._who_icd_initialized = True
            return False

    async def resolve_icd10_dynamic(
        self,
        indication: str,
        therapeutic_area: Optional[str] = None,
    ) -> Optional[Tuple[str, str]]:
        """
        Resolve an indication to ICD-10 code, using WHO ICD API as fallback.

        This method first checks the static YAML mappings, then falls back
        to the WHO ICD API for dynamic resolution if not found.

        Args:
            indication: Disease/condition name
            therapeutic_area: Optional therapeutic area hint

        Returns:
            Tuple of (ICD-10 code, chapter) or None if not found
        """
        ind_lower = indication.lower().strip()

        # Check static mappings first (fast path)
        static_result = self.get_icd10_code(indication)
        if static_result:
            return static_result

        # Check dynamic cache
        if ind_lower in self._dynamic_cache:
            return self._dynamic_cache[ind_lower]

        # Try WHO ICD API
        if not await self._ensure_who_icd_client():
            return None

        if not self._who_icd_client:
            return None

        try:
            icd_code = await self._who_icd_client.lookup_icd10_by_indication(
                indication=indication,
                therapeutic_area=therapeutic_area,
            )

            if icd_code:
                result = (icd_code.code, icd_code.chapter or icd_code.code[0])
                # Cache for future lookups
                self._dynamic_cache[ind_lower] = result
                logger.debug(f"WHO ICD resolved '{indication}' -> {icd_code.code}")
                return result

        except Exception as e:
            logger.warning(f"WHO ICD lookup failed for '{indication}': {e}")

        return None

    async def search_icd10_dynamic(
        self,
        query: str,
        max_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Search for ICD-10 codes using WHO ICD API.

        Args:
            query: Search text
            max_results: Maximum results to return

        Returns:
            List of matching codes with their details
        """
        if not await self._ensure_who_icd_client():
            return []

        if not self._who_icd_client:
            return []

        try:
            results = await self._who_icd_client.search_icd10(
                query=query,
                max_results=max_results,
            )
            return [r.to_dict() for r in results]
        except Exception as e:
            logger.warning(f"WHO ICD search failed for '{query}': {e}")
            return []

    async def get_icd10_details(self, code: str) -> Optional[Dict[str, Any]]:
        """
        Get full details for an ICD-10 code from WHO ICD API.

        Args:
            code: ICD-10 code (e.g., "M05.79")

        Returns:
            Dict with code details or None
        """
        if not await self._ensure_who_icd_client():
            return None

        if not self._who_icd_client:
            return None

        try:
            icd_code = await self._who_icd_client.get_icd10_code(code)
            return icd_code.to_dict() if icd_code else None
        except Exception as e:
            logger.warning(f"WHO ICD get_icd10_code failed for '{code}': {e}")
            return None

    async def get_icd10_hierarchy(
        self,
        code: str,
        include_children: bool = True,
        include_parent: bool = True,
    ) -> Dict[str, Any]:
        """
        Get ICD-10 code hierarchy from WHO ICD API.

        Args:
            code: ICD-10 code
            include_children: Include child codes
            include_parent: Include parent code

        Returns:
            Dict with code and its hierarchical relationships
        """
        result = {
            "code": code,
            "parent": None,
            "children": [],
        }

        if not await self._ensure_who_icd_client():
            return result

        if not self._who_icd_client:
            return result

        try:
            icd_code = await self._who_icd_client.get_icd10_code(code)
            if not icd_code:
                return result

            result["title"] = icd_code.title
            result["definition"] = icd_code.definition

            if include_parent and icd_code.parent_code:
                result["parent"] = icd_code.parent_code

            if include_children and icd_code.children:
                children = await self._who_icd_client.get_icd10_children(code)
                result["children"] = [
                    {"code": c.code, "title": c.title}
                    for c in children
                ]

        except Exception as e:
            logger.warning(f"WHO ICD hierarchy lookup failed for '{code}': {e}")

        return result

    def enable_dynamic_resolution(self, enable: bool = True) -> None:
        """
        Enable or disable WHO ICD API dynamic resolution.

        Args:
            enable: Whether to enable dynamic resolution
        """
        self._who_icd_enabled = enable
        if not enable:
            self._who_icd_client = None
            self._who_icd_initialized = False

    @property
    def who_icd_available(self) -> bool:
        """Check if WHO ICD API is available (credentials configured)."""
        client_id = os.getenv("WHO_ICD_CLIENT_ID")
        client_secret = os.getenv("WHO_ICD_CLIENT_SECRET")
        return bool(client_id and client_secret)


# Singleton instance
_ontology_loader: Optional[OntologyLoader] = None


def get_ontology_loader(config_path: Optional[str] = None) -> OntologyLoader:
    """
    Get or create the ontology loader singleton.

    Args:
        config_path: Optional path to config file

    Returns:
        OntologyLoader instance
    """
    global _ontology_loader

    if _ontology_loader is None:
        _ontology_loader = OntologyLoader(config_path)
        _ontology_loader.load()

    return _ontology_loader


def get_ontology_mappings(config_path: Optional[str] = None) -> OntologyMappings:
    """
    Convenience function to get loaded ontology mappings.

    Args:
        config_path: Optional path to config file

    Returns:
        OntologyMappings instance
    """
    return get_ontology_loader(config_path).mappings
