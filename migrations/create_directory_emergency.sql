-- Migration: create directory_emergency table (final consolidated shape)
-- Backs the "Emergency Directory" section of the Directory Management admin
-- module and the public Directory page's Emergency Directory.
-- Category has no CHECK constraint — validated at the application layer
-- against directory_subcategories (module='emergency').
-- No hours fields — emergency contacts don't have operating hours in this model.
-- Run this in the Supabase SQL Editor before deploying the Directory
-- Management backend. Run create_directory_categories.sql first.

CREATE TABLE IF NOT EXISTS directory_emergency (
    id            TEXT              PRIMARY KEY,
    name          TEXT              NOT NULL DEFAULT '',
    category      TEXT              NOT NULL DEFAULT 'Emergency Contacts',
    number        TEXT                       DEFAULT '',
    alt_number    TEXT                       DEFAULT '',
    address       TEXT                       DEFAULT '',
    services      TEXT                       DEFAULT '',
    lat           DOUBLE PRECISION,
    lng           DOUBLE PRECISION,
    status        TEXT              NOT NULL DEFAULT 'draft'
                  CHECK (status IN ('draft', 'published', 'hidden')),
    image_url     TEXT                       DEFAULT '',
    featured      BOOLEAN                    DEFAULT false,
    verified      BOOLEAN                    DEFAULT false,
    website       TEXT                       DEFAULT '',
    email         TEXT                       DEFAULT '',
    facebook      TEXT                       DEFAULT '',
    keywords      TEXT                       DEFAULT '',
    gallery       TEXT[]                     DEFAULT '{}',
    created_at    TIMESTAMPTZ       NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ       NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_directory_emergency_status
    ON directory_emergency (status);

-- Disable RLS so the server-side Python client (service role) can read/write freely.
-- This matches the setup of all other tables in this project.
ALTER TABLE directory_emergency DISABLE ROW LEVEL SECURITY;
