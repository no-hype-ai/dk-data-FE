"""
External Resolver Service

Resolves molecule identifiers via external APIs (PubChem, ChEMBL, UniChem).
Used by IdentifierResolver for cross-reference resolution when local lookup fails.

Part of DK Molecule Data Platform (012-dk-data-platform)
"""

import asyncio
import aiohttp
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class ExternalResolutionResult:
    """Result from external API resolution."""
    success: bool
    source: str
    inchi_key: Optional[str] = None
    inchi: Optional[str] = None
    smiles: Optional[str] = None
    name: Optional[str] = None
    molecular_formula: Optional[str] = None
    molecular_weight: Optional[float] = None
    identifiers: Dict[str, str] = None
    raw_response: Dict[str, Any] = None
    error: Optional[str] = None

    def __post_init__(self):
        if self.identifiers is None:
            self.identifiers = {}


class PubChemResolver:
    """Resolver for PubChem API."""

    BASE_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        self._session = session
        self._owns_session = session is None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._session

    async def close(self):
        if self._owns_session and self._session:
            await self._session.close()
            self._session = None

    async def resolve_by_name(self, name: str) -> ExternalResolutionResult:
        """Resolve compound by name via PubChem."""
        session = await self._get_session()
        url = f"{self.BASE_URL}/compound/name/{name}/JSON"

        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_compound_response(data, 'name')
                elif response.status == 404:
                    return ExternalResolutionResult(
                        success=False,
                        source='pubchem',
                        error='Compound not found'
                    )
                else:
                    return ExternalResolutionResult(
                        success=False,
                        source='pubchem',
                        error=f'HTTP {response.status}'
                    )
        except asyncio.TimeoutError:
            return ExternalResolutionResult(
                success=False,
                source='pubchem',
                error='Request timeout'
            )
        except Exception as e:
            logger.error(f"PubChem name resolution error: {e}")
            return ExternalResolutionResult(
                success=False,
                source='pubchem',
                error=str(e)
            )

    async def resolve_by_cid(self, cid: int) -> ExternalResolutionResult:
        """Resolve compound by CID via PubChem."""
        session = await self._get_session()
        url = f"{self.BASE_URL}/compound/cid/{cid}/JSON"

        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_compound_response(data, 'cid')
                elif response.status == 404:
                    return ExternalResolutionResult(
                        success=False,
                        source='pubchem',
                        error='Compound not found'
                    )
                else:
                    return ExternalResolutionResult(
                        success=False,
                        source='pubchem',
                        error=f'HTTP {response.status}'
                    )
        except asyncio.TimeoutError:
            return ExternalResolutionResult(
                success=False,
                source='pubchem',
                error='Request timeout'
            )
        except Exception as e:
            logger.error(f"PubChem CID resolution error: {e}")
            return ExternalResolutionResult(
                success=False,
                source='pubchem',
                error=str(e)
            )

    async def resolve_by_smiles(self, smiles: str) -> ExternalResolutionResult:
        """Resolve compound by SMILES via PubChem."""
        session = await self._get_session()
        # Use POST for SMILES to handle special characters
        url = f"{self.BASE_URL}/compound/smiles/JSON"

        try:
            async with session.post(url, data={'smiles': smiles}) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_compound_response(data, 'smiles')
                elif response.status == 404:
                    return ExternalResolutionResult(
                        success=False,
                        source='pubchem',
                        error='Compound not found'
                    )
                else:
                    return ExternalResolutionResult(
                        success=False,
                        source='pubchem',
                        error=f'HTTP {response.status}'
                    )
        except Exception as e:
            logger.error(f"PubChem SMILES resolution error: {e}")
            return ExternalResolutionResult(
                success=False,
                source='pubchem',
                error=str(e)
            )

    async def resolve_by_inchi_key(self, inchi_key: str) -> ExternalResolutionResult:
        """Resolve compound by InChI Key via PubChem."""
        session = await self._get_session()
        url = f"{self.BASE_URL}/compound/inchikey/{inchi_key}/JSON"

        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_compound_response(data, 'inchikey')
                elif response.status == 404:
                    return ExternalResolutionResult(
                        success=False,
                        source='pubchem',
                        error='Compound not found'
                    )
                else:
                    return ExternalResolutionResult(
                        success=False,
                        source='pubchem',
                        error=f'HTTP {response.status}'
                    )
        except Exception as e:
            logger.error(f"PubChem InChI Key resolution error: {e}")
            return ExternalResolutionResult(
                success=False,
                source='pubchem',
                error=str(e)
            )

    def _parse_compound_response(self, data: Dict, query_type: str) -> ExternalResolutionResult:
        """Parse PubChem compound response."""
        try:
            compounds = data.get('PC_Compounds', [])
            if not compounds:
                return ExternalResolutionResult(
                    success=False,
                    source='pubchem',
                    error='No compounds in response'
                )

            compound = compounds[0]
            props = {}

            # Extract properties
            for prop in compound.get('props', []):
                label = prop.get('urn', {}).get('label', '')
                name = prop.get('urn', {}).get('name', '')
                value = prop.get('value', {})

                if label == 'InChIKey':
                    props['inchi_key'] = value.get('sval')
                elif label == 'InChI':
                    props['inchi'] = value.get('sval')
                elif label == 'SMILES' and name == 'Canonical':
                    props['smiles'] = value.get('sval')
                elif label == 'Molecular Formula':
                    props['molecular_formula'] = value.get('sval')
                elif label == 'Molecular Weight':
                    props['molecular_weight'] = value.get('fval')
                elif label == 'IUPAC Name' and name == 'Preferred':
                    props['name'] = value.get('sval')

            cid = compound.get('id', {}).get('id', {}).get('cid')

            identifiers = {'pubchem_cid': str(cid)} if cid else {}
            if props.get('inchi_key'):
                identifiers['inchi_key'] = props['inchi_key']

            return ExternalResolutionResult(
                success=True,
                source='pubchem',
                inchi_key=props.get('inchi_key'),
                inchi=props.get('inchi'),
                smiles=props.get('smiles'),
                name=props.get('name'),
                molecular_formula=props.get('molecular_formula'),
                molecular_weight=props.get('molecular_weight'),
                identifiers=identifiers,
                raw_response=data
            )

        except Exception as e:
            logger.error(f"Error parsing PubChem response: {e}")
            return ExternalResolutionResult(
                success=False,
                source='pubchem',
                error=f'Parse error: {str(e)}'
            )

    async def resolve(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Generic resolve method for identifier_resolver integration."""
        # Try name first, then CID if numeric
        result = await self.resolve_by_name(identifier)
        if result.success:
            return {
                'inchi_key': result.inchi_key,
                'name': result.name,
                'smiles': result.smiles,
                'identifiers': result.identifiers
            }

        # If identifier is numeric, try as CID
        if identifier.isdigit():
            result = await self.resolve_by_cid(int(identifier))
            if result.success:
                return {
                    'inchi_key': result.inchi_key,
                    'name': result.name,
                    'smiles': result.smiles,
                    'identifiers': result.identifiers
                }

        return None


class ChEMBLResolver:
    """Resolver for ChEMBL API."""

    BASE_URL = "https://www.ebi.ac.uk/chembl/api/data"

    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        self._session = session
        self._owns_session = session is None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={'Accept': 'application/json'}
            )
        return self._session

    async def close(self):
        if self._owns_session and self._session:
            await self._session.close()
            self._session = None

    async def resolve_by_chembl_id(self, chembl_id: str) -> ExternalResolutionResult:
        """Resolve molecule by ChEMBL ID."""
        session = await self._get_session()
        # Normalize ChEMBL ID
        if not chembl_id.upper().startswith('CHEMBL'):
            chembl_id = f'CHEMBL{chembl_id}'
        chembl_id = chembl_id.upper()

        url = f"{self.BASE_URL}/molecule/{chembl_id}.json"

        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_molecule_response(data)
                elif response.status == 404:
                    return ExternalResolutionResult(
                        success=False,
                        source='chembl',
                        error='Molecule not found'
                    )
                else:
                    return ExternalResolutionResult(
                        success=False,
                        source='chembl',
                        error=f'HTTP {response.status}'
                    )
        except asyncio.TimeoutError:
            return ExternalResolutionResult(
                success=False,
                source='chembl',
                error='Request timeout'
            )
        except Exception as e:
            logger.error(f"ChEMBL ID resolution error: {e}")
            return ExternalResolutionResult(
                success=False,
                source='chembl',
                error=str(e)
            )

    async def search_by_name(self, name: str, limit: int = 5) -> List[ExternalResolutionResult]:
        """Search molecules by name via ChEMBL."""
        session = await self._get_session()
        url = f"{self.BASE_URL}/molecule/search.json"
        params = {'q': name, 'limit': limit}

        try:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    molecules = data.get('molecules', [])
                    return [self._parse_molecule_response(mol) for mol in molecules]
                else:
                    return []
        except Exception as e:
            logger.error(f"ChEMBL name search error: {e}")
            return []

    async def resolve_by_inchi_key(self, inchi_key: str) -> ExternalResolutionResult:
        """Resolve molecule by InChI Key via ChEMBL."""
        session = await self._get_session()
        url = f"{self.BASE_URL}/molecule.json"
        params = {'molecule_structures__standard_inchi_key': inchi_key}

        try:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    molecules = data.get('molecules', [])
                    if molecules:
                        return self._parse_molecule_response(molecules[0])
                    return ExternalResolutionResult(
                        success=False,
                        source='chembl',
                        error='Molecule not found'
                    )
                else:
                    return ExternalResolutionResult(
                        success=False,
                        source='chembl',
                        error=f'HTTP {response.status}'
                    )
        except Exception as e:
            logger.error(f"ChEMBL InChI Key resolution error: {e}")
            return ExternalResolutionResult(
                success=False,
                source='chembl',
                error=str(e)
            )

    def _parse_molecule_response(self, data: Dict) -> ExternalResolutionResult:
        """Parse ChEMBL molecule response."""
        try:
            structures = data.get('molecule_structures') or {}
            properties = data.get('molecule_properties') or {}

            chembl_id = data.get('molecule_chembl_id')
            identifiers = {}
            if chembl_id:
                identifiers['chembl_id'] = chembl_id

            inchi_key = structures.get('standard_inchi_key')
            if inchi_key:
                identifiers['inchi_key'] = inchi_key

            return ExternalResolutionResult(
                success=True,
                source='chembl',
                inchi_key=inchi_key,
                inchi=structures.get('standard_inchi'),
                smiles=structures.get('canonical_smiles'),
                name=data.get('pref_name'),
                molecular_formula=properties.get('full_molformula'),
                molecular_weight=float(properties['full_mwt']) if properties.get('full_mwt') else None,
                identifiers=identifiers,
                raw_response=data
            )
        except Exception as e:
            logger.error(f"Error parsing ChEMBL response: {e}")
            return ExternalResolutionResult(
                success=False,
                source='chembl',
                error=f'Parse error: {str(e)}'
            )

    async def resolve(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Generic resolve method for identifier_resolver integration."""
        # Try as ChEMBL ID first
        if identifier.upper().startswith('CHEMBL') or identifier.isdigit():
            result = await self.resolve_by_chembl_id(identifier)
            if result.success:
                return {
                    'inchi_key': result.inchi_key,
                    'name': result.name,
                    'smiles': result.smiles,
                    'identifiers': result.identifiers
                }

        # Search by name
        results = await self.search_by_name(identifier, limit=1)
        if results and results[0].success:
            result = results[0]
            return {
                'inchi_key': result.inchi_key,
                'name': result.name,
                'smiles': result.smiles,
                'identifiers': result.identifiers
            }

        return None


class UniChemResolver:
    """Resolver for UniChem API (cross-reference service)."""

    BASE_URL = "https://www.ebi.ac.uk/unichem/rest"

    # UniChem source IDs - complete list for all 16 data sources
    SOURCE_IDS = {
        'chembl': 1,
        'drugbank': 2,
        'pdb': 3,
        'iuphar': 4,
        'pubchem_dotf': 5,
        'kegg': 6,
        'chebi': 7,
        'nih_ncc': 8,
        'zinc': 9,
        'emolecules': 10,
        'ibm': 11,
        'atlas': 12,
        'lincs': 15,
        'selleck': 17,
        'pharmgkb': 18,
        'hmdb': 20,
        'pubchem': 22,
        'pubchem_sid': 14,
        'bindingdb': 31,
        'surechembl': 29,
        'carotenoid': 30,
    }

    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        self._session = session
        self._owns_session = session is None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._session

    async def close(self):
        if self._owns_session and self._session:
            await self._session.close()
            self._session = None

    async def get_cross_references(
        self,
        inchi_key: str
    ) -> Dict[str, List[str]]:
        """Get cross-references for an InChI Key from all sources."""
        session = await self._get_session()
        url = f"{self.BASE_URL}/inchikey/{inchi_key}"

        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_cross_refs(data)
                else:
                    return {}
        except Exception as e:
            logger.error(f"UniChem cross-reference error: {e}")
            return {}

    async def convert_id(
        self,
        src_id: str,
        src_source: str,
        target_source: str
    ) -> List[str]:
        """Convert identifier from one source to another."""
        session = await self._get_session()

        src_source_id = self.SOURCE_IDS.get(src_source.lower())
        target_source_id = self.SOURCE_IDS.get(target_source.lower())

        if not src_source_id or not target_source_id:
            return []

        url = f"{self.BASE_URL}/src_compound_id/{src_id}/{src_source_id}/{target_source_id}"

        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return [item.get('src_compound_id') for item in data if item.get('src_compound_id')]
                else:
                    return []
        except Exception as e:
            logger.error(f"UniChem ID conversion error: {e}")
            return []

    def _parse_cross_refs(self, data: List[Dict]) -> Dict[str, List[str]]:
        """Parse UniChem cross-reference response."""
        result = {}
        source_names = {v: k for k, v in self.SOURCE_IDS.items()}

        for item in data:
            src_id = item.get('src_id')
            compound_id = item.get('src_compound_id')

            if src_id and compound_id:
                source_name = source_names.get(int(src_id), f'source_{src_id}')
                if source_name not in result:
                    result[source_name] = []
                result[source_name].append(compound_id)

        return result


class ExternalResolverService:
    """
    Unified external resolver service.

    Aggregates multiple external API resolvers for comprehensive
    molecule cross-referencing across all 16 data sources.

    Supported resolvers:
    - PubChem (pubchem_cid, name, inchi_key, smiles)
    - ChEMBL (chembl_id, name, inchi_key)
    - UniChem (cross-reference between sources)
    - RxNorm (rxcui, name)
    - PharmGKB (pharmgkb_id, name)
    - KEGG (kegg_id, name)
    - BindingDB (bindingdb_id)
    """

    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        """Initialize the external resolver service with all resolvers."""
        self.pubchem = PubChemResolver(session)
        self.chembl = ChEMBLResolver(session)
        self.unichem = UniChemResolver(session)
        self.rxnorm = RxNormResolver(session)
        self.pharmgkb = PharmGKBResolver(session)
        self.kegg = KEGGResolver(session)
        self.bindingdb = BindingDBResolver(session)
        self._session = session

    async def close(self):
        """Close all resolver sessions."""
        await self.pubchem.close()
        await self.chembl.close()
        await self.unichem.close()
        await self.rxnorm.close()
        await self.pharmgkb.close()
        await self.kegg.close()
        await self.bindingdb.close()

    async def resolve_all(
        self,
        identifier: str,
        identifier_type: Optional[str] = None
    ) -> Dict[str, ExternalResolutionResult]:
        """
        Resolve identifier across all external sources.

        Args:
            identifier: The identifier to resolve
            identifier_type: Optional type hint (name, chembl_id, pubchem_cid, inchi_key,
                           rxcui, pharmgkb_id, kegg_id, bindingdb_id)

        Returns:
            Dict mapping source name to resolution result
        """
        results = {}
        tasks = []

        # PubChem resolution
        if identifier_type in [None, 'name', 'pubchem_cid', 'inchi_key', 'smiles']:
            if identifier_type == 'pubchem_cid' and identifier.isdigit():
                tasks.append(('pubchem', self.pubchem.resolve_by_cid(int(identifier))))
            elif identifier_type == 'inchi_key':
                tasks.append(('pubchem', self.pubchem.resolve_by_inchi_key(identifier)))
            elif identifier_type == 'smiles':
                tasks.append(('pubchem', self.pubchem.resolve_by_smiles(identifier)))
            else:
                tasks.append(('pubchem', self.pubchem.resolve_by_name(identifier)))

        # ChEMBL resolution
        if identifier_type in [None, 'name', 'chembl_id', 'inchi_key']:
            if identifier_type == 'chembl_id' or identifier.upper().startswith('CHEMBL'):
                tasks.append(('chembl', self.chembl.resolve_by_chembl_id(identifier)))
            elif identifier_type == 'inchi_key':
                tasks.append(('chembl', self.chembl.resolve_by_inchi_key(identifier)))
            else:
                async def chembl_name_search():
                    search_results = await self.chembl.search_by_name(identifier, limit=1)
                    return search_results[0] if search_results else ExternalResolutionResult(
                        success=False, source='chembl', error='No results'
                    )
                tasks.append(('chembl', chembl_name_search()))

        # RxNorm resolution
        if identifier_type in [None, 'name', 'rxcui']:
            if identifier_type == 'rxcui' or (identifier.isdigit() and len(identifier) <= 8):
                tasks.append(('rxnorm', self.rxnorm.resolve_by_rxcui(identifier)))
            elif identifier_type == 'name':
                tasks.append(('rxnorm', self.rxnorm.resolve_by_name(identifier)))

        # PharmGKB resolution
        if identifier_type in [None, 'name', 'pharmgkb_id']:
            if identifier_type == 'pharmgkb_id' or identifier.upper().startswith('PA'):
                tasks.append(('pharmgkb', self.pharmgkb.resolve_by_pharmgkb_id(identifier)))
            elif identifier_type == 'name':
                async def pharmgkb_name_search():
                    search_results = await self.pharmgkb.search_by_name(identifier, limit=1)
                    return search_results[0] if search_results else ExternalResolutionResult(
                        success=False, source='pharmgkb', error='No results'
                    )
                tasks.append(('pharmgkb', pharmgkb_name_search()))

        # KEGG resolution
        if identifier_type in [None, 'name', 'kegg_id']:
            if identifier_type == 'kegg_id' or (identifier.upper().startswith('D') and identifier[1:].isdigit()):
                tasks.append(('kegg', self.kegg.resolve_by_kegg_id(identifier)))
            elif identifier_type == 'name':
                async def kegg_name_search():
                    search_results = await self.kegg.search_by_name(identifier)
                    return search_results[0] if search_results else ExternalResolutionResult(
                        success=False, source='kegg', error='No results'
                    )
                tasks.append(('kegg', kegg_name_search()))

        # BindingDB resolution
        if identifier_type in ['bindingdb_id']:
            if identifier_type == 'bindingdb_id' or identifier.upper().startswith('BDBM'):
                tasks.append(('bindingdb', self.bindingdb.resolve_by_bindingdb_id(identifier)))

        # Execute all tasks in parallel
        for source, task in tasks:
            try:
                result = await task
                results[source] = result
            except Exception as e:
                logger.error(f"Error resolving via {source}: {e}")
                results[source] = ExternalResolutionResult(
                    success=False,
                    source=source,
                    error=str(e)
                )

        return results

    async def get_best_resolution(
        self,
        identifier: str,
        identifier_type: Optional[str] = None
    ) -> Optional[ExternalResolutionResult]:
        """
        Get the best resolution result from all sources.

        Prioritizes: ChEMBL > PubChem based on data quality.

        Args:
            identifier: The identifier to resolve
            identifier_type: Optional type hint

        Returns:
            Best resolution result or None if all failed
        """
        results = await self.resolve_all(identifier, identifier_type)

        # Priority order
        priority = ['chembl', 'pubchem']

        for source in priority:
            if source in results and results[source].success:
                return results[source]

        # Return any successful result
        for result in results.values():
            if result.success:
                return result

        return None

    async def get_cross_references(self, inchi_key: str) -> Dict[str, List[str]]:
        """Get cross-references for an InChI Key via UniChem."""
        return await self.unichem.get_cross_references(inchi_key)

    async def enrich_identifiers(
        self,
        inchi_key: str
    ) -> Dict[str, Any]:
        """
        Enrich molecule with all available identifiers from external sources.

        Args:
            inchi_key: The InChI Key to enrich

        Returns:
            Dict with all discovered identifiers and metadata
        """
        enriched = {
            'inchi_key': inchi_key,
            'identifiers': {},
            'names': [],
            'sources_queried': [],
            'timestamp': datetime.utcnow().isoformat()
        }

        # Get UniChem cross-references
        cross_refs = await self.get_cross_references(inchi_key)
        for source, ids in cross_refs.items():
            enriched['identifiers'][source] = ids
            enriched['sources_queried'].append(f'unichem_{source}')

        # Get detailed info from PubChem
        pubchem_result = await self.pubchem.resolve_by_inchi_key(inchi_key)
        if pubchem_result.success:
            enriched['sources_queried'].append('pubchem')
            if pubchem_result.name:
                enriched['names'].append({
                    'name': pubchem_result.name,
                    'source': 'pubchem',
                    'type': 'iupac'
                })
            if pubchem_result.smiles:
                enriched['canonical_smiles'] = pubchem_result.smiles
            if pubchem_result.molecular_formula:
                enriched['molecular_formula'] = pubchem_result.molecular_formula
            if pubchem_result.molecular_weight:
                enriched['molecular_weight'] = pubchem_result.molecular_weight

        # Get detailed info from ChEMBL
        chembl_result = await self.chembl.resolve_by_inchi_key(inchi_key)
        if chembl_result.success:
            enriched['sources_queried'].append('chembl')
            if chembl_result.name:
                enriched['names'].append({
                    'name': chembl_result.name,
                    'source': 'chembl',
                    'type': 'preferred'
                })
            # ChEMBL is authoritative for SMILES if not already set
            if chembl_result.smiles and 'canonical_smiles' not in enriched:
                enriched['canonical_smiles'] = chembl_result.smiles

        return enriched


class RxNormResolver:
    """Resolver for RxNorm API (drug nomenclature)."""

    BASE_URL = "https://rxnav.nlm.nih.gov/REST"

    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        self._session = session
        self._owns_session = session is None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._session

    async def close(self):
        if self._owns_session and self._session:
            await self._session.close()
            self._session = None

    async def resolve_by_rxcui(self, rxcui: str) -> ExternalResolutionResult:
        """Resolve drug by RxCUI."""
        session = await self._get_session()
        url = f"{self.BASE_URL}/rxcui/{rxcui}/properties.json"

        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_rxnorm_response(data, rxcui)
                else:
                    return ExternalResolutionResult(
                        success=False, source='rxnorm', error=f'HTTP {response.status}'
                    )
        except Exception as e:
            logger.error(f"RxNorm RxCUI resolution error: {e}")
            return ExternalResolutionResult(success=False, source='rxnorm', error=str(e))

    async def resolve_by_name(self, name: str) -> ExternalResolutionResult:
        """Resolve drug by name to get RxCUI."""
        session = await self._get_session()
        url = f"{self.BASE_URL}/rxcui.json"
        params = {'name': name, 'search': 1}  # search=1 for normalized match

        try:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    id_group = data.get('idGroup', {})
                    rxcuis = id_group.get('rxnormId', [])
                    if rxcuis:
                        # Get properties for first match
                        return await self.resolve_by_rxcui(rxcuis[0])
                    return ExternalResolutionResult(
                        success=False, source='rxnorm', error='Drug not found'
                    )
                else:
                    return ExternalResolutionResult(
                        success=False, source='rxnorm', error=f'HTTP {response.status}'
                    )
        except Exception as e:
            logger.error(f"RxNorm name resolution error: {e}")
            return ExternalResolutionResult(success=False, source='rxnorm', error=str(e))

    def _parse_rxnorm_response(self, data: Dict, rxcui: str) -> ExternalResolutionResult:
        """Parse RxNorm properties response."""
        props = data.get('properties', {})
        if not props:
            return ExternalResolutionResult(
                success=False, source='rxnorm', error='No properties returned'
            )

        return ExternalResolutionResult(
            success=True,
            source='rxnorm',
            name=props.get('name'),
            identifiers={
                'rxcui': rxcui,
                'tty': props.get('tty'),  # Term type (IN, SCD, BN, etc.)
            },
            raw_response=data
        )


class PharmGKBResolver:
    """Resolver for PharmGKB API (pharmacogenomics)."""

    BASE_URL = "https://api.pharmgkb.org/v1/data"

    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        self._session = session
        self._owns_session = session is None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._session

    async def close(self):
        if self._owns_session and self._session:
            await self._session.close()
            self._session = None

    async def resolve_by_pharmgkb_id(self, pharmgkb_id: str) -> ExternalResolutionResult:
        """Resolve drug by PharmGKB ID (e.g., PA449015)."""
        session = await self._get_session()
        url = f"{self.BASE_URL}/drug/{pharmgkb_id}"

        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_drug_response(data)
                elif response.status == 404:
                    return ExternalResolutionResult(
                        success=False, source='pharmgkb', error='Drug not found'
                    )
                else:
                    return ExternalResolutionResult(
                        success=False, source='pharmgkb', error=f'HTTP {response.status}'
                    )
        except Exception as e:
            logger.error(f"PharmGKB ID resolution error: {e}")
            return ExternalResolutionResult(success=False, source='pharmgkb', error=str(e))

    async def search_by_name(self, name: str, limit: int = 5) -> List[ExternalResolutionResult]:
        """Search drugs by name via PharmGKB."""
        session = await self._get_session()
        url = f"{self.BASE_URL}/drug"
        params = {'q': name, 'limit': limit}

        try:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    results = data.get('data', [])
                    return [self._parse_drug_response(r) for r in results]
                else:
                    return []
        except Exception as e:
            logger.error(f"PharmGKB name search error: {e}")
            return []

    def _parse_drug_response(self, data: Dict) -> ExternalResolutionResult:
        """Parse PharmGKB drug response."""
        identifiers = {'pharmgkb_id': data.get('id')}

        # Extract cross-references
        xrefs = data.get('crossReferences', {})
        if xrefs.get('DrugBank'):
            identifiers['drugbank_id'] = xrefs['DrugBank'][0]
        if xrefs.get('ChEMBL'):
            identifiers['chembl_id'] = xrefs['ChEMBL'][0]
        if xrefs.get('RxNorm'):
            identifiers['rxcui'] = xrefs['RxNorm'][0]
        if xrefs.get('PubChem Compound'):
            identifiers['pubchem_cid'] = xrefs['PubChem Compound'][0]

        return ExternalResolutionResult(
            success=True,
            source='pharmgkb',
            name=data.get('name'),
            smiles=data.get('smiles'),
            inchi_key=data.get('inchiKey'),
            identifiers=identifiers,
            raw_response=data
        )


class KEGGResolver:
    """Resolver for KEGG Drug API."""

    BASE_URL = "https://rest.kegg.jp"

    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        self._session = session
        self._owns_session = session is None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._session

    async def close(self):
        if self._owns_session and self._session:
            await self._session.close()
            self._session = None

    async def resolve_by_kegg_id(self, kegg_id: str) -> ExternalResolutionResult:
        """Resolve drug by KEGG Drug ID (e.g., D00001)."""
        session = await self._get_session()
        url = f"{self.BASE_URL}/get/dr:{kegg_id}"

        try:
            async with session.get(url) as response:
                if response.status == 200:
                    text = await response.text()
                    return self._parse_kegg_flat_response(text, kegg_id)
                elif response.status == 404:
                    return ExternalResolutionResult(
                        success=False, source='kegg', error='Drug not found'
                    )
                else:
                    return ExternalResolutionResult(
                        success=False, source='kegg', error=f'HTTP {response.status}'
                    )
        except Exception as e:
            logger.error(f"KEGG ID resolution error: {e}")
            return ExternalResolutionResult(success=False, source='kegg', error=str(e))

    async def search_by_name(self, name: str) -> List[ExternalResolutionResult]:
        """Search drugs by name via KEGG."""
        session = await self._get_session()
        url = f"{self.BASE_URL}/find/drug/{name}"

        try:
            async with session.get(url) as response:
                if response.status == 200:
                    text = await response.text()
                    results = []
                    for line in text.strip().split('\n'):
                        if line:
                            parts = line.split('\t')
                            if len(parts) >= 2:
                                kegg_id = parts[0].replace('dr:', '')
                                result = await self.resolve_by_kegg_id(kegg_id)
                                if result.success:
                                    results.append(result)
                    return results
                else:
                    return []
        except Exception as e:
            logger.error(f"KEGG name search error: {e}")
            return []

    def _parse_kegg_flat_response(self, text: str, kegg_id: str) -> ExternalResolutionResult:
        """Parse KEGG flat file format response."""
        data = {'kegg_id': kegg_id}
        identifiers = {'kegg_id': kegg_id}
        current_field = None
        current_value = []

        for line in text.split('\n'):
            if line.startswith(' '):
                # Continuation of previous field
                if current_field:
                    current_value.append(line.strip())
            else:
                # Save previous field
                if current_field and current_value:
                    data[current_field.lower()] = '\n'.join(current_value)

                # Start new field
                if line.strip():
                    parts = line.split(None, 1)
                    current_field = parts[0] if parts else None
                    current_value = [parts[1]] if len(parts) > 1 else []

        # Extract specific identifiers from DBLINKS section
        dblinks = data.get('dblinks', '')
        for line in dblinks.split('\n'):
            if 'DrugBank:' in line:
                identifiers['drugbank_id'] = line.split('DrugBank:')[1].strip().split()[0]
            elif 'PubChem:' in line:
                identifiers['pubchem_sid'] = line.split('PubChem:')[1].strip().split()[0]
            elif 'ChEMBL:' in line:
                identifiers['chembl_id'] = line.split('ChEMBL:')[1].strip().split()[0]
            elif 'CAS:' in line:
                identifiers['cas_number'] = line.split('CAS:')[1].strip().split()[0]

        return ExternalResolutionResult(
            success=True,
            source='kegg',
            name=data.get('name', '').split(';')[0].strip() if data.get('name') else None,
            molecular_formula=data.get('formula'),
            identifiers=identifiers,
            raw_response=data
        )


class BindingDBResolver:
    """Resolver for BindingDB API."""

    BASE_URL = "https://bindingdb.org/axis2/services/BDBService"

    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        self._session = session
        self._owns_session = session is None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._session

    async def close(self):
        if self._owns_session and self._session:
            await self._session.close()
            self._session = None

    async def resolve_by_bindingdb_id(self, bindingdb_id: str) -> ExternalResolutionResult:
        """Resolve ligand by BindingDB ID (e.g., BDBM50000001)."""
        session = await self._get_session()
        # BindingDB uses SOAP API - simplified REST-like access
        monomer_id = bindingdb_id.replace('BDBM', '')
        url = f"{self.BASE_URL}/getLigandByMonomerid"
        params = {'monomerid': monomer_id}

        try:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    # Response is XML, parse it
                    text = await response.text()
                    return self._parse_bindingdb_xml(text, bindingdb_id)
                else:
                    return ExternalResolutionResult(
                        success=False, source='bindingdb', error=f'HTTP {response.status}'
                    )
        except Exception as e:
            logger.error(f"BindingDB ID resolution error: {e}")
            return ExternalResolutionResult(success=False, source='bindingdb', error=str(e))

    def _parse_bindingdb_xml(self, xml_text: str, bindingdb_id: str) -> ExternalResolutionResult:
        """Parse BindingDB XML response."""
        # Simple XML parsing for key fields
        identifiers = {'bindingdb_id': bindingdb_id}

        # Extract SMILES
        smiles = None
        if '<smiles>' in xml_text:
            start = xml_text.find('<smiles>') + 8
            end = xml_text.find('</smiles>')
            smiles = xml_text[start:end] if end > start else None

        # Extract InChI Key
        inchi_key = None
        if '<inchikey>' in xml_text:
            start = xml_text.find('<inchikey>') + 10
            end = xml_text.find('</inchikey>')
            inchi_key = xml_text[start:end] if end > start else None

        return ExternalResolutionResult(
            success=True,
            source='bindingdb',
            smiles=smiles,
            inchi_key=inchi_key,
            identifiers=identifiers,
            raw_response={'xml': xml_text[:1000]}  # Truncate for storage
        )
