-- Migration 139: Drop orphaned raw.* tables superseded by mol_raw.*
-- Issue: #196 L4
-- Branch: 025-schema-integrity-stability
--
-- raw.trademark_status_history was created in migration 073.
-- USPTO/EUIPO loaders have written to mol_raw.trademark_status_history since
-- migration 137. The raw.* version is orphaned and receives no new data.
-- Migration 138 section (j) handles fresh clusters; this migration handles
-- existing clusters that ran 138 before section (j) was added.

DROP TABLE IF EXISTS raw.trademark_status_history;
