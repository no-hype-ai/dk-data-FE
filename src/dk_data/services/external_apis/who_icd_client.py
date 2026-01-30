"""
WHO ICD API Client.

Provides access to ICD-10 and ICD-11 codes from the official WHO ICD API.
Uses OAuth2 client credentials flow for authentication.

API Documentation: https://icd.who.int/icdapi
Swagger: https://id.who.int/swagger/index.html

Registration required at: https://icd.who.int/icdapi
"""

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from loguru import logger

from .base_client import APIClientConfig, BaseAPIClient
from .cache_manager import CacheManager


@dataclass
class ICDCode:
    """An ICD code (ICD-10 or ICD-11)."""

    code: str  # ICD code (e.g., "M05.79")
    title: str  # Display title
    definition: Optional[str] = None
    version: str = "ICD-10"  # ICD-10 or ICD-11
    chapter: Optional[str] = None  # Chapter letter/code
    block_id: Optional[str] = None  # Block identifier
    parent_code: Optional[str] = None
    children: List[str] = field(default_factory=list)
    synonyms: List[str] = field(default_factory=list)
    inclusions: List[str] = field(default_factory=list)
    exclusions: List[str] = field(default_factory=list)
    foundation_uri: Optional[str] = None  # WHO foundation URI

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "title": self.title,
            "definition": self.definition,
            "version": self.version,
            "chapter": self.chapter,
            "block_id": self.block_id,
            "parent_code": self.parent_code,
            "children": self.children,
            "synonyms": self.synonyms,
            "inclusions": self.inclusions,
            "exclusions": self.exclusions,
            "foundation_uri": self.foundation_uri,
        }


@dataclass
class ICDSearchResult:
    """Search result from ICD API."""

    code: str
    title: str
    score: float = 0.0
    matching_text: Optional[str] = None
    uri: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "title": self.title,
            "score": self.score,
            "matching_text": self.matching_text,
            "uri": self.uri,
        }


@dataclass
class OAuth2Token:
    """OAuth2 access token."""

    access_token: str
    token_type: str
    expires_at: datetime

    @property
    def is_expired(self) -> bool:
        # Consider expired 60 seconds before actual expiry
        return datetime.now() >= (self.expires_at - timedelta(seconds=60))


class WHOICDClient(BaseAPIClient[Dict[str, Any]]):
    """
    Client for WHO ICD API.

    Provides access to official ICD-10 and ICD-11 codes from WHO.
    Uses OAuth2 client credentials flow for authentication.

    Environment variables required:
    - WHO_ICD_CLIENT_ID: Client ID from icd.who.int registration
    - WHO_ICD_CLIENT_SECRET: Client secret from icd.who.int registration

    Usage:
        client = WHOICDClient()
        await client.initialize()

        # Search for ICD-10 codes
        results = await client.search_icd10("rheumatoid arthritis")

        # Get specific code details
        code = await client.get_icd10_code("M05.79")

        # Search ICD-11
        results = await client.search_icd11("rheumatoid arthritis")
    """

    # API endpoints
    TOKEN_URL = "https://icdaccessmanagement.who.int/connect/token"
    API_BASE_URL = "https://id.who.int"

    # Release IDs
    ICD10_RELEASE = "2019-covid-expanded"  # Latest ICD-10 with COVID codes
    ICD11_RELEASE = "2024-01"  # Latest ICD-11 release

    def __init__(self, cache_manager: Optional[CacheManager] = None):
        config = APIClientConfig(
            base_url=self.API_BASE_URL,
            timeout=30.0,
            max_retries=3,
            requests_per_second=10.0,
            cache_ttl=604800,  # 7 days (ICD codes rarely change)
            headers={
                "Accept": "application/json",
                "Accept-Language": "en",
                "API-Version": "v2",
            }
        )
        super().__init__(config, cache_manager)

        self._client_id = os.getenv("WHO_ICD_CLIENT_ID")
        self._client_secret = os.getenv("WHO_ICD_CLIENT_SECRET")
        self._token: Optional[OAuth2Token] = None
        self._initialized = False

    async def initialize(self) -> bool:
        """
        Initialize the client by obtaining an OAuth2 token.

        Returns:
            True if initialization successful
        """
        if not self._client_id or not self._client_secret:
            logger.warning(
                "WHO ICD API credentials not configured. "
                "Set WHO_ICD_CLIENT_ID and WHO_ICD_CLIENT_SECRET environment variables. "
                "Register at https://icd.who.int/icdapi"
            )
            return False

        try:
            await self._refresh_token()
            self._initialized = True
            logger.info("WHO ICD API client initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize WHO ICD client: {e}")
            return False

    async def _refresh_token(self) -> None:
        """Refresh the OAuth2 access token."""
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "scope": "icdapi_access",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            data = response.json()

            expires_in = data.get("expires_in", 3600)
            self._token = OAuth2Token(
                access_token=data["access_token"],
                token_type=data.get("token_type", "Bearer"),
                expires_at=datetime.now() + timedelta(seconds=expires_in),
            )
            logger.debug(f"WHO ICD token refreshed, expires in {expires_in}s")

    async def _ensure_token(self) -> Optional[str]:
        """Ensure we have a valid token, refreshing if necessary."""
        if not self._initialized:
            if not await self.initialize():
                return None

        if self._token is None or self._token.is_expired:
            await self._refresh_token()

        return self._token.access_token if self._token else None

    async def _authenticated_get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        use_cache: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Make an authenticated GET request."""
        token = await self._ensure_token()
        if not token:
            logger.error("No valid WHO ICD API token available")
            return None

        # Add auth header
        await self._get_client()
        self.config.headers["Authorization"] = f"Bearer {token}"

        try:
            return await self._get(endpoint, params=params, use_cache=use_cache)
        except Exception as e:
            logger.error(f"WHO ICD API request failed: {e}")
            return None

    async def health_check(self) -> bool:
        """Check if WHO ICD API is accessible."""
        try:
            token = await self._ensure_token()
            if not token:
                return False

            # Try to get ICD-10 root
            result = await self._authenticated_get(
                f"/icd/release/10/{self.ICD10_RELEASE}",
                use_cache=False
            )
            return result is not None
        except Exception as e:
            logger.error(f"WHO ICD health check failed: {e}")
            return False

    # =========================================================================
    # ICD-10 Methods
    # =========================================================================

    async def search_icd10(
        self,
        query: str,
        subtree_filter: Optional[str] = None,
        chapter_filter: Optional[str] = None,
        use_flexisearch: bool = True,
        flat_results: bool = True,
        max_results: int = 20,
    ) -> List[ICDSearchResult]:
        """
        Search for ICD-10 codes matching a text query.

        Args:
            query: Search text (e.g., "rheumatoid arthritis")
            subtree_filter: Limit search to a specific subtree (e.g., "M00-M99")
            chapter_filter: Limit to a chapter (e.g., "XIII")
            use_flexisearch: Use flexible matching (recommended)
            flat_results: Return flat list instead of hierarchy
            max_results: Maximum results to return

        Returns:
            List of matching ICD-10 codes
        """
        params = {
            "q": query,
            "useFlexisearch": str(use_flexisearch).lower(),
            "flatResults": str(flat_results).lower(),
        }

        if subtree_filter:
            params["subtreesFilter"] = subtree_filter
        if chapter_filter:
            params["chapterFilter"] = chapter_filter

        endpoint = f"/icd/release/10/{self.ICD10_RELEASE}/search"
        result = await self._authenticated_get(endpoint, params=params)

        if not result:
            return []

        results = []
        for item in result.get("destinationEntities", [])[:max_results]:
            # Extract code from URI
            uri = item.get("id", "")
            code = uri.split("/")[-1] if uri else ""

            results.append(ICDSearchResult(
                code=code,
                title=item.get("title", ""),
                score=item.get("score", 0.0),
                matching_text=item.get("matchingPVs", [{}])[0].get("propertyValue") if item.get("matchingPVs") else None,
                uri=uri,
            ))

        return results

    async def get_icd10_code(self, code: str) -> Optional[ICDCode]:
        """
        Get details for a specific ICD-10 code.

        Args:
            code: ICD-10 code (e.g., "M05.79", "M05", "M00-M99")

        Returns:
            ICDCode with full details or None
        """
        # Normalize code format for URL
        code_url = code.replace(".", "")

        endpoint = f"/icd/release/10/{self.ICD10_RELEASE}/{code_url}"
        result = await self._authenticated_get(endpoint)

        if not result:
            return None

        return self._parse_icd10_entity(result)

    async def get_icd10_chapter(self, chapter: str) -> Optional[ICDCode]:
        """
        Get an ICD-10 chapter.

        Args:
            chapter: Chapter number (e.g., "XIII" or "M00-M99")

        Returns:
            ICDCode for the chapter
        """
        # Chapters are accessed directly
        return await self.get_icd10_code(chapter)

    async def get_icd10_children(self, code: str) -> List[ICDCode]:
        """
        Get child codes of an ICD-10 code.

        Args:
            code: Parent ICD-10 code

        Returns:
            List of child ICDCodes
        """
        parent = await self.get_icd10_code(code)
        if not parent or not parent.children:
            return []

        children = []
        for child_uri in parent.children:
            child_code = child_uri.split("/")[-1]
            child = await self.get_icd10_code(child_code)
            if child:
                children.append(child)

        return children

    async def lookup_icd10_by_indication(
        self,
        indication: str,
        therapeutic_area: Optional[str] = None
    ) -> Optional[ICDCode]:
        """
        Look up the best matching ICD-10 code for a disease/indication.

        This is the main method for dynamic ICD-10 resolution.

        Args:
            indication: Disease/condition name (e.g., "rheumatoid arthritis")
            therapeutic_area: Optional therapeutic area hint (e.g., "oncology")

        Returns:
            Best matching ICDCode or None
        """
        # Build search with optional therapeutic area filter
        chapter_filter = None
        if therapeutic_area:
            chapter_filter = self._therapeutic_area_to_chapter(therapeutic_area)

        results = await self.search_icd10(
            query=indication,
            chapter_filter=chapter_filter,
            max_results=5,
        )

        if not results:
            return None

        # Get full details for best match
        best_match = results[0]
        return await self.get_icd10_code(best_match.code)

    def _therapeutic_area_to_chapter(self, therapeutic_area: str) -> Optional[str]:
        """Map therapeutic area to ICD-10 chapter filter."""
        area_lower = therapeutic_area.lower()

        mappings = {
            "oncology": "II",  # C00-D48 Neoplasms
            "immunology": "III",  # D50-D89 Blood/immune
            "endocrinology": "IV",  # E00-E90 Endocrine
            "neurology": "VI",  # G00-G99 Nervous system
            "ophthalmology": "VII",  # H00-H59 Eye
            "cardiology": "IX",  # I00-I99 Circulatory
            "cardiovascular": "IX",
            "respiratory": "X",  # J00-J99 Respiratory
            "pulmonology": "X",
            "gastroenterology": "XI",  # K00-K93 Digestive
            "dermatology": "XII",  # L00-L99 Skin
            "rheumatology": "XIII",  # M00-M99 Musculoskeletal
            "nephrology": "XIV",  # N00-N99 Genitourinary
            "infectious": "I",  # A00-B99 Infectious
            "psychiatry": "V",  # F00-F99 Mental
            "hematology": "III",  # D50-D89
        }

        for key, chapter in mappings.items():
            if key in area_lower:
                return chapter

        return None

    def _parse_icd10_entity(self, data: Dict[str, Any]) -> ICDCode:
        """Parse an ICD-10 entity response into ICDCode."""
        # Extract code from @id URI
        uri = data.get("@id", "")
        code_raw = uri.split("/")[-1] if uri else ""

        # Format code with decimal (e.g., "M0579" -> "M05.79")
        code = self._format_icd10_code(code_raw)

        # Get title (prefer browserUrl format)
        title_data = data.get("title", {})
        if isinstance(title_data, dict):
            title = title_data.get("@value", "")
        else:
            title = str(title_data)

        # Get definition
        definition = None
        if "definition" in data:
            def_data = data["definition"]
            if isinstance(def_data, dict):
                definition = def_data.get("@value", "")
            else:
                definition = str(def_data)

        # Get chapter (from classKind or parent)
        chapter = None
        class_kind = data.get("classKind", "")
        if class_kind == "chapter":
            chapter = code
        elif len(code) >= 1:
            chapter = code[0]  # First letter is chapter

        # Get children URIs
        children = data.get("child", [])
        if isinstance(children, str):
            children = [children]

        # Get parent
        parent = data.get("parent", [])
        parent_code = None
        if parent:
            if isinstance(parent, list):
                parent_code = parent[0].split("/")[-1] if parent else None
            else:
                parent_code = parent.split("/")[-1]
            if parent_code:
                parent_code = self._format_icd10_code(parent_code)

        # Get index terms (synonyms)
        synonyms = []
        index_terms = data.get("indexTerm", [])
        if isinstance(index_terms, list):
            for term in index_terms:
                if isinstance(term, dict):
                    label = term.get("label", {})
                    if isinstance(label, dict):
                        synonyms.append(label.get("@value", ""))
                    else:
                        synonyms.append(str(label))

        # Get inclusions
        inclusions = []
        inclusion_data = data.get("inclusion", [])
        if isinstance(inclusion_data, list):
            for inc in inclusion_data:
                if isinstance(inc, dict):
                    label = inc.get("label", {})
                    if isinstance(label, dict):
                        inclusions.append(label.get("@value", ""))

        # Get exclusions
        exclusions = []
        exclusion_data = data.get("exclusion", [])
        if isinstance(exclusion_data, list):
            for exc in exclusion_data:
                if isinstance(exc, dict):
                    label = exc.get("label", {})
                    if isinstance(label, dict):
                        exclusions.append(label.get("@value", ""))

        return ICDCode(
            code=code,
            title=title,
            definition=definition,
            version="ICD-10",
            chapter=chapter,
            parent_code=parent_code,
            children=[c.split("/")[-1] for c in children] if children else [],
            synonyms=synonyms,
            inclusions=inclusions,
            exclusions=exclusions,
            foundation_uri=uri,
        )

    def _format_icd10_code(self, code: str) -> str:
        """Format ICD-10 code with proper decimal placement."""
        code = code.upper().strip()

        # Already has decimal
        if "." in code:
            return code

        # No decimal needed for 3 chars or less
        if len(code) <= 3:
            return code

        # Add decimal after first 3 characters
        return f"{code[:3]}.{code[3:]}"

    # =========================================================================
    # ICD-11 Methods
    # =========================================================================

    async def search_icd11(
        self,
        query: str,
        subtree_filter: Optional[str] = None,
        use_flexisearch: bool = True,
        flat_results: bool = True,
        max_results: int = 20,
    ) -> List[ICDSearchResult]:
        """
        Search for ICD-11 codes matching a text query.

        Args:
            query: Search text
            subtree_filter: Limit search to a specific subtree
            use_flexisearch: Use flexible matching
            flat_results: Return flat list
            max_results: Maximum results

        Returns:
            List of matching ICD-11 codes
        """
        params = {
            "q": query,
            "useFlexisearch": str(use_flexisearch).lower(),
            "flatResults": str(flat_results).lower(),
        }

        if subtree_filter:
            params["subtreesFilter"] = subtree_filter

        endpoint = f"/icd/release/11/{self.ICD11_RELEASE}/mms/search"
        result = await self._authenticated_get(endpoint, params=params)

        if not result:
            return []

        results = []
        for item in result.get("destinationEntities", [])[:max_results]:
            # ICD-11 uses theCode field
            code = item.get("theCode", "")
            if not code:
                # Extract from URI
                uri = item.get("id", "")
                code = uri.split("/")[-1] if uri else ""

            results.append(ICDSearchResult(
                code=code,
                title=item.get("title", ""),
                score=item.get("score", 0.0),
                uri=item.get("id"),
            ))

        return results

    async def get_icd11_code(self, code: str) -> Optional[ICDCode]:
        """
        Get details for a specific ICD-11 code.

        Args:
            code: ICD-11 code

        Returns:
            ICDCode with full details
        """
        endpoint = f"/icd/release/11/{self.ICD11_RELEASE}/mms/codeinfo/{code}"
        result = await self._authenticated_get(endpoint)

        if not result:
            # Try searching for the code
            search_results = await self.search_icd11(code, max_results=1)
            if search_results and search_results[0].uri:
                # Get from URI
                result = await self._authenticated_get(search_results[0].uri)

        if not result:
            return None

        return self._parse_icd11_entity(result)

    def _parse_icd11_entity(self, data: Dict[str, Any]) -> ICDCode:
        """Parse an ICD-11 entity response into ICDCode."""
        code = data.get("code", data.get("theCode", ""))

        title_data = data.get("title", {})
        if isinstance(title_data, dict):
            title = title_data.get("@value", "")
        else:
            title = str(title_data)

        definition = None
        if "definition" in data:
            def_data = data["definition"]
            if isinstance(def_data, dict):
                definition = def_data.get("@value", "")
            else:
                definition = str(def_data)

        # Get synonyms from indexTerm
        synonyms = []
        for term in data.get("indexTerm", []):
            if isinstance(term, dict):
                label = term.get("label", {})
                if isinstance(label, dict):
                    synonyms.append(label.get("@value", ""))

        return ICDCode(
            code=code,
            title=title,
            definition=definition,
            version="ICD-11",
            synonyms=synonyms,
            foundation_uri=data.get("@id"),
        )

    # =========================================================================
    # ICD Foundation Methods
    # =========================================================================

    async def search_foundation(
        self,
        query: str,
        use_flexisearch: bool = True,
        flat_results: bool = True,
        max_results: int = 20,
    ) -> List[ICDSearchResult]:
        """
        Search the ICD Foundation component.

        The Foundation is the comprehensive semantic layer containing
        all ICD entities with their full semantics, not constrained
        by any linearization rules.

        Args:
            query: Search text
            use_flexisearch: Use flexible matching
            flat_results: Return flat list
            max_results: Maximum results

        Returns:
            List of matching foundation entities
        """
        params = {
            "q": query,
            "useFlexisearch": str(use_flexisearch).lower(),
            "flatResults": str(flat_results).lower(),
        }

        endpoint = "/icd/entity/search"
        result = await self._authenticated_get(endpoint, params=params)

        if not result:
            return []

        results = []
        for item in result.get("destinationEntities", [])[:max_results]:
            uri = item.get("id", "")
            # Foundation uses entity IDs, not codes
            entity_id = uri.split("/")[-1] if uri else ""

            results.append(ICDSearchResult(
                code=entity_id,
                title=item.get("title", ""),
                score=item.get("score", 0.0),
                uri=uri,
            ))

        return results

    async def get_foundation_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a foundation entity by its ID.

        Foundation entities contain rich semantic content including:
        - Multiple parents (polyhierarchy)
        - Definitions
        - Synonyms
        - Narrower terms
        - Exclusions

        Args:
            entity_id: Foundation entity ID

        Returns:
            Full entity data or None
        """
        endpoint = f"/icd/entity/{entity_id}"
        return await self._authenticated_get(endpoint)

    async def get_foundation_linearization_uris(
        self,
        entity_id: str
    ) -> Dict[str, Optional[str]]:
        """
        Get linearization URIs for a foundation entity.

        This shows which linearizations (ICD-10, ICD-11 MMS, etc.)
        include this entity and what code it maps to.

        Args:
            entity_id: Foundation entity ID

        Returns:
            Dict mapping linearization name to URI/code
        """
        entity = await self.get_foundation_entity(entity_id)
        if not entity:
            return {}

        linearizations = {}

        # Check for ICD-11 MMS
        if "classKind" in entity:
            linearizations["icd11_mms"] = entity.get("@id")

        # Look for linearization links
        for key in ["icd10", "icd11"]:
            if key in entity:
                linearizations[key] = entity[key]

        return linearizations

    # =========================================================================
    # ICD-10 to ICD-11 Mapping
    # =========================================================================

    async def map_icd10_to_icd11(
        self,
        icd10_code: str
    ) -> Optional[ICDCode]:
        """
        Map an ICD-10 code to its ICD-11 equivalent.

        Uses the WHO mapping tables to find the corresponding
        ICD-11 code for a given ICD-10 code.

        Args:
            icd10_code: ICD-10 code (e.g., "M05.79")

        Returns:
            Corresponding ICD-11 code or None
        """
        # Search ICD-11 for the ICD-10 code title
        icd10_entity = await self.get_icd10_code(icd10_code)
        if not icd10_entity:
            return None

        # Search ICD-11 using the ICD-10 title
        results = await self.search_icd11(
            query=icd10_entity.title,
            max_results=5
        )

        if not results:
            return None

        # Return the best match
        return await self.get_icd11_code(results[0].code)

    async def get_icd11_mms_entity(self, code_or_uri: str) -> Optional[ICDCode]:
        """
        Get an ICD-11 MMS (Mortality and Morbidity Statistics) entity.

        MMS is the primary tabular list for mortality and morbidity
        statistics, replacing ICD-10 for international reporting.

        Args:
            code_or_uri: ICD-11 code or full URI

        Returns:
            ICDCode with MMS details
        """
        if code_or_uri.startswith("http"):
            # It's a URI, fetch directly
            result = await self._authenticated_get(code_or_uri)
        else:
            # It's a code, use codeinfo endpoint
            endpoint = f"/icd/release/11/{self.ICD11_RELEASE}/mms/codeinfo/{code_or_uri}"
            result = await self._authenticated_get(endpoint)

        if not result:
            return None

        return self._parse_icd11_entity(result)

    # =========================================================================
    # Hierarchical Navigation
    # =========================================================================

    async def get_icd10_ancestors(self, code: str) -> List[ICDCode]:
        """
        Get all ancestor codes (parents, grandparents, etc.) for an ICD-10 code.

        Args:
            code: ICD-10 code

        Returns:
            List of ancestor codes from immediate parent to chapter
        """
        ancestors = []
        current = await self.get_icd10_code(code)

        if not current:
            return []

        while current and current.parent_code:
            parent = await self.get_icd10_code(current.parent_code)
            if parent:
                ancestors.append(parent)
                current = parent
            else:
                break

        return ancestors

    async def get_icd10_siblings(self, code: str) -> List[ICDCode]:
        """
        Get sibling codes (same parent) for an ICD-10 code.

        Args:
            code: ICD-10 code

        Returns:
            List of sibling codes
        """
        current = await self.get_icd10_code(code)
        if not current or not current.parent_code:
            return []

        parent = await self.get_icd10_code(current.parent_code)
        if not parent:
            return []

        siblings = []
        for child_code in parent.children:
            if child_code != code:
                child = await self.get_icd10_code(child_code)
                if child:
                    siblings.append(child)

        return siblings

    async def get_full_hierarchy(
        self,
        code: str,
        version: str = "ICD-10"
    ) -> Dict[str, Any]:
        """
        Get the full hierarchical context for a code.

        Args:
            code: ICD code
            version: "ICD-10" or "ICD-11"

        Returns:
            Dict with ancestors, current, children, and siblings
        """
        if version == "ICD-11":
            current = await self.get_icd11_code(code)
            children = []  # ICD-11 children would need separate implementation
            ancestors = []
            siblings = []
        else:
            current = await self.get_icd10_code(code)
            children = await self.get_icd10_children(code) if current else []
            ancestors = await self.get_icd10_ancestors(code) if current else []
            siblings = await self.get_icd10_siblings(code) if current else []

        return {
            "code": code,
            "version": version,
            "current": current.to_dict() if current else None,
            "ancestors": [a.to_dict() for a in ancestors],
            "children": [c.to_dict() for c in children],
            "siblings": [s.to_dict() for s in siblings],
        }

    # =========================================================================
    # Batch Operations
    # =========================================================================

    async def resolve_indications_batch(
        self,
        indications: List[str],
        version: str = "ICD-10"
    ) -> Dict[str, Optional[ICDCode]]:
        """
        Resolve multiple indications to ICD codes in batch.

        Args:
            indications: List of indication texts
            version: "ICD-10" or "ICD-11"

        Returns:
            Dict mapping indication text to ICDCode (or None if not found)
        """
        results = {}

        for indication in indications:
            if version == "ICD-11":
                code = await self.lookup_icd11_by_indication(indication)
            else:
                code = await self.lookup_icd10_by_indication(indication)
            results[indication] = code

        return results

    async def lookup_icd11_by_indication(
        self,
        indication: str,
    ) -> Optional[ICDCode]:
        """
        Look up the best matching ICD-11 code for a disease/indication.

        Args:
            indication: Disease/condition name

        Returns:
            Best matching ICDCode or None
        """
        results = await self.search_icd11(query=indication, max_results=5)

        if not results:
            return None

        best_match = results[0]
        return await self.get_icd11_code(best_match.code)

    # =========================================================================
    # Cross-version Utilities
    # =========================================================================

    async def get_all_codes_for_indication(
        self,
        indication: str
    ) -> Dict[str, Optional[ICDCode]]:
        """
        Get ICD codes across all supported versions for an indication.

        Args:
            indication: Disease/condition name

        Returns:
            Dict with keys "icd10" and "icd11" mapped to their codes
        """
        icd10 = await self.lookup_icd10_by_indication(indication)
        icd11 = await self.lookup_icd11_by_indication(indication)

        return {
            "icd10": icd10,
            "icd11": icd11,
        }


# Singleton instance
_who_icd_client: Optional[WHOICDClient] = None


async def get_who_icd_client(
    cache_manager: Optional[CacheManager] = None
) -> WHOICDClient:
    """Get or create the WHO ICD client instance."""
    global _who_icd_client

    if _who_icd_client is None:
        _who_icd_client = WHOICDClient(cache_manager)
        await _who_icd_client.initialize()

    return _who_icd_client
