"""Fallback modes for dk-data-client.

When a call misses dk-data's own data (404, empty result, stale-rejected),
the client falls back according to its configured mode:

- **strict**: raise `DkDataNotFoundError` / `DkDataStaleError` immediately.
  Used by human-facing tools that would rather show "no data" than slow,
  potentially-wrong data.

- **upstream**: try the originating upstream API (PubChem, FDA, CT.gov,
  Europe PMC, etc.), transforming the response to match the dk-data
  shape. On upstream failure, raise `DkDataUpstreamError`. NO write-back
  to dk-data in v0.1 — hydration is an operator decision, tracked via
  telemetry.

- **hydrate**: DEFERRED to v1.1 — same as upstream but writes the result
  back to dk-data. Gated behind idempotent ingestion endpoints which
  land in Phase 4. Importing `FallbackMode.HYDRATE` in v0.1 raises
  `NotImplementedError`.

The per-upstream shims live here so they can be unit-tested in isolation.
For v0.1 we ship a single canonical upstream per method — the contract
is "best-effort, clearly-labeled telemetry outcome" rather than "try
every upstream in order".
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from dk_data_client.errors import (
    DkDataNotFoundError,
    DkDataUpstreamError,
)


class FallbackMode(enum.Enum):
    STRICT = "strict"
    UPSTREAM = "upstream"
    HYDRATE = "hydrate"  # v1.1


@dataclass
class FallbackContext:
    """State passed to an upstream shim when the primary call missed."""

    method: str
    args: dict[str, Any]
    upstream_name: str  # e.g., "pubchem", "fda", "ct.gov"


class UpstreamShim(Protocol):
    """A shim knows how to fetch one method's data from one upstream API
    and return a response shaped like dk-data's own."""

    upstream_name: str

    async def fetch(self, ctx: FallbackContext, http: httpx.AsyncClient) -> Any: ...


# -----------------------------------------------------------------------------
# Registry of v0.1 shims — extended over time as sources are added.
# Each shim implements a narrow best-effort fetch for ONE method.
# -----------------------------------------------------------------------------


class PubchemMoleculeShim:
    upstream_name = "pubchem"

    async def fetch(self, ctx: FallbackContext, http: httpx.AsyncClient) -> Any:
        name_or_id = ctx.args.get("name_or_id") or ctx.args.get("id") or ""
        if not name_or_id:
            raise DkDataNotFoundError(f"no identifier for {ctx.method}")
        # PubChem REST: /rest/pug/compound/name/{name}/property/InChIKey,CanonicalSMILES/JSON
        url = (
            f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/"
            f"name/{name_or_id}/property/InChIKey,CanonicalSMILES,MolecularFormula/JSON"
        )
        try:
            resp = await http.get(url, timeout=10.0)
        except httpx.HTTPError as e:
            raise DkDataUpstreamError(
                f"pubchem fetch failed: {e}", upstream=self.upstream_name
            ) from e
        if resp.status_code == 404:
            raise DkDataNotFoundError(f"not found in pubchem: {name_or_id}")
        if resp.status_code >= 500:
            raise DkDataUpstreamError(
                f"pubchem returned {resp.status_code}",
                upstream=self.upstream_name,
            )
        data = resp.json()
        props = data.get("PropertyTable", {}).get("Properties", [])
        if not props:
            raise DkDataNotFoundError(f"pubchem returned empty: {name_or_id}")
        row = props[0]
        return {
            "id": f"PUBCHEM:{row.get('CID')}",
            "inchi_key": row.get("InChIKey"),
            "canonical_smiles": row.get("CanonicalSMILES"),
            "molecular_formula": row.get("MolecularFormula"),
            "source": "pubchem",
            "fallthrough": True,
        }


class ClinicalTrialsShim:
    upstream_name = "clinicaltrials.gov"

    async def fetch(self, ctx: FallbackContext, http: httpx.AsyncClient) -> Any:
        query = ctx.args.get("id") or ctx.args.get("name_or_id") or ""
        if not query:
            raise DkDataNotFoundError(f"no query for {ctx.method}")
        # CT.gov v2 API: /api/v2/studies?query.term={q}&pageSize=50
        url = "https://clinicaltrials.gov/api/v2/studies"
        try:
            resp = await http.get(
                url,
                params={"query.term": query, "pageSize": 50, "format": "json"},
                timeout=15.0,
            )
        except httpx.HTTPError as e:
            raise DkDataUpstreamError(
                f"ct.gov fetch failed: {e}", upstream=self.upstream_name
            ) from e
        if resp.status_code >= 500:
            raise DkDataUpstreamError(
                f"ct.gov returned {resp.status_code}",
                upstream=self.upstream_name,
            )
        data = resp.json()
        studies = data.get("studies", [])
        return [
            {
                "nct_id": s.get("protocolSection", {})
                .get("identificationModule", {})
                .get("nctId"),
                "title": s.get("protocolSection", {})
                .get("identificationModule", {})
                .get("briefTitle"),
                "source": "ct.gov",
                "fallthrough": True,
            }
            for s in studies
        ]


class PubchemMoleculeSearchShim:
    """PubChem fallback for molecules.search.

    Without this, ``molecules.search(query=...)`` with ``fallback_mode="upstream"``
    raises ``DkDataNotFoundError("no upstream shim registered")`` on a dk-data
    404 — surprising because the other molecule methods DO have a shim.

    PubChem name search returns a list of matching compounds by name/synonym.
    Results are shaped to match the dk-data search result schema with a
    ``fallthrough=True`` marker so callers can distinguish upstream results.
    """

    upstream_name = "pubchem"

    async def fetch(self, ctx: FallbackContext, http: httpx.AsyncClient) -> Any:
        query = ctx.args.get("query") or ctx.args.get("name_or_id") or ""
        if not query:
            raise DkDataNotFoundError(f"no query for {ctx.method}")
        # PubChem name→property lookup — same endpoint as resolve shim but
        # returns all matching compounds rather than just the first.
        url = (
            f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/"
            f"name/{query}/property/InChIKey,CanonicalSMILES,"
            f"MolecularFormula,IUPACName/JSON"
        )
        try:
            resp = await http.get(url, timeout=10.0)
        except httpx.HTTPError as e:
            raise DkDataUpstreamError(
                f"pubchem search failed: {e}", upstream=self.upstream_name
            ) from e
        if resp.status_code == 404:
            raise DkDataNotFoundError(f"not found in pubchem: {query}")
        if resp.status_code >= 500:
            raise DkDataUpstreamError(
                f"pubchem returned {resp.status_code}", upstream=self.upstream_name
            )
        data = resp.json()
        props = data.get("PropertyTable", {}).get("Properties", [])
        if not props:
            raise DkDataNotFoundError(f"pubchem returned empty results: {query}")
        return [
            {
                "id": f"PUBCHEM:{row.get('CID')}",
                "inchi_key": row.get("InChIKey"),
                "canonical_smiles": row.get("CanonicalSMILES"),
                "molecular_formula": row.get("MolecularFormula"),
                "canonical_name": row.get("IUPACName"),
                "source": "pubchem",
                "fallthrough": True,
            }
            for row in props
        ]


class EuropePMCShim:
    upstream_name = "europe-pmc"

    async def fetch(self, ctx: FallbackContext, http: httpx.AsyncClient) -> Any:
        query = ctx.args.get("query") or ""
        if not query:
            raise DkDataNotFoundError(f"no query for {ctx.method}")
        url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        try:
            resp = await http.get(
                url,
                params={"query": query, "format": "json", "pageSize": 25},
                timeout=15.0,
            )
        except httpx.HTTPError as e:
            raise DkDataUpstreamError(
                f"europe-pmc fetch failed: {e}", upstream=self.upstream_name
            ) from e
        if resp.status_code >= 500:
            raise DkDataUpstreamError(
                f"europe-pmc returned {resp.status_code}",
                upstream=self.upstream_name,
            )
        data = resp.json()
        hits = data.get("resultList", {}).get("result", [])
        return [
            {
                "id": h.get("id"),
                "title": h.get("title"),
                "doi": h.get("doi"),
                "source": "europe-pmc",
                "fallthrough": True,
            }
            for h in hits
        ]


# Map method → shim. Extend as new fallthrough sources are implemented.
_SHIM_REGISTRY: dict[str, UpstreamShim] = {
    "molecules.resolve": PubchemMoleculeShim(),
    "molecules.get": PubchemMoleculeShim(),
    # molecules.search was missing — a 404 with fallback_mode="upstream" would
    # raise DkDataNotFoundError("no upstream shim registered") instead of
    # attempting PubChem.  PubchemMoleculeSearchShim returns a list of hits.
    "molecules.search": PubchemMoleculeSearchShim(),
    "molecules.getClinicalTrials": ClinicalTrialsShim(),
    "publications.search": EuropePMCShim(),
}


async def fallback_to_upstream(
    method: str,
    args: dict[str, Any],
    *,
    mode: FallbackMode,
    http: httpx.AsyncClient,
) -> tuple[Any, str]:
    """Run the configured fallback for a missed call.

    Returns `(value, upstream_name)` — both for caller logging and for
    the telemetry emitter to tag the event. Raises
    `DkDataNotFoundError` if no shim is registered and mode is not
    strict; raises `DkDataNotFoundError` / `DkDataStaleError` in strict
    mode (caller re-raises).
    """
    if mode is FallbackMode.STRICT:
        raise DkDataNotFoundError(f"strict fallback: {method}({args})")
    if mode is FallbackMode.HYDRATE:
        raise NotImplementedError(
            "hydrate fallback is scheduled for v1.1 (idempotent ingestion required)"
        )
    shim = _SHIM_REGISTRY.get(method)
    if shim is None:
        raise DkDataNotFoundError(
            f"no upstream shim registered for {method}; cannot fallback"
        )
    ctx = FallbackContext(method=method, args=args, upstream_name=shim.upstream_name)
    value = await shim.fetch(ctx, http)
    return value, shim.upstream_name


def register_shim(method: str, shim: UpstreamShim) -> None:
    """Consumer-provided shim registration (advanced use only)."""
    _SHIM_REGISTRY[method] = shim
