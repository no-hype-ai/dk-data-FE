"""Domain modules for dk-data-client.

Each module wraps a slice of the dk-data read surface:
- molecules — mol_silver / mol_gold / mol_api
- companies — mol_silver.companies + mol_gold.company_pipeline
- conditions — ind_silver / ind_gold
- publications — mol_silver.publications + pubmed + openalex
- patents — ip_silver.patents
- providers — hcs_silver.providers

Modules do not own transport, cache, or telemetry — they delegate
everything to `DkDataClient.call()`. This keeps the per-domain modules
thin (just URL + params + method-name bookkeeping) and makes the
observable behavior uniform across domains.
"""
