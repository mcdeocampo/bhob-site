-- Migration: create Public Services CMS tables
-- Backs the "Public Services" admin module and the public services.html page.
-- Run this in the Supabase SQL Editor before deploying the Public Services
-- CMS backend. Run seed_public_services.sql immediately after to preserve
-- the site's current content.

CREATE TABLE IF NOT EXISTS public_services (
    id                TEXT         PRIMARY KEY,
    title             TEXT         NOT NULL    DEFAULT '',
    short_description TEXT                     DEFAULT '',
    description       TEXT                     DEFAULT '',
    icon_type         TEXT         NOT NULL    DEFAULT 'preset'
                      CHECK (icon_type IN ('preset', 'upload')),
    icon              TEXT                     DEFAULT '',
    banner_image      TEXT                     DEFAULT '',
    processing_time   TEXT                     DEFAULT '',
    fee               TEXT                     DEFAULT '',
    office            TEXT                     DEFAULT '',
    processing_hours  TEXT                     DEFAULT '',
    contact_number    TEXT                     DEFAULT '',
    contact_email     TEXT                     DEFAULT '',
    notes             TEXT                     DEFAULT '',
    status            TEXT         NOT NULL    DEFAULT 'draft'
                      CHECK (status IN ('draft', 'published', 'hidden')),
    display_order     INTEGER      NOT NULL    DEFAULT 0,
    created_by        TEXT                     DEFAULT '',
    updated_by        TEXT                     DEFAULT '',
    created_at        TIMESTAMPTZ  NOT NULL    DEFAULT NOW(),
    updated_at        TIMESTAMPTZ  NOT NULL    DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public_service_requirements (
    id            TEXT    PRIMARY KEY,
    service_id    TEXT    NOT NULL REFERENCES public_services(id) ON DELETE CASCADE,
    requirement   TEXT    NOT NULL DEFAULT '',
    display_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS public_service_steps (
    id               TEXT    PRIMARY KEY,
    service_id       TEXT    NOT NULL REFERENCES public_services(id) ON DELETE CASCADE,
    step_number      INTEGER NOT NULL DEFAULT 0,
    step_description TEXT    NOT NULL DEFAULT '',
    display_order    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS public_service_files (
    id            TEXT    PRIMARY KEY,
    service_id    TEXT    NOT NULL REFERENCES public_services(id) ON DELETE CASCADE,
    filename      TEXT    NOT NULL DEFAULT '',
    filepath      TEXT    NOT NULL DEFAULT '',
    filesize      INTEGER          DEFAULT 0,
    display_order INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_public_services_status ON public_services (status);
CREATE INDEX IF NOT EXISTS idx_psvc_req_service ON public_service_requirements (service_id);
CREATE INDEX IF NOT EXISTS idx_psvc_step_service ON public_service_steps (service_id);
CREATE INDEX IF NOT EXISTS idx_psvc_file_service ON public_service_files (service_id);

-- Disable RLS so the server-side Python client (service role) can read/write freely.
-- This matches the setup of all other tables in this project.
ALTER TABLE public_services DISABLE ROW LEVEL SECURITY;
ALTER TABLE public_service_requirements DISABLE ROW LEVEL SECURITY;
ALTER TABLE public_service_steps DISABLE ROW LEVEL SECURITY;
ALTER TABLE public_service_files DISABLE ROW LEVEL SECURITY;
