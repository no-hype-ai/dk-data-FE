"""CMS Part D Drug Spending — spending dashboard data via data-api.

The API returns wide-format records (one row per drug, year-suffixed columns).
insert_records() pivots them into year-rows for hcs_raw.cms_part_d_spending.
"""

from typing import Any, Dict, List, Optional
from .cms_base import CMSBaseAdapter


class Adapter(CMSBaseAdapter):
    # Medicare Part D Spending by Drug
    DATASET_ID = "7e0b4365-fd63-4a29-8f5e-e0ac9f66a81b"

    @property
    def source_name(self) -> str:
        return "cms_part_d_spending"

    def build_query_url(self, base_url: str, query_keys: Dict[str, str]) -> str:
        filters = {}
        if "drug_name" in query_keys:
            filters["Brnd_Name"] = query_keys["drug_name"]
        return self.data_api_url(base_url, self.DATASET_ID, filters)

    def normalize(self, api_response: Any) -> Any:
        if isinstance(api_response, dict):
            return api_response.get("data", api_response)
        return api_response

    def _pivot_to_year_rows(self, wide_record: Dict) -> List[Dict]:
        """Pivot a wide-format API record into one dict per year."""
        # Detect years present in keys (e.g. Tot_Spndng_2023 → 2023)
        years = set()
        for key in wide_record:
            if key.startswith("Tot_Spndng_"):
                try:
                    years.add(int(key.split("_")[-1]))
                except ValueError:
                    pass

        rows = []
        brand = wide_record.get("Brnd_Name")
        generic = wide_record.get("Gnrc_Name")
        for year in sorted(years):
            total_spending = wide_record.get(f"Tot_Spndng_{year}")
            total_claims = wide_record.get(f"Tot_Clms_{year}")
            total_beneficiaries = wide_record.get(f"Tot_Benes_{year}")
            avg_cost_per_claim = wide_record.get(f"Avg_Spnd_Per_Clm_{year}")
            # Skip years with no data
            if total_spending is None and total_claims is None:
                continue
            rows.append({
                "brand_name": brand,
                "generic_name": generic,
                "total_spending": float(total_spending) if total_spending is not None else None,
                "total_claims": int(total_claims) if total_claims is not None else None,
                "total_beneficiaries": int(total_beneficiaries) if total_beneficiaries is not None else None,
                "avg_cost_per_claim": float(avg_cost_per_claim) if avg_cost_per_claim is not None else None,
                "year": year,
            })
        return rows

    async def insert_records(self, db_pool, api_response: Any) -> Optional[str]:
        """Upsert pivoted year-rows into hcs_raw.cms_part_d_spending."""
        records = self.normalize(api_response)
        if not records:
            return None
        if not isinstance(records, list):
            records = [records]

        total_upserted = 0
        async with db_pool.acquire() as conn:
            for wide_record in records:
                for row in self._pivot_to_year_rows(wide_record):
                    await conn.execute("""
                        INSERT INTO hcs_raw.cms_part_d_spending
                            (brand_name, generic_name, total_spending, total_claims,
                             total_beneficiaries, avg_cost_per_claim, year, _loaded_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
                        ON CONFLICT (brand_name, year) DO UPDATE SET
                            generic_name        = EXCLUDED.generic_name,
                            total_spending      = EXCLUDED.total_spending,
                            total_claims        = EXCLUDED.total_claims,
                            total_beneficiaries = EXCLUDED.total_beneficiaries,
                            avg_cost_per_claim  = EXCLUDED.avg_cost_per_claim,
                            _loaded_at          = NOW()
                    """,
                        row["brand_name"], row["generic_name"],
                        row["total_spending"], row["total_claims"],
                        row["total_beneficiaries"], row["avg_cost_per_claim"],
                        row["year"],
                    )
                    total_upserted += 1

        return f"cms_part_d_upserted:{total_upserted}" if total_upserted else None
