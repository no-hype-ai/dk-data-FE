"""Publications / literature read surface.

Reads from `mol_silver.publications` (unified), `mol_silver.pubmed_articles`,
and the upstream Europe PMC shim for fallthrough.
"""

from __future__ import annotations

from typing import Any

from dk_data_client.modules._base import ModuleBase


class PublicationsModule(ModuleBase):
    async def search(
        self, query: str, *, limit: int = 25, since: str | None = None
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "select": "publication_id,title,doi,pmid,published_at,journal",
            "title": f"ilike.*{query}*",
            "order": "published_at.desc",
            "limit": str(limit),
        }
        if since:
            params["published_at"] = f"gte.{since}"
        data = await self._call(
            method="publications.search",
            path="/publications",
            args={"query": query, "limit": limit, "since": since},
            params=params,
        )
        return list(data) if isinstance(data, list) else []

    async def get_by_molecule(self, molecule_id: str) -> list[dict[str, Any]]:
        params = {
            "molecule_id": f"eq.{molecule_id}",
            "order": "published_at.desc",
            "limit": "100",
        }
        data = await self._call(
            method="publications.getByMolecule",
            path="/publications",
            args={"molecule_id": molecule_id},
            params=params,
        )
        return list(data) if isinstance(data, list) else []

    async def get_pubmed(self, pmid: str) -> dict[str, Any]:
        params = {"pmid": f"eq.{pmid}", "limit": "1"}
        rows = await self._call(
            method="publications.getPubMed",
            path="/pubmed_articles",
            args={"pmid": pmid},
            params=params,
        )
        return dict(rows[0]) if isinstance(rows, list) and rows else {}

    async def get_openalex(self, work_id: str) -> dict[str, Any]:
        params = {"openalex_id": f"eq.{work_id}", "limit": "1"}
        rows = await self._call(
            method="publications.getOpenAlex",
            path="/publications",
            args={"openalex_id": work_id},
            params=params,
        )
        return dict(rows[0]) if isinstance(rows, list) and rows else {}
