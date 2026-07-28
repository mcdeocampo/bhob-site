-- Migration: create Transparency Documents CMS table
-- Backs the enhanced Transparency admin module and the transparency.html
-- page's per-category document lists. Run this in the Supabase SQL Editor
-- before deploying the Transparency enhancement backend.
--
-- `category` is a fixed set matching the site's existing 7 Transparency
-- categories (unchanged from the current static page) — stored as a slug
-- so labels can be edited in the UI layer without a migration.

CREATE TABLE IF NOT EXISTS transparency_documents (
    id                TEXT         PRIMARY KEY,
    category          TEXT         NOT NULL    DEFAULT ''
                      CHECK (category IN (
                          'budget-summary', 'financial-reports', 'procurement-notices',
                          'resolutions', 'ordinances', 'project-accomplishments',
                          'assembly-reports'
                      )),
    title             TEXT         NOT NULL    DEFAULT '',
    doc_number        TEXT                     DEFAULT '',
    description       TEXT                     DEFAULT '',
    publication_date  DATE,
    doc_year          INTEGER,
    file_url          TEXT                     DEFAULT '',
    file_name         TEXT                     DEFAULT '',
    file_type         TEXT                     DEFAULT '',
    file_size         INTEGER                  DEFAULT 0,
    status            TEXT         NOT NULL    DEFAULT 'draft'
                      CHECK (status IN ('draft', 'published', 'archived')),
    display_order     INTEGER      NOT NULL    DEFAULT 0,
    created_at        TIMESTAMPTZ  NOT NULL    DEFAULT NOW(),
    updated_at        TIMESTAMPTZ  NOT NULL    DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_transparency_docs_category ON transparency_documents (category);
CREATE INDEX IF NOT EXISTS idx_transparency_docs_status   ON transparency_documents (status);

-- RLS enabled with no policies — server.py talks to Supabase using the
-- service-role key (bypasses RLS by design), same as every other table.
ALTER TABLE IF EXISTS transparency_documents ENABLE ROW LEVEL SECURITY;
