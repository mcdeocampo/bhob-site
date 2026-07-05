"""
One-time seed data migration — run locally before first Vercel deploy.
Reads data/seed/*.json and inserts rows into Supabase with ON CONFLICT DO NOTHING.
Never called by server.py. Safe to run multiple times (idempotent).

Usage:
    python migrate_seed.py
"""
import os
import json
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')

from db import supabase  # noqa: E402 — must come after env load


def _read_seed(filename):
    path = os.path.join(BASE_DIR, 'data', 'seed', filename)
    if not os.path.exists(path):
        print(f'  [SKIP] {filename} not found at {path}')
        return []
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def _migrate_announcements():
    print('\n[announcements]')
    rows = _read_seed('announcements.json')
    if not rows:
        return
    for item in rows:
        row = {
            'id':                item['id'],
            'title':             item.get('title', ''),
            'date':              item.get('date', ''),
            'category':          item.get('category', ''),
            'short_description': item.get('shortDescription', ''),
            'full_details':      item.get('fullDetails', ''),
            'image_url':         item.get('imageUrl', ''),
            'status':            item.get('status', 'draft'),
            'featured':          bool(item.get('featured', False)),
            'display_order':     int(item.get('displayOrder', 0)),
            'created_at':        item.get('createdAt', ''),
            'updated_at':        item.get('updatedAt', ''),
        }
        result = supabase.table('announcements').upsert(row, on_conflict='id').execute()
        if hasattr(result, 'error') and result.error:
            print(f'  [ERROR] {item["id"]}: {result.error}')
        else:
            print(f'  [OK] {item["id"]} — {item.get("title", "")}')


def _migrate_initiatives():
    print('\n[community_initiatives]')
    rows = _read_seed('community-initiatives.json')
    if not rows:
        return
    for item in rows:
        row = {
            'id':                item['id'],
            'title':             item.get('title', ''),
            'category':          item.get('category', ''),
            'subtitle':          item.get('subtitle', ''),
            'short_description': item.get('shortDescription', ''),
            'full_details':      item.get('fullDetails', ''),
            'image_url':         item.get('imageUrl', ''),
            'status':            item.get('status', 'draft'),
            'featured':          bool(item.get('featured', False)),
            'display_order':     int(item.get('displayOrder', 0)),
            'button_label':      item.get('buttonLabel', ''),
            'button_link':       item.get('buttonLink', ''),
            'created_at':        item.get('createdAt', ''),
            'updated_at':        item.get('updatedAt', ''),
        }
        result = supabase.table('community_initiatives').upsert(row, on_conflict='id').execute()
        if hasattr(result, 'error') and result.error:
            print(f'  [ERROR] {item["id"]}: {result.error}')
        else:
            print(f'  [OK] {item["id"]} — {item.get("title", "")}')


def _migrate_forms():
    print('\n[forms]')
    rows = _read_seed('forms.json')
    if not rows:
        return
    for item in rows:
        row = {
            'id':            item['id'],
            'title':         item.get('title', ''),
            'description':   item.get('description', ''),
            'file_url':      item.get('fileUrl', ''),
            'file_name':     item.get('fileName', ''),
            'file_type':     item.get('fileType', ''),
            'file_size':     int(item.get('fileSize', 0)),
            'status':        item.get('status', 'draft'),
            'display_order': int(item.get('displayOrder', 0)),
            'created_at':    item.get('createdAt', ''),
            'updated_at':    item.get('updatedAt', ''),
        }
        result = supabase.table('forms').upsert(row, on_conflict='id').execute()
        if hasattr(result, 'error') and result.error:
            print(f'  [ERROR] {item["id"]}: {result.error}')
        else:
            print(f'  [OK] {item["id"]} — {item.get("title", "")}')


if __name__ == '__main__':
    print('=== BHOB Seed Migration ===')
    print('Inserting seed data into Supabase (existing rows are skipped).')
    _migrate_announcements()
    _migrate_initiatives()
    _migrate_forms()
    print('\n=== Done ===')
    print('Seed data inserted. Run the app and log in to verify.')
