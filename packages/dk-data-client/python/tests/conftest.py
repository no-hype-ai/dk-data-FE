"""pytest configuration for dk-data-client tests.

Every test module that defines async tests relies on
`asyncio_mode = "auto"` in pyproject.toml. This file exists to anchor
`tests/` as a package root so relative imports work under pytest's
rootdir discovery.
"""
