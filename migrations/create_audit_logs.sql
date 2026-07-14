-- Migration: Audit Log
-- Records authentication events (login success/failure, logout, password
-- changes) for every account, including the hidden Root account. Backs the
-- re-enabled _audit() in server.py, which was previously a no-op stub.
-- Run this in the Supabase SQL Editor.

CREATE TABLE IF NOT EXISTS audit_logs (
    id         TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    message    TEXT NOT NULL DEFAULT '',
    user_id    TEXT,
    username   TEXT,
    role       TEXT,
    success    BOOLEAN NOT NULL DEFAULT true,
    ip_address TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs (user_id);
