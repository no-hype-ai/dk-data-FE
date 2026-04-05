-- Migration 156: alter mol_bronze.openfda_labels.spl_version from INTEGER to BIGINT
-- SPL version values can exceed INT32 max (2,147,483,647); e.g. 4,571,261,921 observed.
ALTER TABLE mol_bronze.openfda_labels
    ALTER COLUMN spl_version TYPE BIGINT;
