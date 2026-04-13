"""Molecule read surface.

All methods hit the dk-data PostgREST / FastAPI endpoints documented in
docs/data-catalog.md and contracts/client-package-api.md. Return shapes
come from mol_silver and mol_gold — see data-model.md for column sets.
"""

from __future__ import annotations

from typing import Any

from dk_data_client.modules._base import ModuleBase


class MoleculesModule(ModuleBase):
    async def resolve(self, name_or_id: str, *, hint: str | None = None) -> dict[str, Any]:
        """Resolve a name or identifier to a canonical molecule_id.

        Uses the FastAPI `/data-platform/molecules/resolve` wrapper
        which calls `mol_silver.resolve_molecule()` server-side.
        """
        body: dict[str, Any] = {"name_or_id": name_or_id}
        if hint:
            body["hint"] = hint
        return await self._call(
            method="molecules.resolve",
            path="/data-platform/molecules/resolve",
            args={"name_or_id": name_or_id, "hint": hint},
            http_method="POST",
            json_body=body,
        )

    async def search(
        self, query: str, *, limit: int = 25, threshold: float = 0.3
    ) -> list[dict[str, Any]]:
        params = {
            "select": "molecule_id,canonical_name,inchi_key",
            "or": f"(canonical_name.ilike.*{query}*,molecule_id.eq.{query})",
            "limit": str(limit),
        }
        data = await self._call(
            method="molecules.search",
            path="/molecules",
            args={"query": query, "limit": limit, "threshold": threshold},
            params=params,
        )
        return list(data) if isinstance(data, list) else []

    async def get(self, molecule_id: str) -> dict[str, Any]:
        params = {"molecule_id": f"eq.{molecule_id}", "limit": "1"}
        rows = await self._call(
            method="molecules.get",
            path="/molecules",
            args={"id": molecule_id},
            params=params,
        )
        if isinstance(rows, list) and rows:
            return dict(rows[0])
        return {}

    async def get_profile(self, molecule_id: str) -> dict[str, Any]:
        params = {"molecule_id": f"eq.{molecule_id}", "limit": "1"}
        rows = await self._call(
            method="molecules.getProfile",
            path="/molecule_profile",
            args={"id": molecule_id},
            params=params,
        )
        if isinstance(rows, list) and rows:
            return dict(rows[0])
        return {}

    async def get_safety(self, molecule_id: str) -> dict[str, Any]:
        params = {"molecule_id": f"eq.{molecule_id}"}
        rows = await self._call(
            method="molecules.getSafety",
            path="/safety_signals",
            args={"id": molecule_id},
            params=params,
        )
        return dict(rows[0]) if isinstance(rows, list) and rows else {}

    async def get_adverse_events(
        self, molecule_id: str, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        params = {"molecule_id": f"eq.{molecule_id}", "limit": str(limit)}
        data = await self._call(
            method="molecules.getAdverseEvents",
            path="/adverse_events",
            args={"id": molecule_id, "limit": limit},
            params=params,
        )
        return list(data) if isinstance(data, list) else []

    async def get_clinical_trials(
        self, molecule_id: str, *, phase: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "molecule_id": f"eq.{molecule_id}",
            "limit": str(limit),
        }
        if phase:
            params["phase"] = f"eq.{phase}"
        data = await self._call(
            method="molecules.getClinicalTrials",
            path="/clinical_trials",
            args={"id": molecule_id, "phase": phase, "limit": limit},
            params=params,
        )
        return list(data) if isinstance(data, list) else []

    async def get_drug_labels(self, molecule_id: str) -> list[dict[str, Any]]:
        params = {"molecule_id": f"eq.{molecule_id}"}
        data = await self._call(
            method="molecules.getDrugLabels",
            path="/drug_labels",
            args={"id": molecule_id},
            params=params,
        )
        return list(data) if isinstance(data, list) else []

    async def get_boxed_warnings(self, molecule_id: str) -> list[dict[str, Any]]:
        # Feature 002 scope correction: boxed warnings live inline on
        # mol_silver.drug_labels, not in a dedicated api.boxed_warnings
        # view. Filter on the inline column.
        params = {
            "molecule_id": f"eq.{molecule_id}",
            "boxed_warning": "not.is.null",
            "select": "molecule_id,boxed_warning,label_date",
        }
        data = await self._call(
            method="molecules.getBoxedWarnings",
            path="/drug_labels",
            args={"id": molecule_id},
            params=params,
        )
        return list(data) if isinstance(data, list) else []

    async def get_contraindications(self, molecule_id: str) -> list[dict[str, Any]]:
        params = {
            "molecule_id": f"eq.{molecule_id}",
            "contraindications": "not.is.null",
            "select": "molecule_id,contraindications,label_date",
        }
        data = await self._call(
            method="molecules.getContraindications",
            path="/drug_labels",
            args={"id": molecule_id},
            params=params,
        )
        return list(data) if isinstance(data, list) else []

    async def get_competitive_landscape(self, indication: str) -> list[dict[str, Any]]:
        """Return the competitive landscape for a therapeutic area.

        Reads `mol_api.competitive_scores` (migration 216) which applies
        a derived numeric score on top of `mol_gold.competitive_landscape`.
        """
        params = {
            "therapeutic_areas": f"cs.{{{indication}}}",
            "order": "competitive_score.desc",
            "limit": "50",
        }
        data = await self._call(
            method="molecules.getCompetitiveLandscape",
            path="/competitive_scores",
            args={"indication": indication},
            params=params,
        )
        return list(data) if isinstance(data, list) else []

    async def get_resolution_queue(
        self, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Live view of unresolved molecule identifiers — NEVER cached."""
        params = {"limit": str(limit), "order": "queued_at.desc"}
        data = await self._call(
            method="molecules.getResolutionQueue",
            path="/resolution_queue",
            args={"limit": limit},
            params=params,
        )
        return list(data) if isinstance(data, list) else []
