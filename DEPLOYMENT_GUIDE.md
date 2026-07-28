# Transparency Module — Deployment Guide

Reference for the release. **Nothing here has been executed** — run these yourself, in order, when you approve the release.

---

## 0. Pre-flight

Confirm what you're about to ship and that no unrelated/unwanted files sneak in.

```bash
git status
git diff --stat
```

Current uncommitted scope (as of this guide): 15 modified files (`server.py`, `admin/index.html`, `transparency.html`, `assets/css/style.css`, plus 11 other HTML pages carrying earlier session work) and 3 new files (`assets/js/transparency.js`, `images/transparency-seal.png`, `images/transparency-seal1.png`, `migrations/create_transparency_documents.sql`).

**Two untracked items to explicitly exclude — do not add these:**
- `.claude/` (local tooling config, not project code)
- `C:UsersmarloAppDataLocalTempserver_test.log` (stray local log file)
- `backup_css/` — check whether this is a deliberate backup you want kept out of git before staging

---

## 1. Stage, commit, push

Push target is confirmed as **`feature/supabase`** (current branch, tracks `origin/feature/supabase` — this is the branch Render watches, **not** `main`).

```bash
git add about.html admin/index.html announcements.html assets/css/style.css citizens-charter.html contact.html directory.html downloads.html emergency-alert-detail.html index.html officials.html projects.html server.py services.html transparency.html assets/js/transparency.js images/transparency-seal.png images/transparency-seal1.png migrations/create_transparency_documents.sql
git status
```

Review the staged list before committing — confirm nothing unintended is included.

```bash
git commit -m "Add Transparency module: admin-managed multi-document CMS"
git push origin feature/supabase
```

---

## 2. Database migration

This project has no migration runner — SQL files under `migrations/` are applied by hand in the **Supabase SQL Editor** (Project → SQL Editor → paste → Run).

```sql
-- migrations/create_transparency_documents.sql
-- (paste full file contents into the Supabase SQL Editor and run)
```

**Status: already applied.** I confirmed this earlier via live `/api/transparency-documents` responses returning real rows. The `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS` statements are idempotent, so re-running the file is harmless if you want to double check — it will no-op.

Run this in the SQL Editor to confirm the table exists before deploying code that depends on it:

```sql
select count(*) from transparency_documents;
```

---

## 3. Render build / deploy

Service: **`bhob-site-xums`** (`https://bhob-site-xums.onrender.com`, Free tier), watching `mcdeocampo/bhob-site` on branch `feature/supabase`.

- **Build command**: none custom — Render's default Python build runs `pip install -r requirements.txt` automatically.
- **Start command**: `gunicorn server:app --threads 8 --timeout 120` — this is set directly on the Render dashboard (Settings → Start Command) and **overrides** the repo's `Procfile` (which just says `web: gunicorn server:app`). Don't rely on editing the Procfile — if the start command ever needs to change, change it on the dashboard.

If Auto-Deploy is **on** for this service, step 1's `git push` triggers the build automatically — no separate command needed. If Auto-Deploy is **off**, trigger it manually:

```bash
# Render dashboard → bhob-site-xums → Manual Deploy → "Deploy latest commit"
```

(No Render CLI command is used for this project — deploys are triggered via the dashboard.)

---

## 4. Post-deployment steps

- The Transparency nav link is already live in the committed HTML (not commented out), so no separate "unhide nav" step is needed at deploy time.
- No new environment variables are required — the Transparency feature reuses the existing Supabase service-role key and storage bucket (`uploads`, via the existing default) already configured on the service.
- Confirm the `uploads` Supabase storage bucket accepts `.pdf`, `.doc`, `.docx` (it already does for other document-upload features on this site — no bucket policy change expected).

---

## 5. Verification steps

Run these against the live production URL after deploy finishes (allow ~50s for cold start on Free tier if it's been idle):

```bash
curl -s https://huloobando.com/api/transparency-documents | head -c 500
```

- Confirm JSON with real document rows, `status: ok`.
- Load `https://huloobando.com/transparency` in a browser — confirm the 7 categories render, accordion opens/closes, View/Download work on a real document.
- Open browser dev tools → Console — confirm no errors on page load or interaction.
- Log into `/admin` → Transparency section — confirm the document list loads and matches what's in the database.
- Check Render's deploy logs for the service to confirm the build succeeded and gunicorn started without errors.

---

## 6. Rollback steps

**Code rollback** (if the new deploy has a problem):

```bash
git revert HEAD --no-edit
git push origin feature/supabase
```

This pushes a new commit undoing the Transparency changes and lets Render auto-deploy (or manually deploy) the reverted state. Prefer `revert` over `reset --hard` + force-push since the branch is shared/deployed from.

Alternatively, from the Render dashboard: **Deploys tab → select the last known-good deploy → Rollback to this deploy** (no git action required, fastest option under time pressure).

**Database rollback** — only if you need to fully undo the migration (this deletes any documents already uploaded through the admin panel, so confirm with yourself first):

```sql
DROP TABLE IF EXISTS transparency_documents;
```

Since the code checks for an empty document list gracefully (categories render with "No Documents Available"), you can also leave the table in place and roll back only the code — the table being present with no traffic hitting it is harmless.

**Note on the old Render service**: per earlier notes, an older Render service was kept running as an emergency Cloudflare-DNS-repoint rollback target, with a note that it was "safe to delete after ~2026-07-28" (today). Verify in the Render dashboard whether that old service still exists before relying on it as a rollback path — it may already be gone.

---

**Nothing in this guide has been executed.** All git, SQL, and Render actions above are yours to run when you're ready to release.
