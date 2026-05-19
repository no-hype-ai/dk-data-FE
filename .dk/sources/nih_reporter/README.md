# nih_reporter

**Domain:** hcp
**Tier:** T1 — free NIH ExPORTER bulk download, no auth
**Fetch:** http_csv, weekly
**Status:** live — tracking issue: #329

## Purpose
NIH RePORTER / ExPORTER publishes weekly dumps of NIH-funded projects, abstracts, publications, and patents tied to grants. Landing this feeds `hcp_silver.researchers` with grant-linked affiliation history and fuels translational-research scoring that connects bench researchers to clinical pipelines — a prerequisite for any KOL-identification use case grounded in funding.

## Upstream
- URL: https://reporter.nih.gov/exporter (weekly ExPORTER CSV bundles by fiscal year and category)
- API docs: https://api.reporter.nih.gov/ (optional paginated JSON companion)
- Rate limits: none documented on bulk; paginated API is 1 req/sec
- Auth: none

## Expected schema
- Target schema: `hcp_raw.nih_reporter` → `hcp_bronze.nih_reporter` → `hcp_silver.researcher_grants`
- Known columns: `appl_id`, `project_num`, `pi_name`, `org_name`, `org_state`, `fy`, `total_cost`, `project_title`, `abstract_text`
- Row-count estimate: ~90k projects/year; cumulative ExPORTER ~2M project rows + publications link table

## Plan
Follow the `dk data source add` scaffold flow when onboarding. See plan.md §F.2 for the CLI surface and §E for tier context.
