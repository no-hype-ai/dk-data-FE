# Specification Quality Checklist: USPTO & EUIPO Model Datasource Integration

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-02-16
**Updated**: 2026-02-16 (post review: fixed FR numbering, API refs, source counts)
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## External API Verification

- [x] USPTO PatentsView API — existing, verified working in dk-data-FE
- [x] USPTO TSDR API — verified from official Swagger spec and FAQ (API key, 60 req/min, lookup-only)
- [x] USPTO Bulk Data — verified migration to data.uspto.gov ODP
- [x] EPO OPS API — existing, verified working in dk-data-FE
- [x] EUIPO — TMview API identified as recommended option (federated search, POST JSON)
- [x] EUIPO IBM API Gateway — confirmed exists but gated (requires registration)
- [x] EUIPO eSearch Plus — confirmed as web app only, no public REST API

## Notes

- Spec now covers BOTH patents and trademarks from both USPTO and EUIPO
- 7 user stories (P1: 2 patent pipeline, P2: 3 trademark + observability, P3: 2 automation + CI)
- 23 functional requirements (FR-001 through FR-015, plus FR-005a-d and FR-006a-d)
- 8 success criteria
- 5 clarifications resolved (Session 2026-02-16): cross-registry dedup, EUIPO API strategy, status history, bulk load scope, gold layer
- TSDR API is lookup-only — initial Class 5 dataset requires bulk XML download
- TMview API chosen over eSearch Plus (which has no public API)
- All API details verified against external documentation, not just dk-data backend code
