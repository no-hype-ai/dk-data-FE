# dk-data-fe Issues Priority List

**Generated**: 2026-01-30
**Total Open Issues**: 48
**Repository**: data-kinetic/dk-data-FE

---

## Priority Legend

| Priority | Description | Action Timeline |
|----------|-------------|-----------------|
| **P0 - Critical** | Security vulnerabilities, blocking issues | Immediate |
| **P1 - High** | Core infrastructure, foundation work | This sprint |
| **P2 - Medium** | Features, enhancements, data sources | Next sprint |
| **P3 - Low** | Documentation, tooling, nice-to-have | Backlog |

---

## P0 - Critical (Security & Blocking)

These issues must be resolved before production deployment.

| # | Issue | Category | Description |
|---|-------|----------|-------------|
| **3** | Insecure JWT Secret Configuration | Security | Empty/weak JWT secrets enable authentication bypass. PostgREST may accept any JWT without verification. |
| **4** | Overly Permissive Anonymous API Access | Security | `web_anon` role has read access to ALL tables including sensitive scoring data, financial indicators, and competitive intelligence. |
| **56** | Fix db-init job SQL syntax errors and role creation | Blocking | DB initialization fails with SQL syntax errors. Roles not created before being referenced. Blocks all database functionality. |

---

## P1 - High (Infrastructure & Foundation)

Core infrastructure required for production operations.

### Database & API Foundation

| # | Issue | Category | Description |
|---|-------|----------|-------------|
| **60** | Create initial API schema tables and views | Database | PostgREST reports "0 Relations" - no tables/views exposed in `api` schema yet. |
| **58** | Add PostgREST health endpoint via database view | API | Health check endpoint needed for Kubernetes probes. |
| **9** | No Database Migration Strategy | Database | No versioned migration system for schema changes. |
| **13** | No Database Backup and Recovery Strategy | Operations | No backup/recovery strategy defined for PostgreSQL data. |

### Security Hardening

| # | Issue | Category | Description |
|---|-------|----------|-------------|
| **17** | No Audit Trail for Data Changes and API Access | Security | Cannot track who accessed or modified data. |
| **18** | Unclear PII/PHI Data Handling | Compliance | No documented approach to handling sensitive health data. |
| **19** | No Defined Data Retention Policy | Compliance | Data retention requirements not defined. |

### CI/CD & Deployment

| # | Issue | Category | Description |
|---|-------|----------|-------------|
| **59** | Set up GitHub Actions CI/CD pipeline | DevOps | No automated CI/CD pipeline for testing and deployment. |
| **54** | Build and publish job-trigger container image | DevOps | Job trigger service needs container image for K8s deployment. |
| **55** | Build container images for ingestion CronJobs | DevOps | Ingestion jobs need container images. |
| **57** | Document and automate Doppler secret configuration | DevOps | Secret management setup not documented/automated. |

### Observability & Reliability

| # | Issue | Category | Description |
|---|-------|----------|-------------|
| **11** | No Observability Stack | Operations | No metrics, logging, or tracing infrastructure. |
| **61** | Enable observability stack integration | Operations | ServiceMonitor and PrometheusRule resources disabled - needs Prometheus Operator. |
| **6** | Silent CronJob Failures and Data Freshness Drift | Operations | CronJob failures not detected; data staleness not monitored. |
| **12** | No Kubernetes Resource Limits Defined | Operations | Missing resource limits can cause cluster instability. |

### Code Quality

| # | Issue | Category | Description |
|---|-------|----------|-------------|
| **14** | Incomplete Error Handling in Fetchers | Quality | External API errors not properly caught/logged. |
| **15** | Unknown Test Coverage | Quality | No visibility into test coverage metrics. |
| **5** | Brittle External API Dependencies | Quality | External API changes can break fetchers silently. |
| **7** | No Data Validation on Downstream Pipeline Outputs | Quality | SQLMesh outputs not validated for correctness. |

---

## P2 - Medium (Features & Enhancements)

### Production Readiness (Meta-Issue)

| # | Issue | Category | Description |
|---|-------|----------|-------------|
| **22** | Production Readiness for dk-data-fe | Meta | Comprehensive issue covering security, tech debt, observability, and GitOps deployment. 139 tasks total. |

### Technical Improvements

| # | Issue | Category | Description |
|---|-------|----------|-------------|
| **8** | Tight Coupling to Edwards/TAVR Use Case | Architecture | Platform too specific; needs generalization for other use cases. |
| **10** | SQLMesh Model Dependencies Not Explicit | Data Pipeline | Model dependencies not clearly defined. |
| **16** | Documentation Drift Risk | Documentation | Docs may not match actual implementation. |
| **20** | Python Dependency Version Management | Dependencies | No pinned versions or lock file for reproducibility. |
| **21** | PostgREST Version Compatibility | Dependencies | PostgREST version compatibility not tracked. |

### Frontend & Integration

| # | Issue | Category | Description |
|---|-------|----------|-------------|
| **52** | Frontend integration — React onboarding wizard + dashboard | Feature | React-based UI for platform onboarding and data visualization. |

---

## P3 - Low (Data Source Integrations)

New data source integrations - prioritize based on business value.

### Pharmaceutical & Clinical Data

| # | Issue | Data Source | Description |
|---|-------|-------------|-------------|
| **41** | DrugBank (requires API key) | Drug Info | Comprehensive drug database - requires paid API key. |
| **42** | UniProt | Proteins | Protein sequence and function database. |
| **44** | BindingDB | Binding Affinities | Drug-target binding measurements. |
| **45** | SIDER | Side Effects | Drug side effect information. |
| **49** | TDC ADMET | ADMET Properties | Absorption, distribution, metabolism, excretion, toxicity data. |
| **50** | PDB (Protein Data Bank) | Structures | 3D protein structure database. |

### Regulatory & Patent Data

| # | Issue | Data Source | Description |
|---|-------|-------------|-------------|
| **46** | Orange Book | FDA Approvals | FDA-approved drugs with patent/exclusivity info. |
| **47** | USPTO Patents | Patents | US patent data for competitive intelligence. |
| **48** | EMA | EU Regulatory | European Medicines Agency data. |
| **28** | EMA regulatory data fetcher | EU Regulatory | CHMP opinions, EPAR, referrals. |
| **30** | USPTO PatentsView API | Patents | Patent monitoring and analysis. |
| **31** | EPO Open Patent Services | EU Patents | European Patent Office data. |
| **33** | HTA body decision fetchers | HTA | NICE, G-BA, HAS, PBAC decisions. |

### Publications & Research

| # | Issue | Data Source | Description |
|---|-------|-------------|-------------|
| **26** | PubMed/MEDLINE API | Publications | Publication monitoring for competitive intelligence. |
| **27** | OpenAlex API | Publications | Publication metadata and citations. |
| **43** | OpenAlex | Publications | Open scholarly metadata. |
| **29** | Configurable journal RSS/Atom feed | Publications | Framework for journal article feeds. |
| **32** | Cochrane Library API | Systematic Reviews | Cochrane systematic review data. |

### Business Intelligence

| # | Issue | Data Source | Description |
|---|-------|-------------|-------------|
| **34** | Medical news aggregator framework | News | Medscape, Healio, etc. |
| **35** | SEC EDGAR API | Financial | Earnings and financial signals. |
| **51** | ORCID | KOL Identification | Researcher identification for key opinion leaders. |

---

## Recommended Execution Order

### Phase 1: Security & Stability (Week 1)
1. **#3** - Fix JWT secret configuration
2. **#4** - Restrict anonymous API access
3. **#56** - Fix db-init SQL errors
4. **#60** - Create initial API schema

### Phase 2: Infrastructure (Week 2)
1. **#59** - Set up CI/CD pipeline
2. **#54, #55** - Build container images
3. **#57** - Automate Doppler secrets
4. **#58** - Add health endpoints

### Phase 3: Observability & Quality (Week 3)
1. **#11, #61** - Enable observability stack
2. **#6** - Fix CronJob failure detection
3. **#12** - Set resource limits
4. **#14, #15** - Improve error handling and test coverage

### Phase 4: Production Hardening (Week 4)
1. **#9** - Implement migration strategy
2. **#13** - Set up backup/recovery
3. **#17** - Add audit trail
4. **#22** - Address remaining production readiness items

### Phase 5+: Features & Data Sources (Ongoing)
- Prioritize data source integrations based on business requirements
- Implement frontend dashboard (#52)
- Add data sources as needed by customers

---

## Quick Stats

| Category | Count |
|----------|-------|
| Security Issues | 5 |
| Infrastructure Issues | 12 |
| Data Quality Issues | 4 |
| Documentation Issues | 2 |
| Data Source Integrations | 22 |
| Feature Requests | 3 |

---

## Notes

- Issues **#3** and **#4** are security-critical and should be addressed before any external access is enabled
- Issue **#56** (db-init errors) blocks database functionality and should be the first fix
- The **#22** meta-issue contains a comprehensive production readiness plan with 139 sub-tasks
- Data source integrations (P3) should be prioritized based on customer demand and business value
