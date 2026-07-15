-- Migration: Enable Row-Level Security on all application tables
-- Supabase's Security Advisor flags every table below as "publicly
-- accessible" because RLS was never enabled — by default, Supabase
-- exposes every table in the public schema over its REST API, and
-- without RLS, anyone with the project's anon key can read, edit, or
-- delete any row directly, completely bypassing this app's Flask
-- backend, its auth checks, and its audit log.
--
-- Safe fix for this app: server.py connects using SUPABASE_SERVICE_KEY
-- (see db.py), and the service-role key bypasses RLS by design.
-- Enabling RLS with NO policies makes each table default-deny for the
-- anon/authenticated roles (the public REST API), while the Flask
-- backend keeps working exactly as before — nothing in this app talks
-- to Supabase directly except server.py.
-- Run this in the Supabase SQL Editor.

ALTER TABLE IF EXISTS announcements ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS calendar_activities ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS community_initiatives ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS directory_businesses ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS directory_category_groups ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS directory_emergency ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS directory_map_locations ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS directory_organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS directory_subcategories ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS ea_resolved_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS emergency_alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS emergency_hotlines ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS forms ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS officials ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public_service_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public_service_requirements ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public_service_steps ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public_services ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS site_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS users ENABLE ROW LEVEL SECURITY;
