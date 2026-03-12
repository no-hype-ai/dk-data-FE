# Unified Data Tools Adapters
#
# Re-exports existing MCP adapters for molecule/IP tools.
# New CMS adapters live in this package alongside the CMS base adapter.
#
# Adapter contract:
#   - class Adapter with normalize(api_response) → dict
#   - For CMS queryable: also async fetch(query_keys, timeout) → dict
