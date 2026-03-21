-- Migration 108: Rebuild cms_usp for USP MMG v9.0 Alignment File
-- Applied: 2026-03-15
--
-- Replaces the old (usp_category, usp_class, drug_names) schema
-- with the alignment file schema that maps RxCUI → USP Category/Class.
-- PK is (rxcui, usp_category, usp_class) because some drugs map
-- to multiple categories (e.g., doxepin → Antidepressants AND Anxiolytics).

DROP TABLE IF EXISTS hcs_raw.cms_usp CASCADE;
CREATE TABLE hcs_raw.cms_usp (
    rxcui          TEXT NOT NULL,
    tty            TEXT,
    branded_name   TEXT,
    related_bn     TEXT,
    related_df     TEXT,
    usp_category   TEXT NOT NULL,
    usp_class      TEXT NOT NULL,
    _loaded_at     TIMESTAMPTZ DEFAULT now(),
    _source_file   TEXT,
    _source_hash   TEXT,
    PRIMARY KEY (rxcui, usp_category, usp_class)
);
