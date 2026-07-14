-- Migration: create directory_organizations table (final consolidated shape)
-- Backs the "Organization Directory" section of the Directory Management
-- admin module and the public Directory page's Organization Directory.
-- Category has no CHECK constraint — validated at the application layer
-- against directory_subcategories (module='organization').
-- No hours fields — organizations don't have operating hours in this model.
-- Run this in the Supabase SQL Editor before deploying the Directory
-- Management backend. Run create_directory_categories.sql first.

CREATE TABLE IF NOT EXISTS directory_organizations (
    id              TEXT              PRIMARY KEY,
    name            TEXT              NOT NULL DEFAULT '',
    category        TEXT              NOT NULL DEFAULT 'Community Groups',
    description     TEXT                       DEFAULT '',
    contact_person  TEXT                       DEFAULT '',
    officers        JSONB             NOT NULL DEFAULT '[]'::jsonb,
    contact_details TEXT                       DEFAULT '',
    programs        TEXT                       DEFAULT '',
    location        TEXT                       DEFAULT '',
    lat             DOUBLE PRECISION,
    lng             DOUBLE PRECISION,
    status          TEXT              NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'published', 'hidden')),
    image_url       TEXT                       DEFAULT '',
    featured        BOOLEAN                    DEFAULT false,
    verified        BOOLEAN                    DEFAULT false,
    website         TEXT                       DEFAULT '',
    email           TEXT                       DEFAULT '',
    facebook        TEXT                       DEFAULT '',
    keywords        TEXT                       DEFAULT '',
    gallery         TEXT[]                     DEFAULT '{}',
    created_at      TIMESTAMPTZ       NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ       NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_directory_organizations_status
    ON directory_organizations (status);

-- Disable RLS so the server-side Python client (service role) can read/write freely.
-- This matches the setup of all other tables in this project.
ALTER TABLE directory_organizations DISABLE ROW LEVEL SECURITY;
