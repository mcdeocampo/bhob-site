-- Migration: Transparency Categories (CMS-managed)
-- Replaces the fixed 7-slug set that was previously hardcoded in
-- server.py's TRANSPARENCY_CATEGORIES dict and baked into
-- transparency_documents.category via a CHECK constraint. Categories are
-- now rows an admin can create/rename/reorder/deactivate/delete, with no
-- code change required to add more. Run this in the Supabase SQL Editor.

CREATE TABLE IF NOT EXISTS transparency_categories (
    id            TEXT         PRIMARY KEY,
    name          TEXT         NOT NULL UNIQUE,
    display_order INTEGER      NOT NULL DEFAULT 0,
    active        BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

ALTER TABLE IF EXISTS transparency_categories ENABLE ROW LEVEL SECURITY;

-- Seed the 7 categories that were previously hardcoded, preserving their
-- existing display names and order — existing documents are remapped to
-- these below, so nothing currently published disappears from the site.
-- Fixed literal IDs so this INSERT/UPDATE pairing is safe to re-run.
INSERT INTO transparency_categories (id, name, display_order) VALUES
    ('11111111-0001-4000-8000-000000000001', 'Barangay Budget Summary',    0),
    ('11111111-0001-4000-8000-000000000002', 'Financial Reports',         1),
    ('11111111-0001-4000-8000-000000000003', 'Procurement Notices',       2),
    ('11111111-0001-4000-8000-000000000004', 'Barangay Resolutions',      3),
    ('11111111-0001-4000-8000-000000000005', 'Barangay Ordinances',       4),
    ('11111111-0001-4000-8000-000000000006', 'Project Accomplishments',   5),
    ('11111111-0001-4000-8000-000000000007', 'Barangay Assembly Reports', 6)
ON CONFLICT (id) DO NOTHING;

-- transparency_documents now references a category row instead of a fixed
-- slug string.
ALTER TABLE transparency_documents ADD COLUMN IF NOT EXISTS category_id TEXT;

UPDATE transparency_documents SET category_id = '11111111-0001-4000-8000-000000000001' WHERE category = 'budget-summary';
UPDATE transparency_documents SET category_id = '11111111-0001-4000-8000-000000000002' WHERE category = 'financial-reports';
UPDATE transparency_documents SET category_id = '11111111-0001-4000-8000-000000000003' WHERE category = 'procurement-notices';
UPDATE transparency_documents SET category_id = '11111111-0001-4000-8000-000000000004' WHERE category = 'resolutions';
UPDATE transparency_documents SET category_id = '11111111-0001-4000-8000-000000000005' WHERE category = 'ordinances';
UPDATE transparency_documents SET category_id = '11111111-0001-4000-8000-000000000006' WHERE category = 'project-accomplishments';
UPDATE transparency_documents SET category_id = '11111111-0001-4000-8000-000000000007' WHERE category = 'assembly-reports';

-- The fixed 7-slug CHECK constraint and the old category column are fully
-- replaced by category_id now that every existing row has been remapped.
ALTER TABLE transparency_documents DROP CONSTRAINT IF EXISTS transparency_documents_category_check;
ALTER TABLE transparency_documents DROP COLUMN IF EXISTS category;

CREATE INDEX IF NOT EXISTS idx_transparency_docs_category_id ON transparency_documents (category_id);
