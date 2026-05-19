-- Migration 107: Add patent_type and patent_kind to mol_raw.uspto_patents
-- patent_type: "utility" / "design" / "plant" (from PatentsView API field patent_type)
-- patent_kind: document kind code (B1, B2, A1, etc.) — reserved for future extraction

ALTER TABLE mol_raw.uspto_patents
    ADD COLUMN IF NOT EXISTS patent_type TEXT,
    ADD COLUMN IF NOT EXISTS patent_kind TEXT;
