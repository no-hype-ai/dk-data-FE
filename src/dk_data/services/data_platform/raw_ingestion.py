"""
Raw Ingestion Service

Fetches data from external APIs and stores complete responses in the Raw layer.
Implements tiered refresh schedules: Daily (clinical trials, FDA), Weekly (FAERS), Monthly (reference).

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

import hashlib
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import logging
import aiohttp

logger = logging.getLogger(__name__)


class DataSource(Enum):
    """Available data sources with their refresh tiers."""
    CLINICALTRIALS = "clinicaltrials"
    OPENFDA_FAERS = "openfda_faers"
    OPENFDA_LABELS = "openfda_labels"
    CHEMBL = "chembl"
    DRUGBANK = "drugbank"
    PUBCHEM = "pubchem"
    UNIPROT = "uniprot"
    PDB = "pdb"
    SIDER = "sider"
    OPENALEX = "openalex"
    # New data sources for 012-dk-data-platform spec
    BINDINGDB = "bindingdb"
    EMA = "ema"
    ORANGE_BOOK = "orange_book"
    USPTO_PATENTS = "uspto_patents"
    # Research code and biologic coverage sources
    WHO_INN = "who_inn"              # WHO International Non-proprietary Names (research code mappings)
    KEGG_DRUG = "kegg_drug"          # KEGG Drug database (research codes, pathways)
    TTD = "ttd"                      # Therapeutic Target Database (biologics, targets)
    FDA_DRUGS = "fda_drugs"          # FDA Drugs@FDA (approved drugs, research codes)
    IMGT = "imgt"                    # ImMunoGeneTics (antibody/biologic sequences)
    CDC_VACCINES = "cdc_vaccines"    # CDC Vaccine Information (vaccine schedules)
    # Complete medallion architecture sources
    RXNORM = "rxnorm"                # RxNorm drug nomenclature
    TDC_ADMET = "tdc_admet"          # Therapeutics Data Commons ADMET
    PHARMGKB = "pharmgkb"            # PharmGKB pharmacogenomics
    WEBSEARCH = "websearch"          # Web search for news/publications
    DAILYMED = "dailymed"            # DailyMed drug labels
    # Assessment-enrichment sources (xenon integration)
    REACTOME = "reactome"              # Reactome biological pathways
    NICE_HTA = "nice_hta"              # NICE Technology Appraisals (UK HTA)
    CMS_OPEN_PAYMENTS = "cms_open_payments"  # CMS Open Payments (physician KOL data)
    CMS_MEDICARE = "cms_medicare"      # CMS Medicare Part B/D drug spending
    NIH_REPORTER = "nih_reporter"      # NIH RePORTER research grants
    NPI_REGISTRY = "npi_registry"      # NPI Registry physician directory
    EUROPEPMC = "europepmc"            # EuropePMC full-text literature
    FDA_DRUGSFDA = "fda_drugsfda"      # FDA Drugs@FDA approval history


# Tiered refresh schedule (in hours)
REFRESH_SCHEDULE = {
    DataSource.CLINICALTRIALS: 24,      # Daily
    DataSource.OPENFDA_LABELS: 24,      # Daily
    DataSource.OPENFDA_FAERS: 168,      # Weekly
    DataSource.CHEMBL: 720,             # Monthly
    DataSource.DRUGBANK: 720,           # Monthly
    DataSource.PUBCHEM: 720,            # Monthly
    DataSource.UNIPROT: 720,            # Monthly
    DataSource.PDB: 720,                # Monthly
    DataSource.SIDER: 720,              # Monthly
    DataSource.OPENALEX: 168,           # Weekly
    # New data sources
    DataSource.BINDINGDB: 720,          # Monthly (large bulk download)
    DataSource.EMA: 168,                # Weekly (regulatory updates)
    DataSource.ORANGE_BOOK: 168,        # Weekly (patent expirations)
    DataSource.USPTO_PATENTS: 168,      # Weekly (patent filings)
    # Research code and biologic sources
    DataSource.WHO_INN: 2160,           # Quarterly (INN lists published quarterly)
    DataSource.KEGG_DRUG: 720,          # Monthly
    DataSource.TTD: 720,                # Monthly
    DataSource.FDA_DRUGS: 168,          # Weekly (new approvals)
    DataSource.IMGT: 720,               # Monthly
    DataSource.CDC_VACCINES: 720,       # Monthly
    # Complete medallion architecture sources
    DataSource.RXNORM: 168,             # Weekly (RxNorm updates weekly)
    DataSource.TDC_ADMET: 720,          # Monthly (TDC dataset updates)
    DataSource.PHARMGKB: 720,           # Monthly (pharmacogenomics)
    DataSource.WEBSEARCH: 24,           # On-demand (web search)
    DataSource.DAILYMED: 168,           # Weekly (label updates)
    # Assessment-enrichment sources
    DataSource.REACTOME: 720,           # Monthly (pathway database)
    DataSource.NICE_HTA: 168,           # Weekly (HTA decisions)
    DataSource.CMS_OPEN_PAYMENTS: 720,  # Monthly (annual data release)
    DataSource.CMS_MEDICARE: 720,       # Monthly (annual data release)
    DataSource.NIH_REPORTER: 168,       # Weekly (grant data)
    DataSource.NPI_REGISTRY: 720,       # Monthly (provider updates)
    DataSource.EUROPEPMC: 168,          # Weekly (literature)
    DataSource.FDA_DRUGSFDA: 168,       # Weekly (approval data)
}


@dataclass
class RawRecord:
    """Raw layer record structure."""
    request_id: str
    api_endpoint: str
    request_params: Dict[str, Any]
    response_status: int
    response_headers: Dict[str, str]
    response_body: Dict[str, Any]
    response_body_hash: str


class RawIngestionService:
    """
    Service for ingesting data from external APIs into the Raw layer.

    Stores complete HTTP responses with:
    - Full request metadata (endpoint, params)
    - Complete response (status, headers, body)
    - Content hash for deduplication
    - Processing status tracking
    """

    def __init__(self, db_pool, http_session: Optional[aiohttp.ClientSession] = None):
        """
        Initialize the raw ingestion service.

        Args:
            db_pool: Database connection pool
            http_session: Optional aiohttp session (created if not provided)
        """
        self.db_pool = db_pool
        self._http_session = http_session
        self._owns_session = http_session is None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._http_session is None:
            self._http_session = aiohttp.ClientSession()
        return self._http_session

    async def close(self):
        """Close HTTP session if owned."""
        if self._owns_session and self._http_session:
            await self._http_session.close()

    @staticmethod
    def compute_hash(data: Dict[str, Any]) -> str:
        """Compute SHA-256 hash of response body for deduplication."""
        json_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode()).hexdigest()

    async def fetch_and_store(
        self,
        source: DataSource,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        request_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Fetch from API and store in Raw layer.

        Args:
            source: Data source enum
            endpoint: API endpoint URL
            params: Query parameters
            headers: Request headers
            request_id: Optional custom request ID

        Returns:
            Record ID if stored, None if duplicate or error
        """
        params = params or {}
        headers = headers or {}
        request_id = request_id or f"{source.value}_{datetime.utcnow().isoformat()}"

        session = await self._get_session()

        try:
            # Build URL manually for APIs with complex search syntax (openFDA uses quotes in params)
            # aiohttp's params= auto-encodes which double-encodes quote characters
            if params:
                from urllib.parse import urlencode, quote
                # Use quote_via=quote to avoid double-encoding of special chars like "
                query_string = "&".join(
                    f"{k}={v}" if isinstance(v, str) and ('"' in v or '+' in v or '(' in v)
                    else f"{k}={quote(str(v))}"
                    for k, v in params.items()
                )
                full_url = f"{endpoint}?{query_string}"
            else:
                full_url = endpoint

            async with session.get(full_url, headers=headers) as response:
                response_body = await response.json()
                response_headers = dict(response.headers)

                record = RawRecord(
                    request_id=request_id,
                    api_endpoint=endpoint,
                    request_params=params,
                    response_status=response.status,
                    response_headers=response_headers,
                    response_body=response_body,
                    response_body_hash=self.compute_hash(response_body)
                )

                return await self._store_raw_record(source, record)

        except aiohttp.ClientError as e:
            logger.error(f"HTTP error fetching {endpoint}: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for {endpoint}: {e}")
            return None

    # ALL sources use mol_raw.* schema — no exceptions.
    # The mol_ prefix is the canonical medallion architecture namespace.
    MOL_RAW_SOURCES = {
        # Core molecule sources
        DataSource.OPENFDA_LABELS, DataSource.OPENFDA_FAERS,
        DataSource.CLINICALTRIALS, DataSource.CHEMBL,
        DataSource.PUBCHEM, DataSource.OPENALEX,
        DataSource.DRUGBANK, DataSource.UNIPROT,
        DataSource.SIDER, DataSource.PDB,
        # Assessment-enrichment sources
        DataSource.REACTOME, DataSource.NICE_HTA,
        DataSource.CMS_OPEN_PAYMENTS, DataSource.CMS_MEDICARE,
        DataSource.NIH_REPORTER, DataSource.NPI_REGISTRY,
        DataSource.EUROPEPMC, DataSource.FDA_DRUGSFDA,
        DataSource.KEGG_DRUG, DataSource.FDA_DRUGS,
        # Reference/regulatory sources
        DataSource.BINDINGDB, DataSource.EMA,
        DataSource.ORANGE_BOOK, DataSource.USPTO_PATENTS,
        DataSource.WHO_INN, DataSource.RXNORM,
        DataSource.TDC_ADMET, DataSource.PHARMGKB,
        DataSource.WEBSEARCH, DataSource.DAILYMED,
        DataSource.IMGT, DataSource.CDC_VACCINES,
    }

    async def _store_raw_record(self, source: DataSource, record: RawRecord) -> Optional[str]:
        """Store raw record in mol_raw.* for molecule sources, raw.* for others."""
        schema = "mol_raw" if source in self.MOL_RAW_SOURCES else "raw"
        table_name = f"{schema}.{source.value}"

        async with self.db_pool.acquire() as conn:
            # Check for duplicate based on hash
            existing = await conn.fetchval(f"""
                SELECT id FROM {table_name}
                WHERE response_body_hash = $1
                  AND request_timestamp > NOW() - INTERVAL '1 hour'
                LIMIT 1
            """, record.response_body_hash)

            if existing:
                logger.debug(f"Duplicate response detected for {source.value}, skipping")
                return None

            # Insert new record
            row = await conn.fetchrow(f"""
                INSERT INTO {table_name} (
                    request_id,
                    api_endpoint,
                    request_params,
                    response_status,
                    response_headers,
                    response_body,
                    response_body_hash
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id::text
            """,
                record.request_id,
                record.api_endpoint,
                json.dumps(record.request_params),
                record.response_status,
                json.dumps(record.response_headers),
                json.dumps(record.response_body),
                record.response_body_hash
            )

            return row['id'] if row else None

    async def should_refresh(self, source: DataSource, endpoint: str) -> bool:
        """Check if source needs refresh based on tiered schedule."""
        refresh_hours = REFRESH_SCHEDULE.get(source, 24)
        table_name = f"raw.{source.value}"

        async with self.db_pool.acquire() as conn:
            last_fetch = await conn.fetchval(f"""
                SELECT MAX(request_timestamp)
                FROM {table_name}
                WHERE api_endpoint = $1
                  AND response_status = 200
            """, endpoint)

            if last_fetch is None:
                return True

            threshold = datetime.utcnow() - timedelta(hours=refresh_hours)
            return last_fetch < threshold

    async def get_unprocessed_records(
        self,
        source: DataSource,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get raw records not yet processed to Bronze."""
        table_name = f"raw.{source.value}"

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(f"""
                SELECT id, request_id, response_body, request_timestamp
                FROM {table_name}
                WHERE processed_to_bronze = FALSE
                  AND response_status = 200
                ORDER BY request_timestamp ASC
                LIMIT $1
            """, limit)

            return [dict(row) for row in rows]

    async def mark_processed(self, source: DataSource, record_ids: List[str]):
        """Mark records as processed to Bronze."""
        if not record_ids:
            return

        table_name = f"raw.{source.value}"

        async with self.db_pool.acquire() as conn:
            await conn.execute(f"""
                UPDATE {table_name}
                SET processed_to_bronze = TRUE,
                    processed_at = NOW()
                WHERE id = ANY($1::uuid[])
            """, record_ids)


class ClinicalTrialsIngestion(RawIngestionService):
    """Specialized ingestion for ClinicalTrials.gov API v2."""

    BASE_URL = "https://clinicaltrials.gov/api/v2/studies"

    async def fetch_studies(
        self,
        query: Optional[str] = None,
        condition: Optional[str] = None,
        intervention: Optional[str] = None,
        page_size: int = 100,
        page_token: Optional[str] = None
    ) -> Optional[str]:
        """Fetch clinical trials studies."""
        params = {
            "format": "json",
            "pageSize": page_size,
        }

        if query:
            params["query.term"] = query
        if condition:
            params["query.cond"] = condition
        if intervention:
            params["query.intr"] = intervention
        if page_token:
            params["pageToken"] = page_token

        return await self.fetch_and_store(
            DataSource.CLINICALTRIALS,
            self.BASE_URL,
            params=params
        )

    async def fetch_study_by_nct(self, nct_id: str) -> Optional[str]:
        """Fetch single study by NCT ID."""
        endpoint = f"{self.BASE_URL}/{nct_id}"
        return await self.fetch_and_store(
            DataSource.CLINICALTRIALS,
            endpoint,
            request_id=f"clinicaltrials_{nct_id}"
        )


class OpenFDAIngestion(RawIngestionService):
    """Specialized ingestion for OpenFDA APIs (FAERS, Labels)."""

    FAERS_URL = "https://api.fda.gov/drug/event.json"
    LABELS_URL = "https://api.fda.gov/drug/label.json"

    async def fetch_faers_events(
        self,
        drug_name: str,
        limit: int = 100,
        skip: int = 0
    ) -> Optional[str]:
        """Fetch FAERS adverse event reports."""
        params = {
            "search": f'patient.drug.medicinalproduct:"{drug_name}"',
            "limit": limit,
            "skip": skip,
        }

        return await self.fetch_and_store(
            DataSource.OPENFDA_FAERS,
            self.FAERS_URL,
            params=params,
            request_id=f"faers_{drug_name}_{skip}"
        )

    async def fetch_drug_labels(
        self,
        drug_name: Optional[str] = None,
        application_number: Optional[str] = None,
        limit: int = 100,
        skip: int = 0
    ) -> Optional[str]:
        """Fetch FDA drug labels. Searches both brand_name and generic_name."""
        search_parts = []
        if drug_name:
            # openFDA exact phrase search is case-sensitive — search both cases
            # Also search substance_name which has the INN name
            name_upper = drug_name.upper()
            name_title = drug_name.title()
            search_parts.append(
                f'(openfda.brand_name:"{name_upper}"+openfda.brand_name:"{name_title}"'
                f'+openfda.generic_name:"{name_upper}"+openfda.generic_name:"{drug_name}"'
                f'+openfda.substance_name:"{name_upper}")'
            )
        if application_number:
            search_parts.append(f'openfda.application_number:"{application_number}"')

        params = {
            "search": " AND ".join(search_parts) if search_parts else "*",
            "limit": limit,
            "skip": skip,
        }

        return await self.fetch_and_store(
            DataSource.OPENFDA_LABELS,
            self.LABELS_URL,
            params=params
        )


class ChEMBLIngestion(RawIngestionService):
    """Specialized ingestion for ChEMBL API."""

    BASE_URL = "https://www.ebi.ac.uk/chembl/api/data"

    async def fetch_molecule(self, chembl_id: str) -> Optional[str]:
        """Fetch molecule by ChEMBL ID."""
        endpoint = f"{self.BASE_URL}/molecule/{chembl_id}.json"
        return await self.fetch_and_store(
            DataSource.CHEMBL,
            endpoint,
            request_id=f"chembl_{chembl_id}"
        )

    async def fetch_molecule_by_name(self, name: str) -> Optional[str]:
        """Search molecules by name."""
        endpoint = f"{self.BASE_URL}/molecule/search.json"
        params = {"q": name}
        return await self.fetch_and_store(
            DataSource.CHEMBL,
            endpoint,
            params=params,
            request_id=f"chembl_search_{name}"
        )

    async def fetch_activities(
        self,
        chembl_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> Optional[str]:
        """Fetch bioactivities for a molecule."""
        endpoint = f"{self.BASE_URL}/activity.json"
        params = {
            "molecule_chembl_id": chembl_id,
            "limit": limit,
            "offset": offset,
        }
        return await self.fetch_and_store(
            DataSource.CHEMBL,
            endpoint,
            params=params,
            request_id=f"chembl_activities_{chembl_id}_{offset}"
        )


class PubChemIngestion(RawIngestionService):
    """Specialized ingestion for PubChem API."""

    BASE_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

    async def fetch_compound(self, cid: int) -> Optional[str]:
        """Fetch compound by PubChem CID."""
        endpoint = f"{self.BASE_URL}/compound/cid/{cid}/JSON"
        return await self.fetch_and_store(
            DataSource.PUBCHEM,
            endpoint,
            request_id=f"pubchem_{cid}"
        )

    async def fetch_compound_by_name(self, name: str) -> Optional[str]:
        """Fetch compound by name."""
        endpoint = f"{self.BASE_URL}/compound/name/{name}/JSON"
        return await self.fetch_and_store(
            DataSource.PUBCHEM,
            endpoint,
            request_id=f"pubchem_name_{name}"
        )

    async def fetch_compound_properties(
        self,
        cid: int,
        properties: List[str] = None
    ) -> Optional[str]:
        """Fetch specific properties for a compound."""
        properties = properties or [
            "MolecularFormula", "MolecularWeight", "CanonicalSMILES",
            "InChI", "InChIKey", "IUPACName"
        ]
        props_str = ",".join(properties)
        endpoint = f"{self.BASE_URL}/compound/cid/{cid}/property/{props_str}/JSON"
        return await self.fetch_and_store(
            DataSource.PUBCHEM,
            endpoint,
            request_id=f"pubchem_props_{cid}"
        )


class UniProtIngestion(RawIngestionService):
    """Specialized ingestion for UniProt API."""

    BASE_URL = "https://rest.uniprot.org/uniprotkb"

    async def fetch_protein(self, uniprot_id: str) -> Optional[str]:
        """Fetch protein by UniProt ID."""
        endpoint = f"{self.BASE_URL}/{uniprot_id}.json"
        return await self.fetch_and_store(
            DataSource.UNIPROT,
            endpoint,
            request_id=f"uniprot_{uniprot_id}"
        )

    async def search_proteins(
        self,
        query: str,
        limit: int = 100
    ) -> Optional[str]:
        """Search proteins by query."""
        endpoint = f"{self.BASE_URL}/search"
        params = {
            "query": query,
            "format": "json",
            "size": limit,
        }
        return await self.fetch_and_store(
            DataSource.UNIPROT,
            endpoint,
            params=params,
            request_id=f"uniprot_search_{query[:50]}"
        )


class OpenAlexIngestion(RawIngestionService):
    """Specialized ingestion for OpenAlex API."""

    BASE_URL = "https://api.openalex.org"

    async def fetch_works(
        self,
        search: str,
        per_page: int = 100,
        page: int = 1
    ) -> Optional[str]:
        """Search works/publications."""
        endpoint = f"{self.BASE_URL}/works"
        params = {
            "search": search,
            "per_page": per_page,
            "page": page,
        }
        return await self.fetch_and_store(
            DataSource.OPENALEX,
            endpoint,
            params=params,
            request_id=f"openalex_works_{search[:30]}_{page}"
        )

    async def fetch_work_by_doi(self, doi: str) -> Optional[str]:
        """Fetch work by DOI."""
        endpoint = f"{self.BASE_URL}/works/doi:{doi}"
        return await self.fetch_and_store(
            DataSource.OPENALEX,
            endpoint,
            request_id=f"openalex_doi_{doi}"
        )


class SIDERIngestion(RawIngestionService):
    """
    Specialized ingestion for SIDER (Side Effect Resource) database.

    SIDER provides information on marketed medicines and their recorded adverse drug reactions.
    Data is available as TSV bulk downloads from sideeffects.embl.de.
    """

    # SIDER bulk download URLs (TSV format)
    BASE_URL = "http://sideeffects.embl.de/media/download"
    DRUG_NAMES_URL = f"{BASE_URL}/drug_names.tsv"
    SIDE_EFFECTS_URL = f"{BASE_URL}/meddra_all_se.tsv.gz"
    INDICATIONS_URL = f"{BASE_URL}/meddra_all_indications.tsv.gz"
    DRUG_ATCS_URL = f"{BASE_URL}/drug_atc.tsv"

    async def fetch_drug_names(self) -> Optional[str]:
        """Fetch SIDER drug names mapping (STITCH ID to drug name)."""
        return await self.fetch_and_store(
            DataSource.SIDER,
            self.DRUG_NAMES_URL,
            request_id="sider_drug_names"
        )

    async def fetch_side_effects(self) -> Optional[str]:
        """Fetch all side effects from SIDER (MedDRA terms)."""
        return await self.fetch_and_store(
            DataSource.SIDER,
            self.SIDE_EFFECTS_URL,
            request_id="sider_side_effects"
        )

    async def fetch_indications(self) -> Optional[str]:
        """Fetch all drug indications from SIDER."""
        return await self.fetch_and_store(
            DataSource.SIDER,
            self.INDICATIONS_URL,
            request_id="sider_indications"
        )

    async def fetch_atc_codes(self) -> Optional[str]:
        """Fetch ATC codes for drugs."""
        return await self.fetch_and_store(
            DataSource.SIDER,
            self.DRUG_ATCS_URL,
            request_id="sider_atc_codes"
        )


class BindingDBIngestion(RawIngestionService):
    """
    Specialized ingestion for BindingDB database.

    BindingDB is a public database of measured binding affinities,
    focusing on interactions between proteins and drug-like molecules.
    """

    BASE_URL = "https://www.bindingdb.org/axis2/services/BDBService"
    BULK_URL = "https://www.bindingdb.org/bind/downloads"

    async def fetch_by_ligand(
        self,
        smiles: str,
        similarity_threshold: float = 0.85
    ) -> Optional[str]:
        """Fetch binding data for a ligand by SMILES similarity."""
        endpoint = f"{self.BASE_URL}/getLigandsBySmiles"
        params = {
            "smiles": smiles,
            "cutoff": similarity_threshold,
            "response": "application/json"
        }
        return await self.fetch_and_store(
            DataSource.BINDINGDB,
            endpoint,
            params=params,
            request_id=f"bindingdb_smiles_{smiles[:20]}"
        )

    async def fetch_by_target(
        self,
        uniprot_id: str,
        limit: int = 100
    ) -> Optional[str]:
        """Fetch binding data for a target by UniProt ID."""
        endpoint = f"{self.BASE_URL}/getLigandsByUniprotId"
        params = {
            "uniprot": uniprot_id,
            "response": "application/json"
        }
        return await self.fetch_and_store(
            DataSource.BINDINGDB,
            endpoint,
            params=params,
            request_id=f"bindingdb_target_{uniprot_id}"
        )

    async def fetch_by_compound_name(self, name: str) -> Optional[str]:
        """Fetch binding data by compound name."""
        endpoint = f"{self.BASE_URL}/getLigandsByCompoundName"
        params = {
            "name": name,
            "response": "application/json"
        }
        return await self.fetch_and_store(
            DataSource.BINDINGDB,
            endpoint,
            params=params,
            request_id=f"bindingdb_name_{name[:30]}"
        )


class EMAIngestion(RawIngestionService):
    """
    Specialized ingestion for European Medicines Agency (EMA) data.

    EMA provides information on medicines authorized in the European Union
    via their public data portal.
    """

    BASE_URL = "https://www.ema.europa.eu/en/medicines/download-medicine-data"
    # EMA Open Data API
    API_URL = "https://api.ema.europa.eu/api"

    async def fetch_authorized_medicines(
        self,
        limit: int = 100,
        skip: int = 0
    ) -> Optional[str]:
        """Fetch list of authorized medicines from EMA."""
        endpoint = f"{self.API_URL}/medicines"
        params = {
            "$top": limit,
            "$skip": skip,
            "$format": "json"
        }
        return await self.fetch_and_store(
            DataSource.EMA,
            endpoint,
            params=params,
            request_id=f"ema_medicines_{skip}"
        )

    async def fetch_medicine_by_name(self, name: str) -> Optional[str]:
        """Fetch medicine details by name."""
        endpoint = f"{self.API_URL}/medicines"
        params = {
            "$filter": f"contains(name, '{name}')",
            "$format": "json"
        }
        return await self.fetch_and_store(
            DataSource.EMA,
            endpoint,
            params=params,
            request_id=f"ema_medicine_{name[:30]}"
        )

    async def fetch_epars(self, limit: int = 100, skip: int = 0) -> Optional[str]:
        """Fetch European Public Assessment Reports (EPARs)."""
        endpoint = f"{self.API_URL}/epars"
        params = {
            "$top": limit,
            "$skip": skip,
            "$format": "json"
        }
        return await self.fetch_and_store(
            DataSource.EMA,
            endpoint,
            params=params,
            request_id=f"ema_epars_{skip}"
        )

    async def fetch_safety_signals(
        self,
        limit: int = 100,
        skip: int = 0
    ) -> Optional[str]:
        """Fetch pharmacovigilance safety signals."""
        endpoint = f"{self.API_URL}/signals"
        params = {
            "$top": limit,
            "$skip": skip,
            "$format": "json"
        }
        return await self.fetch_and_store(
            DataSource.EMA,
            endpoint,
            params=params,
            request_id=f"ema_signals_{skip}"
        )


class OrangeBookIngestion(RawIngestionService):
    """
    Specialized ingestion for FDA Orange Book data.

    The Orange Book identifies drug products approved under the
    Federal Food, Drug, and Cosmetic Act, including patent and
    exclusivity information.
    """

    # Orange Book data files (CSV format)
    BASE_URL = "https://www.fda.gov/media"
    PRODUCTS_URL = "https://www.fda.gov/drugs/drug-approvals-and-databases/orange-book-data-files"

    # Direct CSV download links (updated periodically)
    PRODUCTS_CSV = "https://www.fda.gov/media/76860/download"  # products.txt
    PATENTS_CSV = "https://www.fda.gov/media/76861/download"   # patent.txt
    EXCLUSIVITY_CSV = "https://www.fda.gov/media/76862/download"  # exclusivity.txt

    async def fetch_products(self) -> Optional[str]:
        """Fetch Orange Book products data."""
        return await self.fetch_and_store(
            DataSource.ORANGE_BOOK,
            self.PRODUCTS_CSV,
            request_id="orange_book_products"
        )

    async def fetch_patents(self) -> Optional[str]:
        """Fetch Orange Book patent data."""
        return await self.fetch_and_store(
            DataSource.ORANGE_BOOK,
            self.PATENTS_CSV,
            request_id="orange_book_patents"
        )

    async def fetch_exclusivity(self) -> Optional[str]:
        """Fetch Orange Book exclusivity data."""
        return await self.fetch_and_store(
            DataSource.ORANGE_BOOK,
            self.EXCLUSIVITY_CSV,
            request_id="orange_book_exclusivity"
        )


class USPTOPatentsIngestion(RawIngestionService):
    """
    Specialized ingestion for USPTO PatentSearch API.

    PatentSearch provides a RESTful API for accessing patent data
    from the USPTO, useful for tracking pharmaceutical patents.
    """

    BASE_URL = "https://search.patentsview.org/api/v1/patent/"

    async def fetch_patents_by_assignee(
        self,
        assignee: str,
        limit: int = 100,
        offset: int = 0
    ) -> Optional[str]:
        """Fetch patents by assignee (company) name."""
        session = await self._get_session()

        query = {
            "q": {"assignees.assignee_organization": assignee},
            "f": [
                "patent_id", "patent_title", "patent_date",
                "patent_abstract", "assignees",
                "inventors", "application"
            ],
            "o": {"size": limit}
        }

        try:
            async with session.post(self.BASE_URL, json=query) as response:
                response_body = await response.json()
                response_headers = dict(response.headers)

                record = RawRecord(
                    request_id=f"uspto_assignee_{assignee[:20]}_{offset}",
                    api_endpoint=self.BASE_URL,
                    request_params=query,
                    response_status=response.status,
                    response_headers=response_headers,
                    response_body=response_body,
                    response_body_hash=self.compute_hash(response_body)
                )

                return await self._store_raw_record(DataSource.USPTO_PATENTS, record)
        except Exception as e:
            logger.error(f"USPTO patent fetch error: {e}")
            return None

    async def fetch_patents_by_cpc(
        self,
        cpc_code: str,
        limit: int = 100,
        offset: int = 0
    ) -> Optional[str]:
        """
        Fetch patents by CPC (Cooperative Patent Classification) code.

        Pharma-related CPC codes:
        - A61K: Preparations for medical, dental, or toiletry purposes
        - A61P: Specific therapeutic activity of chemical compounds
        - C07D: Heterocyclic compounds (many drug scaffolds)
        """
        session = await self._get_session()

        query = {
            "q": {"_begins": {"cpc_current.cpc_subgroup_id": cpc_code}},
            "f": [
                "patent_id", "patent_title", "patent_date",
                "patent_abstract", "assignees",
                "cpc_current", "application"
            ],
            "o": {"size": limit}
        }

        try:
            async with session.post(self.BASE_URL, json=query) as response:
                response_body = await response.json()
                response_headers = dict(response.headers)

                record = RawRecord(
                    request_id=f"uspto_cpc_{cpc_code}_{offset}",
                    api_endpoint=self.BASE_URL,
                    request_params=query,
                    response_status=response.status,
                    response_headers=response_headers,
                    response_body=response_body,
                    response_body_hash=self.compute_hash(response_body)
                )

                return await self._store_raw_record(DataSource.USPTO_PATENTS, record)
        except Exception as e:
            logger.error(f"USPTO patent fetch error: {e}")
            return None

    async def fetch_patent_by_number(self, patent_number: str) -> Optional[str]:
        """Fetch a specific patent by number."""
        session = await self._get_session()

        query = {
            "q": {"patent_id": patent_number},
            "f": [
                "patent_id", "patent_title", "patent_date",
                "patent_abstract", "assignees",
                "inventors", "cpc_current",
                "patent_num_claims", "application"
            ]
        }

        try:
            async with session.post(self.BASE_URL, json=query) as response:
                response_body = await response.json()
                response_headers = dict(response.headers)

                record = RawRecord(
                    request_id=f"uspto_patent_{patent_number}",
                    api_endpoint=self.BASE_URL,
                    request_params=query,
                    response_status=response.status,
                    response_headers=response_headers,
                    response_body=response_body,
                    response_body_hash=self.compute_hash(response_body)
                )

                return await self._store_raw_record(DataSource.USPTO_PATENTS, record)
        except Exception as e:
            logger.error(f"USPTO patent fetch error: {e}")
            return None


class WHOINNIngestion(RawIngestionService):
    """
    Specialized ingestion for WHO International Non-proprietary Names (INN).

    WHO INN provides the global standard for drug naming, including mappings
    from research codes (e.g., CP-690,550) to approved names (tofacitinib).

    This is critical for linking clinical trial interventions to approved drugs.
    """

    # PubChem has INN data via their REST API
    PUBCHEM_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

    async def search_by_research_code(self, research_code: str) -> Optional[str]:
        """
        Search for INN name by research code via PubChem synonyms.

        Args:
            research_code: Drug research code (e.g., CP-690,550, RAD001)

        Returns:
            Record ID if found
        """
        # PubChem stores synonyms including research codes
        endpoint = f"{self.PUBCHEM_URL}/compound/name/{research_code}/synonyms/JSON"
        return await self.fetch_and_store(
            DataSource.WHO_INN,
            endpoint,
            request_id=f"inn_code_{research_code}"
        )

    async def fetch_compound_synonyms(self, cid: int) -> Optional[str]:
        """Fetch all synonyms for a PubChem compound ID."""
        endpoint = f"{self.PUBCHEM_URL}/compound/cid/{cid}/synonyms/JSON"
        return await self.fetch_and_store(
            DataSource.WHO_INN,
            endpoint,
            request_id=f"pubchem_synonyms_{cid}"
        )


class KEGGDrugIngestion(RawIngestionService):
    """
    Specialized ingestion for KEGG DRUG database.

    KEGG DRUG contains approved drugs with research codes, targets,
    pathways, and drug-drug interactions.
    """

    BASE_URL = "https://rest.kegg.jp"

    async def fetch_drug_list(self) -> Optional[str]:
        """Fetch complete list of KEGG drugs."""
        endpoint = f"{self.BASE_URL}/list/drug"
        return await self.fetch_and_store(
            DataSource.KEGG_DRUG,
            endpoint,
            request_id="kegg_drug_list"
        )

    async def fetch_drug_by_id(self, kegg_id: str) -> Optional[str]:
        """Fetch detailed drug information by KEGG ID."""
        endpoint = f"{self.BASE_URL}/get/{kegg_id}"
        return await self.fetch_and_store(
            DataSource.KEGG_DRUG,
            endpoint,
            request_id=f"kegg_drug_{kegg_id}"
        )

    async def search_drug_by_name(self, drug_name: str) -> Optional[str]:
        """Search for drugs by name or synonym."""
        endpoint = f"{self.BASE_URL}/find/drug/{drug_name}"
        return await self.fetch_and_store(
            DataSource.KEGG_DRUG,
            endpoint,
            request_id=f"kegg_search_{drug_name[:30]}"
        )


class TTDIngestion(RawIngestionService):
    """
    Specialized ingestion for Therapeutic Target Database (TTD).

    TTD provides information on therapeutic targets and drugs,
    particularly valuable for biologics and targeted therapies.
    """

    BASE_URL = "http://db.idrblab.net/ttd"

    async def fetch_drug_info(self, drug_id: str) -> Optional[str]:
        """Fetch drug information by TTD ID."""
        endpoint = f"{self.BASE_URL}/data/drug/details/{drug_id}"
        return await self.fetch_and_store(
            DataSource.TTD,
            endpoint,
            request_id=f"ttd_drug_{drug_id}"
        )

    async def fetch_target_info(self, target_id: str) -> Optional[str]:
        """Fetch target information by TTD ID."""
        endpoint = f"{self.BASE_URL}/data/target/details/{target_id}"
        return await self.fetch_and_store(
            DataSource.TTD,
            endpoint,
            request_id=f"ttd_target_{target_id}"
        )


class FDADrugsIngestion(RawIngestionService):
    """
    Specialized ingestion for FDA Drugs@FDA database.

    Drugs@FDA contains all FDA-approved drug products including:
    - NDA/ANDA/BLA application details
    - Approval history and dates
    - Research codes and INN names
    """

    BASE_URL = "https://api.fda.gov/drug"

    async def fetch_approvals(
        self,
        limit: int = 100,
        skip: int = 0,
        since: Optional[str] = None
    ) -> Optional[str]:
        """
        Fetch drug approvals from FDA.

        Args:
            limit: Max results per request
            skip: Number to skip for pagination
            since: ISO date string for filtering recent approvals
        """
        endpoint = f"{self.BASE_URL}/drugsfda.json"
        params = {"limit": limit, "skip": skip}
        if since:
            params["search"] = f"submissions.submission_status_date:[{since} TO *]"

        return await self.fetch_and_store(
            DataSource.FDA_DRUGS,
            endpoint,
            params=params,
            request_id=f"fda_approvals_{skip}"
        )

    async def search_by_name(self, drug_name: str, limit: int = 100) -> Optional[str]:
        """Search FDA approved drugs by name."""
        endpoint = f"{self.BASE_URL}/drugsfda.json"
        params = {
            "search": f"products.brand_name:{drug_name}+products.active_ingredients.name:{drug_name}",
            "limit": limit
        }
        return await self.fetch_and_store(
            DataSource.FDA_DRUGS,
            endpoint,
            params=params,
            request_id=f"fda_search_{drug_name[:30]}"
        )


class IMGTIngestion(RawIngestionService):
    """
    Specialized ingestion for IMGT (ImMunoGeneTics) database.

    IMGT provides sequences and structures for antibodies and
    other immune-related proteins. Critical for biologic drug data.
    """

    # IMGT/3Dstructure-DB for antibody structures
    BASE_URL = "https://www.imgt.org/3Dstructure-DB"

    async def fetch_antibody_structures(self, antibody_name: str) -> Optional[str]:
        """Fetch antibody structure data by name."""
        endpoint = f"{self.BASE_URL}/cgi/details.cgi"
        params = {"pdbcode": antibody_name}
        return await self.fetch_and_store(
            DataSource.IMGT,
            endpoint,
            params=params,
            request_id=f"imgt_ab_{antibody_name[:30]}"
        )


class CDCVaccinesIngestion(RawIngestionService):
    """
    Specialized ingestion for CDC Vaccines database.

    Provides information on approved vaccines including:
    - Vaccine schedules
    - Manufacturer information
    - CVX codes (vaccine administered codes)
    """

    # CDC provides vaccine data via their data portal
    DATA_CDC_URL = "https://data.cdc.gov/api/views"

    async def fetch_vaccine_schedule(self) -> Optional[str]:
        """Fetch current vaccine schedule from CDC."""
        # CDC vaccine schedules dataset
        endpoint = f"{self.DATA_CDC_URL}/fhky-rtsk/rows.json"
        return await self.fetch_and_store(
            DataSource.CDC_VACCINES,
            endpoint,
            request_id="cdc_vaccine_schedule"
        )

    async def fetch_vaccine_products(self) -> Optional[str]:
        """Fetch vaccine product information."""
        # Use openFDA for vaccine product data
        endpoint = "https://api.fda.gov/drug/label.json"
        params = {
            "search": "openfda.product_type:VACCINE",
            "limit": 100
        }
        return await self.fetch_and_store(
            DataSource.CDC_VACCINES,
            endpoint,
            params=params,
            request_id="vaccine_products"
        )


class RxNormIngestion(RawIngestionService):
    """
    Specialized ingestion for RxNorm API.

    RxNorm provides standardized drug nomenclature:
    - Drug name normalization
    - RxCUI lookups
    - Ingredient identification
    - NDC to RxCUI mapping
    - Drug class lookups (ATC, VA, etc.)

    API Documentation: https://lhncbc.nlm.nih.gov/RxNav/APIs/
    """

    BASE_URL = "https://rxnav.nlm.nih.gov/REST"

    async def get_rxcui(self, name: str, search_type: int = 0) -> Optional[str]:
        """
        Get RxCUI for a drug name.

        Args:
            name: Drug name to search
            search_type: 0=exact, 1=normalized, 2=approximate
        """
        endpoint = f"{self.BASE_URL}/rxcui.json"
        params = {"name": name, "search": search_type}
        return await self.fetch_and_store(
            DataSource.RXNORM,
            endpoint,
            params=params,
            request_id=f"rxnorm_rxcui_{name[:30]}"
        )

    async def get_concept(self, rxcui: str) -> Optional[str]:
        """Fetch concept details by RxCUI."""
        endpoint = f"{self.BASE_URL}/rxcui/{rxcui}/properties.json"
        return await self.fetch_and_store(
            DataSource.RXNORM,
            endpoint,
            request_id=f"rxnorm_concept_{rxcui}"
        )

    async def get_ingredients(self, rxcui: str) -> Optional[str]:
        """Get ingredients for a drug by RxCUI."""
        endpoint = f"{self.BASE_URL}/rxcui/{rxcui}/related.json"
        params = {"tty": "IN+MIN+PIN"}
        return await self.fetch_and_store(
            DataSource.RXNORM,
            endpoint,
            params=params,
            request_id=f"rxnorm_ingredients_{rxcui}"
        )

    async def get_ndc_codes(self, rxcui: str) -> Optional[str]:
        """Get NDC codes for an RxCUI."""
        endpoint = f"{self.BASE_URL}/rxcui/{rxcui}/ndcs.json"
        return await self.fetch_and_store(
            DataSource.RXNORM,
            endpoint,
            request_id=f"rxnorm_ndc_{rxcui}"
        )

    async def get_drug_classes(self, rxcui: str) -> Optional[str]:
        """Get drug classes for an RxCUI from RxClass."""
        endpoint = f"{self.BASE_URL}/rxclass/class/byRxcui.json"
        params = {"rxcui": rxcui}
        return await self.fetch_and_store(
            DataSource.RXNORM,
            endpoint,
            params=params,
            request_id=f"rxnorm_classes_{rxcui}"
        )

    async def approximate_match(self, name: str, max_entries: int = 10) -> Optional[str]:
        """Find approximate matches for a drug name."""
        endpoint = f"{self.BASE_URL}/approximateTerm.json"
        params = {"term": name, "maxEntries": max_entries}
        return await self.fetch_and_store(
            DataSource.RXNORM,
            endpoint,
            params=params,
            request_id=f"rxnorm_approx_{name[:30]}"
        )


class TDCAdmetIngestion(RawIngestionService):
    """
    Specialized ingestion for TDC (Therapeutics Data Commons) ADMET datasets.

    TDC provides curated datasets for ADMET (Absorption, Distribution,
    Metabolism, Excretion, Toxicity) properties. Data is file-based.

    Website: https://tdcommons.ai
    """

    # TDC provides datasets via their Python package, but we can
    # also access pre-processed files
    ADMET_DATASETS = [
        "Caco2_Wang",
        "HIA_Hou",
        "Pgp_Broccatelli",
        "Bioavailability_Ma",
        "Lipophilicity_AstraZeneca",
        "Solubility_AqSolDB",
        "BBB_Martins",
        "PPBR_AZ",
        "VDss_Lombardo",
        "CYP2C9_Veith",
        "CYP2D6_Veith",
        "CYP3A4_Veith",
        "CYP2C19_Veith",
        "CYP1A2_Veith",
        "Half_Life_Obach",
        "Clearance_Hepatocyte_AZ",
        "hERG",
        "AMES",
        "DILI",
        "LD50_Zhu",
        "Carcinogens_Lagunin",
        "ClinTox",
    ]

    async def fetch_dataset(self, dataset_name: str) -> Optional[str]:
        """
        Fetch an ADMET dataset from TDC.

        Args:
            dataset_name: Name of the TDC dataset (e.g., 'Caco2_Wang')
        """
        # TDC datasets can be loaded via their package or from
        # Harvard Dataverse mirrors
        endpoint = f"https://dataverse.harvard.edu/api/access/datafile/{dataset_name}"
        return await self.fetch_and_store(
            DataSource.TDC_ADMET,
            endpoint,
            request_id=f"tdc_admet_{dataset_name}"
        )

    async def fetch_all_datasets(self) -> List[Optional[str]]:
        """Fetch all ADMET datasets."""
        results = []
        for dataset in self.ADMET_DATASETS:
            result = await self.fetch_dataset(dataset)
            results.append(result)
        return results


class PharmGKBIngestion(RawIngestionService):
    """
    Specialized ingestion for PharmGKB API.

    PharmGKB provides pharmacogenomics information:
    - Drug-gene associations
    - Clinical annotations
    - Dosing guidelines
    - Drug labels with PGx info
    - Variant annotations

    API Documentation: https://api.pharmgkb.org
    """

    BASE_URL = "https://api.pharmgkb.org/v1/data"

    async def fetch_drug(self, pharmgkb_id: str) -> Optional[str]:
        """Fetch drug by PharmGKB ID (e.g., PA449015)."""
        endpoint = f"{self.BASE_URL}/drug/{pharmgkb_id}"
        return await self.fetch_and_store(
            DataSource.PHARMGKB,
            endpoint,
            request_id=f"pharmgkb_drug_{pharmgkb_id}"
        )

    async def search_drugs(self, query: str, limit: int = 100) -> Optional[str]:
        """Search drugs by name."""
        endpoint = f"{self.BASE_URL}/drug"
        params = {"q": query, "limit": limit}
        return await self.fetch_and_store(
            DataSource.PHARMGKB,
            endpoint,
            params=params,
            request_id=f"pharmgkb_search_{query[:30]}"
        )

    async def fetch_clinical_annotations(
        self,
        drug_id: Optional[str] = None,
        gene_id: Optional[str] = None,
        limit: int = 100
    ) -> Optional[str]:
        """Fetch clinical annotations for drug-gene pairs."""
        endpoint = f"{self.BASE_URL}/clinicalAnnotation"
        params = {"limit": limit}
        if drug_id:
            params["drug.id"] = drug_id
        if gene_id:
            params["gene.id"] = gene_id

        return await self.fetch_and_store(
            DataSource.PHARMGKB,
            endpoint,
            params=params,
            request_id=f"pharmgkb_annotations_{drug_id or gene_id}"
        )

    async def fetch_dosing_guidelines(self, drug_id: str) -> Optional[str]:
        """Fetch dosing guidelines for a drug."""
        endpoint = f"{self.BASE_URL}/guidelineAnnotation"
        params = {"drug.id": drug_id}
        return await self.fetch_and_store(
            DataSource.PHARMGKB,
            endpoint,
            params=params,
            request_id=f"pharmgkb_dosing_{drug_id}"
        )

    async def fetch_variant_annotations(
        self,
        variant_id: str,
        limit: int = 100
    ) -> Optional[str]:
        """Fetch variant annotations."""
        endpoint = f"{self.BASE_URL}/variantAnnotation"
        params = {"variant.id": variant_id, "limit": limit}
        return await self.fetch_and_store(
            DataSource.PHARMGKB,
            endpoint,
            params=params,
            request_id=f"pharmgkb_variant_{variant_id}"
        )

    async def fetch_pathways(self, drug_id: str) -> Optional[str]:
        """Fetch pharmacokinetic/pharmacodynamic pathways for a drug."""
        endpoint = f"{self.BASE_URL}/pathway"
        params = {"drug.id": drug_id}
        return await self.fetch_and_store(
            DataSource.PHARMGKB,
            endpoint,
            params=params,
            request_id=f"pharmgkb_pathways_{drug_id}"
        )


class WebSearchIngestion(RawIngestionService):
    """
    Specialized ingestion for web search APIs.

    Provides integration with search engines for:
    - Drug-related news
    - Publication discovery
    - Regulatory announcements

    Supports multiple backends (configurable).
    """

    # Default to a news/search aggregator
    BASE_URL = "https://newsapi.org/v2"

    async def search_news(
        self,
        query: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        language: str = "en",
        page_size: int = 100
    ) -> Optional[str]:
        """
        Search for drug-related news.

        Args:
            query: Search query (e.g., drug name)
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            language: Language code
            page_size: Results per page
        """
        endpoint = f"{self.BASE_URL}/everything"
        params = {
            "q": query,
            "language": language,
            "pageSize": page_size,
            "sortBy": "publishedAt"
        }
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date

        return await self.fetch_and_store(
            DataSource.WEBSEARCH,
            endpoint,
            params=params,
            request_id=f"websearch_news_{query[:30]}"
        )

    async def search_google_scholar(
        self,
        query: str,
        year_start: Optional[int] = None,
        year_end: Optional[int] = None
    ) -> Optional[str]:
        """
        Search Google Scholar via SerpAPI or similar.

        Note: Requires API key configuration.
        """
        # Using SerpAPI for Google Scholar
        endpoint = "https://serpapi.com/search"
        params = {
            "engine": "google_scholar",
            "q": query,
            "hl": "en"
        }
        if year_start:
            params["as_ylo"] = year_start
        if year_end:
            params["as_yhi"] = year_end

        return await self.fetch_and_store(
            DataSource.WEBSEARCH,
            endpoint,
            params=params,
            request_id=f"websearch_scholar_{query[:30]}"
        )


class DailyMedIngestion(RawIngestionService):
    """
    Specialized ingestion for DailyMed API.

    DailyMed provides FDA-approved drug labeling:
    - Structured Product Labels (SPL)
    - Package inserts
    - Medication guides
    - Labeling changes

    API: https://dailymed.nlm.nih.gov/dailymed/services
    """

    BASE_URL = "https://dailymed.nlm.nih.gov/dailymed/services/v2"

    async def search_drugs(
        self,
        name: str,
        page: int = 1,
        pagesize: int = 100
    ) -> Optional[str]:
        """Search for drugs by name."""
        endpoint = f"{self.BASE_URL}/spls.json"
        params = {
            "drug_name": name,
            "page": page,
            "pagesize": pagesize
        }
        return await self.fetch_and_store(
            DataSource.DAILYMED,
            endpoint,
            params=params,
            request_id=f"dailymed_search_{name[:30]}"
        )

    async def fetch_spl(self, set_id: str) -> Optional[str]:
        """Fetch SPL by Set ID."""
        endpoint = f"{self.BASE_URL}/spls/{set_id}.json"
        return await self.fetch_and_store(
            DataSource.DAILYMED,
            endpoint,
            request_id=f"dailymed_spl_{set_id}"
        )

    async def fetch_ndc(self, ndc: str) -> Optional[str]:
        """Fetch drug info by NDC code."""
        endpoint = f"{self.BASE_URL}/ndcs/{ndc}.json"
        return await self.fetch_and_store(
            DataSource.DAILYMED,
            endpoint,
            request_id=f"dailymed_ndc_{ndc}"
        )

    async def fetch_labeling_changes(
        self,
        since_date: Optional[str] = None,
        page: int = 1,
        pagesize: int = 100
    ) -> Optional[str]:
        """Fetch recent labeling changes."""
        endpoint = f"{self.BASE_URL}/labeling_changes.json"
        params = {
            "page": page,
            "pagesize": pagesize
        }
        if since_date:
            params["published_date"] = since_date

        return await self.fetch_and_store(
            DataSource.DAILYMED,
            endpoint,
            params=params,
            request_id=f"dailymed_changes_{page}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Assessment-enrichment ingestion classes (xenon integration)
# ═══════════════════════════════════════════════════════════════════════════

class ReactomeIngestion(RawIngestionService):
    """Ingestion for Reactome pathway database."""

    BASE_URL = "https://reactome.org/ContentService"

    async def search_pathways(self, query: str, species: str = "Homo sapiens") -> Optional[str]:
        endpoint = f"{self.BASE_URL}/search/query"
        params = {"query": query, "types": "Pathway", "species": species, "cluster": "true"}
        return await self.fetch_and_store(
            DataSource.REACTOME, endpoint, params=params,
            request_id=f"reactome_search_{query[:40]}"
        )

    async def fetch_pathway(self, stable_id: str) -> Optional[str]:
        endpoint = f"{self.BASE_URL}/data/query/{stable_id}"
        return await self.fetch_and_store(
            DataSource.REACTOME, endpoint,
            request_id=f"reactome_pathway_{stable_id}"
        )


class NICEHTAIngestion(RawIngestionService):
    """Ingestion for NICE Technology Appraisals.

    Fetches both the search results AND individual guidance pages to capture
    decision status, dates, and ICER values.
    """

    BASE_URL = "https://www.nice.org.uk"
    API_URL = "https://api.nice.org.uk/services/guidance/published"

    async def search_guidance(self, drug_name: str, limit: int = 20) -> Optional[str]:
        # Primary: Use NICE published guidance API (returns structured JSON with decision data)
        endpoint = f"{self.API_URL}"
        params = {"GuidanceTitle": drug_name, "PageSize": limit}
        result = await self.fetch_and_store(
            DataSource.NICE_HTA, endpoint, params=params,
            request_id=f"nice_api_{drug_name[:30]}"
        )
        if result:
            return result

        # Fallback: Search page (HTML, less structured)
        endpoint = f"{self.BASE_URL}/search"
        params = {"q": drug_name, "ps": limit, "sp": "on"}
        return await self.fetch_and_store(
            DataSource.NICE_HTA, endpoint, params=params,
            request_id=f"nice_search_{drug_name[:30]}"
        )

    async def fetch_guidance_detail(self, guidance_id: str) -> Optional[str]:
        """Fetch individual guidance page for decision/date/ICER extraction."""
        endpoint = f"{self.BASE_URL}/guidance/{guidance_id}"
        return await self.fetch_and_store(
            DataSource.NICE_HTA, endpoint,
            request_id=f"nice_detail_{guidance_id}"
        )


class CMSOpenPaymentsIngestion(RawIngestionService):
    """Ingestion for CMS Open Payments physician payment data."""

    BASE_URL = "https://openpaymentsdata.cms.gov/api/1/datastore/query"

    async def fetch_payments(self, manufacturer_name: str, year: int = 2024, limit: int = 1000) -> Optional[str]:
        dataset_ids = {2024: "e6b17c6a-2534-4207-a4a1-6746a14911ff", 2023: "fb3a65aa-c901-4a38-a813-b04b00dfa2a9"}
        dataset_id = dataset_ids.get(year)
        if not dataset_id:
            return None
        endpoint = f"{self.BASE_URL}/{dataset_id}/0"
        params = {
            "conditions[0][property]": "applicable_manufacturer_or_applicable_gpo_making_payment_name",
            "conditions[0][value]": manufacturer_name,
            "limit": limit,
            "sort": "total_amount_of_payment_usdollars",
            "sort_order": "desc",
        }
        return await self.fetch_and_store(
            DataSource.CMS_OPEN_PAYMENTS, endpoint, params=params,
            request_id=f"cms_openpay_{manufacturer_name[:20]}_{year}"
        )


class CMSMedicareIngestion(RawIngestionService):
    """Ingestion for CMS Medicare Part B drug spending.

    Dataset ID (updated 2026-03): 76a714ad-3a2c-43ac-b76d-9dadf8f7d890
    This dataset contains ALL Part B drugs (~734 rows) with spending data 2019-2023.
    Note: CMS periodically changes dataset UUIDs. If 404, check data.cms.gov/data.json.
    """

    PART_B_DATASET = "76a714ad-3a2c-43ac-b76d-9dadf8f7d890"
    BASE = "https://data.cms.gov/data-api/v1/dataset"

    async def fetch_part_b_spending(self, drug_name: str) -> Optional[str]:
        # Dataset returns ALL drugs in one response (~734 rows). Store full response,
        # bronze transformation will filter by drug name.
        endpoint = f"{self.BASE}/{self.PART_B_DATASET}/data"
        params = {"size": 5000}
        return await self.fetch_and_store(
            DataSource.CMS_MEDICARE, endpoint, params=params,
            request_id=f"cms_partb_all_{drug_name[:20]}"
        )


class NIHReporterIngestion(RawIngestionService):
    """Ingestion for NIH RePORTER research grants."""

    BASE_URL = "https://api.reporter.nih.gov/v2/projects/search"

    async def search_grants(self, drug_name: str, limit: int = 50) -> Optional[str]:
        endpoint = self.BASE_URL
        # NIH Reporter uses POST with JSON body
        body = {
            "criteria": {
                "advanced_text_search": {
                    "search_field": "terms",
                    "search_text": drug_name,
                }
            },
            "limit": limit,
            "offset": 0,
        }
        return await self.fetch_and_store(
            DataSource.NIH_REPORTER, endpoint, params=body,
            request_id=f"nih_grants_{drug_name[:30]}"
        )


class NPIRegistryIngestion(RawIngestionService):
    """Ingestion for NPI Registry physician directory."""

    BASE_URL = "https://npiregistry.cms.hhs.gov/api"

    async def search_providers(self, specialty: str, state: str = None, limit: int = 200) -> Optional[str]:
        endpoint = self.BASE_URL
        params = {
            "version": "2.1",
            "enumeration_type": "NPI-1",
            "taxonomy_description": specialty,
            "limit": limit,
        }
        if state:
            params["state"] = state
        return await self.fetch_and_store(
            DataSource.NPI_REGISTRY, endpoint, params=params,
            request_id=f"npi_{specialty[:20]}_{state or 'all'}"
        )


class EuropePMCIngestion(RawIngestionService):
    """Ingestion for EuropePMC full-text literature."""

    BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest"

    async def search_publications(self, query: str, page_size: int = 100) -> Optional[str]:
        endpoint = f"{self.BASE_URL}/search"
        params = {"query": query, "resultType": "core", "pageSize": page_size, "format": "json"}
        return await self.fetch_and_store(
            DataSource.EUROPEPMC, endpoint, params=params,
            request_id=f"europepmc_{query[:40]}"
        )


class FDADrugsfdaIngestion(RawIngestionService):
    """Ingestion for FDA Drugs@FDA approval history."""

    BASE_URL = "https://api.fda.gov/drug/drugsfda.json"

    async def fetch_approvals(self, brand_name: str = None, generic_name: str = None) -> Optional[str]:
        if brand_name:
            search = f'products.brand_name:"{brand_name}"'
        elif generic_name:
            search = f'openfda.generic_name:"{generic_name}"'
        else:
            return None
        endpoint = self.BASE_URL
        params = {"search": search, "limit": 100}
        return await self.fetch_and_store(
            DataSource.FDA_DRUGSFDA, endpoint, params=params,
            request_id=f"fda_drugsfda_{(brand_name or generic_name)[:30]}"
        )
