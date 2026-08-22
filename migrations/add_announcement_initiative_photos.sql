-- Migration: multi-photo support for Announcements and Community
-- Initiatives, separate from and in addition to the existing Featured
-- Image (image_url) and Attachments (attachments) columns, both unchanged.
--
-- Stored as a JSON array of {url, name} objects, mirroring the pattern
-- already used by calendar_activities.photos and by attachments above.
-- Defaults to an empty array so every existing row keeps rendering exactly
-- as it does today -- the API layer treats an empty photos array with a
-- non-empty image_url as a single legacy photo, so no backfill/UPDATE is
-- required for existing rows.
-- Run this in the Supabase SQL Editor.

ALTER TABLE announcements          ADD COLUMN IF NOT EXISTS photos JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE community_initiatives  ADD COLUMN IF NOT EXISTS photos JSONB NOT NULL DEFAULT '[]'::jsonb;
