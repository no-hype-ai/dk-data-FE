# Schema Contract: <Entity Name>

> Formal contract for a persisted data model or shared type.
> Drop into `.dk/specs/<feature>/contracts/` and fill in.

## Purpose

<One-sentence description of what this entity represents and where it lives
(database table, document collection, in-memory struct, wire format).>

## Storage

- **Backend**: <Postgres, DynamoDB, etcd, S3 JSON, in-memory, etc.>
- **Location**: <schema.table, collection path, key prefix>
- **Lifecycle**: <append-only | mutable | TTL after N days>

## Fields

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `id` | uuid | yes | PK, immutable | Stable identifier |
| `created_at` | timestamp | yes | auto | UTC, immutable |
| `updated_at` | timestamp | yes | auto | UTC, bumped on any write |
| `<field>` | `<type>` | <yes/no> | `<constraint>` | <what it means> |

## Indexes

| Index | Columns | Purpose |
|-------|---------|---------|
| `pk_<entity>` | `id` | primary key |
| `ix_<entity>_<col>` | `<col>` | <query pattern it serves> |

## Relations

| Relation | Target | Cardinality | On delete |
|----------|--------|-------------|-----------|
| `<fk_name>` | `<other_entity>.id` | N:1 | `cascade | set null | restrict` |

## Invariants

- <Guarantee 1 — e.g., "status transitions are monotonic: pending → active → archived"></li>
- <Guarantee 2 — e.g., "deleted_at is never unset once set"></li>
- <Guarantee 3 — e.g., "(tenant_id, name) is unique"></li>

## Migration Notes

- <If this replaces an existing schema, describe the migration path>
- <Backfill strategy for required fields added to existing rows>
- <Rollback plan>

## Tags

Active principle tags this contract honors: `[TYPED]`, `[IMMUT]`, `[SEGMN]`
