-- Migration: Harden users.role for the Root/Administrator split
-- 1. Constrains role to the two known values.
-- 2. Guarantees at the database level that at most one 'root' row can ever
--    exist, as a backstop below the app-level bootstrap check in
--    _ensure_root_user() (server.py) — protects the "permanent, singular
--    Root account" guarantee even against a manual dashboard edit or a
--    future bug.
-- Safe to run any time: every existing row already has role='admin'.
-- Run this in the Supabase SQL Editor.

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
ALTER TABLE users ADD CONSTRAINT users_role_check CHECK (role IN ('admin', 'root'));

CREATE UNIQUE INDEX IF NOT EXISTS uniq_users_single_root
    ON users ((role = 'root'))
    WHERE role = 'root';
