"""
Supabase client — server-side only.
SUPABASE_SERVICE_KEY must never be exposed to the browser.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

load_dotenv(Path(__file__).resolve().parent / '.env')

SUPABASE_URL         = os.environ.get('SUPABASE_URL', '').strip()
SUPABASE_SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_KEY', '').strip()

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    raise RuntimeError(
        'SUPABASE_URL and SUPABASE_SERVICE_KEY environment variables must be set.'
    )

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
