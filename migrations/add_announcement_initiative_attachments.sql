-- Migration: optional multi-file Attachments for Announcements and
-- Community Initiatives, separate from and in addition to the existing
-- Featured Image (image_url), which is unchanged.
--
-- Stored as a JSON array of {url, name} objects, mirroring the pattern
-- already used by calendar_activities.photos / calendar_activities.documents.
-- Defaults to an empty array so every existing row keeps rendering exactly
-- as it does today (no attachments section shown until one is added).
-- Run this in the Supabase SQL Editor.

ALTER TABLE announcements          ADD COLUMN IF NOT EXISTS attachments JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE community_initiatives  ADD COLUMN IF NOT EXISTS attachments JSONB NOT NULL DEFAULT '[]'::jsonb;
