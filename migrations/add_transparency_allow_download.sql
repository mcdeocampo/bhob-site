-- Migration: per-document "Allow Download" toggle
-- Status (Draft/Published/Archived) still controls whether a document is
-- public at all — unchanged. This flag only controls whether the Download
-- button shows for an otherwise-public (Published) document: View is
-- always shown; Download shows only when this is true. Defaults to true so
-- every existing document keeps behaving exactly as it does today. Run
-- this in the Supabase SQL Editor.

ALTER TABLE transparency_documents ADD COLUMN IF NOT EXISTS allow_download BOOLEAN NOT NULL DEFAULT TRUE;
