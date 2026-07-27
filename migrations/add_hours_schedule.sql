-- Migration: add hours_schedule (Phase 1 of the operating-hours consistency fix)
-- Scope: directory_businesses and directory_map_locations ONLY. No other
-- table is touched by this file.
--
-- Problem being fixed: the free-text "Operating Hours" field and the
-- Open/Closed status badge are computed independently today (badge uses a
-- single hours_open/hours_close window applied to every day of the week),
-- so a listing can show contradictory information, e.g. text says
-- "Saturday-Sunday: Closed" while the badge still says "Open" on a Saturday.
--
-- This migration only adds a new column and backfills it from existing data.
-- It does NOT drop, rename, or alter any existing column, and no application
-- code reads hours_schedule yet (that is Phase 2, done in a later, separate
-- change once this step is verified in production). The site keeps running
-- exactly as it does today after this file is applied.
--
-- hours_schedule shape (one entry per day, keyed mon..sun):
--   {
--     "mon": {"closed": false, "is24h": false, "periods": [{"open":"08:00","close":"17:00"}]},
--     "sat": {"closed": true,  "is24h": false, "periods": []},
--     ...
--   }
-- `periods` is an array so a future "multiple opening periods per day"
-- feature (e.g. lunch-break split hours) needs no further schema change —
-- Phase 2 will only ever populate a single entry in it.
--
-- Run this in the Supabase SQL Editor (or via the one-time runner script, if
-- that path is chosen instead - see accompanying implementation notes).

-- Step 1: additive column, safe to run any number of times.
ALTER TABLE directory_businesses    ADD COLUMN IF NOT EXISTS hours_schedule JSONB DEFAULT '{}'::jsonb;
ALTER TABLE directory_map_locations ADD COLUMN IF NOT EXISTS hours_schedule JSONB DEFAULT '{}'::jsonb;

-- Step 2: one-time backfill. Only touches rows that:
--   (a) currently have hours_schedule = '{}' (i.e. not already backfilled —
--       makes this statement safe to re-run without clobbering later edits), AND
--   (b) actually have hours data configured today (hours_is_24h = true, or
--       both hours_open and hours_close set).
-- Rows with no hours data configured at all are left as '{}' — matching
-- today's behavior where computeHoursStatus() shows no badge at all when
-- hours aren't set, rather than inventing a "closed" or "open" state for
-- data that was never entered.
UPDATE directory_businesses b
SET hours_schedule = (
  SELECT jsonb_object_agg(
    d.day,
    CASE
      WHEN b.hours_is_24h THEN jsonb_build_object('closed', false, 'is24h', true, 'periods', '[]'::jsonb)
      ELSE jsonb_build_object('closed', false, 'is24h', false, 'periods',
             jsonb_build_array(jsonb_build_object('open', b.hours_open, 'close', b.hours_close)))
    END
  )
  FROM (VALUES ('mon'),('tue'),('wed'),('thu'),('fri'),('sat'),('sun')) AS d(day)
)
WHERE (hours_schedule = '{}'::jsonb OR hours_schedule IS NULL)
  AND (hours_is_24h = true OR (hours_open <> '' AND hours_close <> ''));

UPDATE directory_map_locations b
SET hours_schedule = (
  SELECT jsonb_object_agg(
    d.day,
    CASE
      WHEN b.hours_is_24h THEN jsonb_build_object('closed', false, 'is24h', true, 'periods', '[]'::jsonb)
      ELSE jsonb_build_object('closed', false, 'is24h', false, 'periods',
             jsonb_build_array(jsonb_build_object('open', b.hours_open, 'close', b.hours_close)))
    END
  )
  FROM (VALUES ('mon'),('tue'),('wed'),('thu'),('fri'),('sat'),('sun')) AS d(day)
)
WHERE (hours_schedule = '{}'::jsonb OR hours_schedule IS NULL)
  AND (hours_is_24h = true OR (hours_open <> '' AND hours_close <> ''));

-- Verification queries (read-only — run these after the above to confirm the
-- backfill landed as expected before moving on to Phase 2):
--
-- SELECT id, name, hours_open, hours_close, hours_is_24h, hours_schedule
--   FROM directory_businesses
--   WHERE hours_is_24h = true OR (hours_open <> '' AND hours_close <> '')
--   ORDER BY name;
--
-- SELECT id, name, hours_open, hours_close, hours_is_24h, hours_schedule
--   FROM directory_map_locations
--   WHERE hours_is_24h = true OR (hours_open <> '' AND hours_close <> '')
--   ORDER BY name;
--
-- Expect: every row's hours_schedule has all 7 day keys, each matching that
-- row's own hours_open/hours_close/hours_is_24h values (or is24h:true when
-- hours_is_24h was true). Rows with blank hours should show hours_schedule = {}.
