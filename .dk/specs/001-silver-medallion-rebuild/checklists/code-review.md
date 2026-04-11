# Code Review Checklists — Silver Medallion Rebuild

These three checklists are the operational guardrails from `transformation-reliability-low-tech-solutions.md` §9. Reviewers MUST run through the relevant checklist before approving a PR that touches the corresponding artifact type. All items must pass; any failure blocks the merge.

## Checklist 1 — Fetcher PR

When reviewing a PR that adds or modifies a file in `src/dk_data/ingestion/fetchers/`:

- [ ] Does it use per-row commits or `COPY` for batch inserts? **Reject** if it uses implicit transactions over loops (Python `for record in records: cur.execute(...)` without explicit `conn.commit()` per chunk).
- [ ] Does it call `dk_data.ingestion.utils.database.build_dsn()` to construct the connection? **Reject** if it calls `psycopg2.connect()` directly. (FR-030, `[DSN]` tag)
- [ ] Does the connection have `tcp_keepalives`, `statement_timeout`, `idle_in_transaction_session_timeout`, `lock_timeout` set? Verified via `build_dsn()` — but if the PR adds an inline override, audit it. (FR-022)
- [ ] Does it set `application_name` to the pod name in the DSN? (FR-023)
- [ ] Does it acquire an advisory lock via `meta.job_locks` at `run()` start to prevent concurrent invocations? **Reject** if it uses `pg_try_advisory_lock` (broken under PgBouncer transaction mode). (FR-025, `[JOBLK]` tag)
- [ ] Does it batch checkpoint state with the data inserts in the same transaction? `INSERT INTO meta.fetch_checkpoints` MUST be in the same transaction as the data inserts so a partial failure doesn't leave inconsistent state. (FR-026)
- [ ] Does it use exponential backoff for API errors? Tenacity `retry_with_exponential_backoff` or equivalent. (`[BRKR]` tag — circuit breaker on external service calls)
- [ ] If it downloads files >1 GB, does it support HTTP `Range` resume? (FR-027)
- [ ] If it's a high-volume fetcher (chembl_activities, pubchem-class), is it split into per-year or per-ID-range CronJobs each running <2 hours? (FR-067)
- [ ] Does its CronJob have `concurrencyPolicy: Forbid`?
- [ ] Does its CronJob set `POSTGRES_HOST` to PgBouncer (not the postgres primary) unless it requires session features? (FR-024, `[PGBOU]` tag)

## Checklist 2 — SQLMesh model PR

When reviewing a PR that adds or modifies a file in `src/dk_data/sqlmesh/models/`:

- [ ] **Estimate the WAL produced by the largest source table.** Rule of thumb: `(rows × ~500 B/row) × 2`. **Reject** if the estimate exceeds 5 GB (FR-021a — per-CronJob-run budget). For models touching tables larger than 1M rows, the PR description MUST include the WAL estimate.
- [ ] Does it use any of the 5 banned antipatterns? **Reject on any match.** (FR-015–FR-019, `[SVANT]` tag)
  - **S1**: OR-joins between two hub-eligible identifiers (`a.inchi_key = b.inchi_key OR LOWER(a.name) = LOWER(b.name)`)
  - **S2**: Leading-wildcard `LIKE '%' || name || '%'` against indexed columns
  - **S3**: Correlated scalar subqueries in SELECT lists
  - **S4**: Global `DISTINCT ON` over multi-way `UNION ALL`
  - **S5**: Trigram `similarity()` combined with `=` matchers in the same OR clause
- [ ] Does it carry forward every non-system column from its bronze upstream(s)? Run the `[CARRY]` contract test locally. **Reject** if any non-system bronze column is dropped. (FR-001, `[CARRY]` tag)
- [ ] If it does heavy JSONB extraction or large sort/hash, does it `SET LOCAL work_mem = '128MB'` (or up to 256 MB) at the start of the transaction? Per-session ceiling is 256 MB total — multiplied across multiple sorts. (FR-021b, FR-048)
- [ ] Does it use `INCREMENTAL_BY_UNIQUE_KEY` (good — MERGE semantics) or `INCREMENTAL_BY_TIME_RANGE` (bad — DELETE+INSERT)? **Reject** `INCREMENTAL_BY_TIME_RANGE` for tables larger than 1M rows. (FR-046)
- [ ] If it's an `INCREMENTAL_BY_UNIQUE_KEY` model, is the source wrapped in a deduplicating CTE (`SELECT DISTINCT ON (key) ... ORDER BY key, ingested_at DESC`) so we don't insert older versions? (FR-047)
- [ ] If it's a silver enrichment model, does it obtain entity IDs by indexed equi-join to a hub crosswalk OR by calling a `resolve_*()` function? **Reject** any inline cross-source linkage. (FR-014)
- [ ] If it's a `FULL` gold model, can it be converted to `INCREMENTAL_BY_UNIQUE_KEY` with a watermark? Note in the PR if not. (FR-049)
- [ ] If it depends on freshly-loaded bronze, does it start with an explicit staleness check that raises an exception if the upstream is older than 6 hours? (FR-050)

## Checklist 3 — CronJob YAML PR

When reviewing a PR that adds or modifies a file in `k8s/apps/cronjobs/`:

- [ ] Does it set `concurrencyPolicy: Forbid`? **Reject** `Allow` or unset.
- [ ] Does it set `activeDeadlineSeconds` to a realistic value? Rule of thumb: 2x the expected runtime. For heavy bronze refreshes (chembl_activities, pubchem) at least 14400 (4h). (FR-051, FR-062)
- [ ] Does it set `backoffLimit: 1` (or 0 for procedure invocations) instead of the default 6? Default 6 turns one failure into ~6 hours of retry storms. **Reject** if `backoffLimit > 1`.
- [ ] Does it set CPU and memory `resources.requests` and `resources.limits`? **Reject** if either is missing.
- [ ] Does it set `POSTGRES_HOST` to `pgbouncer.infra.svc.cluster.local` (PgBouncer) unless it's a procedure invocation that needs direct connection (in which case use `POSTGRES_HOST_DIRECT`)? (FR-024, FR-037b, `[PGBOU]` tag)
- [ ] If it's part of the 1st-of-month or April-15 stampede, is it staggered across hours or days from the other stampede members? (FR-029)
- [ ] Does it have a unique label `app.kubernetes.io/component=fetcher` or `=transform` so the global concurrency cap (FR-021e) can count active pods?
- [ ] If it's a backup CronJob, is it scheduled outside the heavy fetch windows (i.e., NOT 02:00 UTC overlapping with overnight fetchers)? (FR-061)
- [ ] If it invokes a PL/pgSQL procedure via `psql -c "CALL ..."`, does it use `POSTGRES_HOST_DIRECT` and not PgBouncer? (FR-037b)

## Notes

- These checklists are `transformation-reliability-low-tech-solutions.md` §9 verbatim, augmented with the FR numbers and tag references from the spec.
- Reviewers MAY waive a checklist item only with explicit justification in the PR description and approval from a second reviewer.
- All three checklists are run on every PR — reviewers pick the relevant ones based on which files the PR touches.
