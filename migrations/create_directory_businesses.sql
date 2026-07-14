-- Migration: create directory_businesses table (final consolidated shape)
-- Backs the "Business Directory" section of the Directory Management admin
-- module and the public Directory page's Business Directory.
-- Category has no CHECK constraint — validated at the application layer
-- against directory_subcategories (module='business').
-- Note: `social_link` doubles as the Facebook link for this module — there
-- is no separate facebook column here (matches BBCB Site's convention).
-- Run this in the Supabase SQL Editor before deploying the Directory
-- Management backend. Run create_directory_categories.sql first.

CREATE TABLE IF NOT EXISTS directory_businesses (
    id            TEXT              PRIMARY KEY,
    name          TEXT              NOT NULL DEFAULT '',
    category      TEXT              NOT NULL DEFAULT 'General Services',
    description   TEXT                       DEFAULT '',
    address       TEXT                       DEFAULT '',
    contact       TEXT                       DEFAULT '',
    hours         TEXT                       DEFAULT '',
    image_url     TEXT                       DEFAULT '',
    social_link   TEXT                       DEFAULT '',
    lat           DOUBLE PRECISION,
    lng           DOUBLE PRECISION,
    status        TEXT              NOT NULL DEFAULT 'draft'
                  CHECK (status IN ('draft', 'published', 'hidden')),
    featured      BOOLEAN                    DEFAULT false,
    verified      BOOLEAN                    DEFAULT false,
    website       TEXT                       DEFAULT '',
    email         TEXT                       DEFAULT '',
    keywords      TEXT                       DEFAULT '',
    gallery       TEXT[]                     DEFAULT '{}',
    hours_open    TEXT                       DEFAULT '',
    hours_close   TEXT                       DEFAULT '',
    hours_is_24h  BOOLEAN                    DEFAULT false,
    created_at    TIMESTAMPTZ       NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ       NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_directory_businesses_status
    ON directory_businesses (status);

-- Disable RLS so the server-side Python client (service role) can read/write freely.
-- This matches the setup of all other tables in this project.
ALTER TABLE directory_businesses DISABLE ROW LEVEL SECURITY;
