-- Migration: create directory_map_locations table (final consolidated shape)
-- Backs the "Community Map" section of the Directory Management admin
-- module and the public Directory page's Community Map.
-- Category has no CHECK constraint — validated at the application layer
-- against directory_subcategories (module='map'), same as every other
-- Directory module.
-- Run this in the Supabase SQL Editor before deploying the Directory
-- Management backend. Run create_directory_categories.sql first.

CREATE TABLE IF NOT EXISTS directory_map_locations (
    id            TEXT              PRIMARY KEY,
    name          TEXT              NOT NULL DEFAULT '',
    category      TEXT              NOT NULL DEFAULT 'Public Facilities',
    description   TEXT                       DEFAULT '',
    address       TEXT                       DEFAULT '',
    contact       TEXT                       DEFAULT '',
    hours         TEXT                       DEFAULT '',
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
    hours_open    TEXT                       DEFAULT '',
    hours_close   TEXT                       DEFAULT '',
    hours_is_24h  BOOLEAN                    DEFAULT false,
    created_at    TIMESTAMPTZ       NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ       NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_directory_map_locations_status
    ON directory_map_locations (status);

-- Disable RLS so the server-side Python client (service role) can read/write freely.
-- This matches the setup of all other tables in this project.
ALTER TABLE directory_map_locations DISABLE ROW LEVEL SECURITY;
