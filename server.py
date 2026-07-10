"""
BHOB Site — Flask server
Serves static files, weather/tide proxy, announcement management API, and secure admin auth.
Data layer: Supabase Postgres + Supabase Storage.
"""
import os
import json
import time
import uuid
import hashlib
import hmac
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from functools import wraps
from flask import Flask, jsonify, send_from_directory, abort, request, session, redirect

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Security constants ────────────────────────────────────────────────────────
MAX_FAILED_ATTEMPTS  = 5
LOCKOUT_MINUTES      = 15
SESSION_IDLE_MINUTES = 60
PW_ITERATIONS        = 600000   # PBKDF2-SHA256 iteration count
SALT_BYTES           = 32

COMMON_PASSWORDS = {
    'password', 'password1', 'password12', 'password123', 'password1234',
    'password!', 'password@123',
    'admin', 'admin123', 'admin1234', 'admin@123', 'administrator',
    'barangay', 'barangay1', 'barangay123', 'barangay2025', 'barangay2026',
    'qwerty', 'qwerty1', 'qwerty123', 'qwerty!', 'qwerty@123',
    '12345678', '123456789', '1234567890', '12345678!',
    'letmein', 'letmein1', 'letmein!',
    'welcome', 'welcome1', 'welcome123', 'welcome!',
    'iloveyou', 'sunshine', 'sunshine1',
    'obando', 'obando123', 'hulo', 'hulo123', 'bulacan', 'bulacan123',
}


def _load_env(path):
    """Minimal .env loader — no external dependency required."""
    if not os.path.exists(path):
        return
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, val = line.partition('=')
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            os.environ.setdefault(key, val)


_load_env(os.path.join(BASE_DIR, '.env'))

# Import Supabase client after env is loaded
from db import supabase  # noqa: E402

# Supabase Storage bucket name
STORAGE_BUCKET = os.environ.get('SUPABASE_STORAGE_BUCKET', 'uploads')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or uuid.uuid4().hex

# Secure session cookie settings
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
# Enable in production (HTTPS): app.config['SESSION_COOKIE_SECURE'] = True

# ── Fixed coordinates — Barangay Hulo, Obando, Bulacan ───────────────────────
TIDE_LAT = 14.7201
TIDE_LON  = 120.9284

# ── Server-side caches ────────────────────────────────────────────────────────
_tide_cache    = {'data': None, 'ts': 0}
TIDE_TTL       = 30 * 60
_weather_cache = {'data': None, 'ts': 0}
WEATHER_TTL    = 10 * 60

WMO_LABELS = {
    0: 'Clear Sky', 1: 'Mainly Clear', 2: 'Partly Cloudy', 3: 'Overcast',
    45: 'Fog', 48: 'Icy Fog', 51: 'Light Drizzle', 53: 'Drizzle',
    55: 'Heavy Drizzle', 61: 'Slight Rain', 63: 'Moderate Rain', 65: 'Heavy Rain',
    71: 'Light Snow', 73: 'Snow', 75: 'Heavy Snow',
    80: 'Slight Rain Showers', 81: 'Moderate Rain Showers', 82: 'Violent Rain Showers',
    95: 'Thunderstorm', 96: 'Thunderstorm', 99: 'Thunderstorm',
}


def _manila_now():
    return datetime.now(timezone.utc) + timedelta(hours=8)


def _wttr_color(code):
    c = int(code)
    if c == 113:                  return '#fbbf24'
    if c == 116:                  return '#93c5fd'
    if c in (119, 122):           return '#94a3b8'
    if c in (143, 248, 260):      return '#cbd5e1'
    if 176 <= c <= 314:           return '#60a5fa'
    if c in (386, 389, 392, 395): return '#a855f7'
    if 323 <= c <= 377:           return '#e2e8f0'
    return 'rgba(255,255,255,0.80)'


# ── Password hashing ──────────────────────────────────────────────────────────
def _hash_pw(password):
    """Hash a password using PBKDF2-SHA256. Format: iterations:salt_hex:hash_hex"""
    salt = os.urandom(SALT_BYTES).hex()
    h = hashlib.pbkdf2_hmac(
        'sha256', password.encode('utf-8'), salt.encode('utf-8'), PW_ITERATIONS
    ).hex()
    return f'{PW_ITERATIONS}:{salt}:{h}'


def _check_pw(password, stored):
    """Verify a password against a stored hash. Always timing-safe."""
    try:
        parts = stored.split(':', 2)
        iterations = int(parts[0])
        salt = parts[1]
        expected = parts[2]
        actual = hashlib.pbkdf2_hmac(
            'sha256', password.encode('utf-8'), salt.encode('utf-8'), iterations
        ).hex()
        return hmac.compare_digest(expected, actual)
    except Exception:
        return False


def _validate_pw_strength(password, username='', email=''):
    """
    Validate password against strength policy.
    Returns (ok: bool, error_message: str).
    Never logs or returns the password itself.
    """
    if len(password) < 10:
        return False, 'Password must be at least 10 characters.'
    if not re.search(r'[A-Z]', password):
        return False, 'Password must contain at least one uppercase letter (A-Z).'
    if not re.search(r'[a-z]', password):
        return False, 'Password must contain at least one lowercase letter (a-z).'
    if not re.search(r'[0-9]', password):
        return False, 'Password must contain at least one number (0-9).'
    if not re.search(r'[^A-Za-z0-9]', password):
        return False, 'Password must contain at least one special character (e.g. !@#$%).'
    if password.lower() in COMMON_PASSWORDS:
        return False, 'Password is too common. Please choose a stronger password.'
    if username and len(username) >= 3 and username.lower() in password.lower():
        return False, 'Password must not contain your username.'
    if email:
        local = email.split('@')[0].lower()
        if local and len(local) >= 3 and local in password.lower():
            return False, 'Password must not contain part of your email address.'
    return True, ''


# ── Row mappers — Postgres snake_case → camelCase dicts ──────────────────────
def _row_to_ann(row):
    return {
        'id':               row['id'],
        'title':            row.get('title', ''),
        'date':             row.get('date', ''),
        'category':         row.get('category', ''),
        'shortDescription': row.get('short_description', ''),
        'fullDetails':      row.get('full_details', ''),
        'imageUrl':         row.get('image_url', ''),
        'status':           row.get('status', 'draft'),
        'featured':         bool(row.get('featured', False)),
        'displayOrder':     row.get('display_order', 0),
        'createdAt':        row.get('created_at', ''),
        'updatedAt':        row.get('updated_at', ''),
    }


def _row_to_proj(row):
    return {
        'id':               row['id'],
        'title':            row.get('title', ''),
        'category':         row.get('category', ''),
        'subtitle':         row.get('subtitle', ''),
        'shortDescription': row.get('short_description', ''),
        'fullDetails':      row.get('full_details', ''),
        'imageUrl':         row.get('image_url', ''),
        'status':           row.get('status', 'draft'),
        'featured':         bool(row.get('featured', False)),
        'displayOrder':     row.get('display_order', 0),
        'buttonLabel':      row.get('button_label', ''),
        'buttonLink':       row.get('button_link', ''),
        'createdAt':        row.get('created_at', ''),
        'updatedAt':        row.get('updated_at', ''),
    }


def _row_to_form(row):
    file_url = row.get('file_url', '')
    return {
        'id':            row['id'],
        'title':         row.get('title', ''),
        'description':   row.get('description', ''),
        'fileUrl':       file_url,
        'fileName':      row.get('file_name', ''),
        'fileType':      row.get('file_type', ''),
        'fileSize':      row.get('file_size', 0),
        'status':        row.get('status', 'draft'),
        'displayOrder':  row.get('display_order', 0),
        'createdAt':     row.get('created_at', ''),
        'updatedAt':     row.get('updated_at', ''),
        'fileAvailable': bool(file_url),
    }


def _row_to_user(row):
    return {
        'id':                  row['id'],
        'fullName':            row.get('full_name', ''),
        'username':            row.get('username', ''),
        'email':               row.get('email', ''),
        'passwordHash':        row.get('password_hash', ''),
        'role':                row.get('role', 'admin'),
        'status':              row.get('status', 'active'),
        'forcePasswordChange': bool(row.get('force_password_change', False)),
        'failedLoginCount':    row.get('failed_login_count', 0),
        'lockedUntil':         row.get('locked_until'),
        'lastLoginAt':         row.get('last_login_at'),
        'createdAt':           row.get('created_at', ''),
        'updatedAt':           row.get('updated_at', ''),
    }


# ── User management (Supabase) ────────────────────────────────────────────────
def _get_user_by_username(username):
    try:
        res = (supabase.table('users')
               .select('*')
               .ilike('username', username.strip())
               .limit(1)
               .execute())
        if res.data:
            return _row_to_user(res.data[0])
    except Exception:
        pass
    return None


def _get_user_by_id(uid):
    if not uid:
        return None
    try:
        res = (supabase.table('users')
               .select('*')
               .eq('id', uid)
               .limit(1)
               .execute())
        if res.data:
            return _row_to_user(res.data[0])
    except Exception:
        pass
    return None


def _update_user(updated_user):
    """Persist changes to a single user record."""
    now = datetime.now(timezone.utc).isoformat()
    patch = {
        'full_name':             updated_user.get('fullName', ''),
        'username':              updated_user.get('username', ''),
        'email':                 updated_user.get('email', ''),
        'password_hash':         updated_user.get('passwordHash', ''),
        'role':                  updated_user.get('role', 'admin'),
        'status':                updated_user.get('status', 'active'),
        'force_password_change': bool(updated_user.get('forcePasswordChange', False)),
        'failed_login_count':    updated_user.get('failedLoginCount', 0),
        'locked_until':          updated_user.get('lockedUntil'),
        'last_login_at':         updated_user.get('lastLoginAt'),
        'updated_at':            now,
    }
    try:
        res = (supabase.table('users')
               .update(patch)
               .eq('id', updated_user['id'])
               .execute())
        return bool(res.data)
    except Exception:
        return False



# Contact form — in-memory rate limit store (IP → last submission timestamp)
_contact_rate: dict = {}
_CONTACT_COOLDOWN = 60  # seconds

@app.route('/api/contact', methods=['POST'])
def api_contact():
    data = request.get_json(silent=True) or {}
    # Honeypot: bots fill the hidden "website" field; humans never see it
    if data.get('website', ''):
        return jsonify({'success': True})  # silently discard
    name = str(data.get('name', '')).strip()
    email = str(data.get('email', '')).strip()
    phone = str(data.get('phone', '')).strip()
    subject = str(data.get('subject', '')).strip()
    message = str(data.get('message', '')).strip()
    if not name or not email or not message:
        return jsonify({'success': False, 'error': 'Missing fields'}), 400
    # Rate limit: 1 submission per IP per minute
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
    now = time.time()
    last = _contact_rate.get(ip, 0)
    if now - last < _CONTACT_COOLDOWN:
        wait = int(_CONTACT_COOLDOWN - (now - last))
        return jsonify({'success': False, 'error': f'Please wait {wait}s before submitting again.'}), 429
    _contact_rate[ip] = now
    print('[contact] Starting, key exists:', bool(os.environ.get('BREVO_API_KEY')), flush=True)
    key = os.environ.get('BREVO_API_KEY', '')
    if not key:
        return jsonify({'success': False, 'error': 'Not configured'}), 500
    se = os.environ.get('BREVO_SENDER_EMAIL', 'web@huloobando.com')
    sn = os.environ.get('BREVO_SENDER_NAME', 'Barangay Hulo')
    ae = os.environ.get('ADMIN_EMAIL', 'contact@huloobando.com')
    pe = os.environ.get('PUBLIC_CONTACT_EMAIL', 'contact@huloobando.com')
    def send(p):
        req = urllib.request.Request(
            'https://api.brevo.com/v3/smtp/email',
            json.dumps(p).encode(),
            {'Content-Type': 'application/json', 'api-key': key},
            method='POST'
        )
        try:
            urllib.request.urlopen(req, timeout=10)
        except urllib.error.HTTPError as http_err:
            body = http_err.read().decode('utf-8', errors='replace')
            print(f'[contact] Brevo API error {http_err.code}: {body}', flush=True)
            raise RuntimeError(f'Brevo {http_err.code}: {body}') from http_err
    import html as _html
    from datetime import datetime, timezone, timedelta
    _ph_tz = timezone(timedelta(hours=8))
    _submitted = datetime.now(_ph_tz).strftime('%B %d, %Y at %I:%M %p (Philippine Standard Time)')
    try:
        def _esc(s): return _html.escape(str(s))
        _phone_display = _esc(phone) if phone else '&mdash;'
        _msg_html = _esc(message).replace('\n', '<br>')
        _field = (
            lambda label, content:
            '<table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:12px"><tr>'
            '<td style="background:#f8fafc;border-left:4px solid #2563eb;border-radius:0 8px 8px 0;padding:12px 16px">'
            '<p style="margin:0 0 3px;font-size:11px;font-weight:700;color:#64748b">' + label + '</p>'
            '<p style="margin:0;font-size:15px;color:#1e293b;font-weight:600">' + content + '</p>'
            '</td></tr></table>'
        )
        admin_html = (
            '<!DOCTYPE html><html><head><meta charset="UTF-8"></head>'
            '<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif">'
            '<table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:32px 16px"><tr><td align="center">'
            '<table cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,.08)">'
            '<tr><td style="background:linear-gradient(135deg,#1e3a5f,#2563eb);padding:28px 32px;text-align:center">'
            '<div style="font-size:28px;margin-bottom:6px">&#x1F4E9;</div>'
            '<h1 style="margin:0;color:#fff;font-size:20px;font-weight:700">New Website Inquiry</h1>'
            '<p style="margin:8px 0 0;color:rgba(255,255,255,.82);font-size:13px">A new inquiry has been submitted through the <strong>Barangay Hulo Official Website</strong>.</p>'
            '</td></tr>'
            '<tr><td style="padding:28px 32px 20px">'
            + _field('Name', _esc(name))
            + _field('Email Address', '<a href="mailto:' + _esc(email) + '" style="color:#2563eb;text-decoration:none;font-weight:600">' + _esc(email) + '</a>')
            + _field('Phone Number', _phone_display)
            + _field('Subject', _esc(subject))
            + '<table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:20px"><tr>'
            '<td style="background:#f8fafc;border-left:4px solid #2563eb;border-radius:0 8px 8px 0;padding:8px 14px">'
            '<p style="margin:0 0 3px;font-size:11px;font-weight:700;color:#64748b">Message</p>'
            '<p style="margin:0;font-size:14px;color:#1e293b;line-height:1.7">' + _msg_html + '</p>'
            '</td></tr></table>'
            '<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f9ff;border-radius:8px;margin-bottom:16px"><tr>'
            '<td style="padding:14px 16px">'
            '<p style="margin:0 0 6px;font-size:13px;color:#475569"><strong>&#128197; Submitted:</strong> ' + _submitted + '</p>'
            '<p style="margin:0;font-size:13px;color:#475569"><strong>&#127760; Source:</strong> Barangay Hulo Official Website</p>'
            '</td></tr></table>'
            '<p style="margin:0;font-size:13px;color:#1e293b;font-style:italic">&#128172; Please click <strong>Reply</strong> to respond directly to the resident.</p>'
            '</td></tr>'
            '<tr><td style="background:#f8fafc;border-top:1px solid #e2e8f0;padding:16px 32px;text-align:center">'
            '<p style="margin:0;font-size:11px;color:#94a3b8;line-height:1.7">'
            'This is an automated notification from the Barangay Hulo Digital Platform.<br>'
            'Please do not reply directly to this automated email.</p>'
            '</td></tr>'
            '</table></td></tr></table></body></html>'
        )
        send({'sender': {'name': sn, 'email': se}, 'to': [{'email': ae}], 'replyTo': {'email': email, 'name': name}, 'subject': 'New Inquiry – ' + subject, 'htmlContent': admin_html})
        print(f'[contact] Admin notification sent to {ae}', flush=True)
    except Exception as e:
        import traceback
        print('[contact] FAILED (admin email):', traceback.format_exc(), flush=True)
        return jsonify({'success': False, 'error': str(e)}), 500
    import html as _html2
    def _esc2(s): return _html2.escape(str(s))
    ack_html = (
        '<!DOCTYPE html><html><head><meta charset="UTF-8"></head>'
        '<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif">'
        '<table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:32px 16px"><tr><td align="center">'
        '<table cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,.08)">'
        # Header
        '<tr><td style="background:linear-gradient(135deg,#1e3a5f,#2563eb);padding:28px 32px;text-align:center">'
        '<div style="font-size:28px;margin-bottom:6px">&#x2705;</div>'
        '<h1 style="margin:0;color:#fff;font-size:20px;font-weight:700">Inquiry Received</h1>'
        '<p style="margin:8px 0 0;color:rgba(255,255,255,.82);font-size:13px">Barangay Hulo &mdash; Obando, Bulacan</p>'
        '</td></tr>'
        # Body
        '<tr><td style="padding:28px 32px 20px">'
        '<p style="margin:0 0 16px;font-size:15px;color:#1e293b">Dear <strong>' + _esc2(name) + '</strong>,</p>'
        '<p style="margin:0 0 14px;font-size:14px;color:#475569;line-height:1.7">'
        'Thank you for reaching out to the <strong>Barangay Hulo Office</strong> through our official website. '
        'This email confirms that we have successfully received your inquiry.</p>'
        '<p style="margin:0 0 20px;font-size:14px;color:#475569;line-height:1.7">'
        'Our team will carefully review your submission and respond as soon as possible during official office hours. '
        'If additional information is needed, we will reach you using the contact details you provided.</p>'
        # Confirmation card
        '<table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:20px"><tr>'
        '<td style="background:#f0f9ff;border-left:4px solid #2563eb;border-radius:0 8px 8px 0;padding:14px 18px">'
        '<p style="margin:0 0 4px;font-size:13px;font-weight:700;color:#1e3a5f">Your Inquiry Summary</p>'
        '<p style="margin:0 0 3px;font-size:13px;color:#475569"><strong>Subject:</strong> ' + _esc2(subject) + '</p>'
        '<p style="margin:0 0 3px;font-size:13px;color:#475569"><strong>Submitted:</strong> ' + _submitted + '</p>'
        '<p style="margin:0;font-size:13px;color:#475569"><strong>Submitted to:</strong> Barangay Hulo Office</p>'
        '</td></tr></table>'
        # Urgent contact
        '<table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:20px"><tr>'
        '<td style="background:#fff7ed;border-left:4px solid #f59e0b;border-radius:0 8px 8px 0;padding:14px 18px">'
        '<p style="margin:0 0 4px;font-size:13px;font-weight:700;color:#92400e">For Urgent Concerns</p>'
        '<p style="margin:0;font-size:13px;color:#78350f;line-height:1.6">'
        'If your concern requires immediate assistance, please contact us directly at '
        '<a href="mailto:contact@huloobando.com" style="color:#2563eb;text-decoration:none;font-weight:600">contact@huloobando.com</a> '
        'or visit the Barangay Hall during office hours.</p>'
        '</td></tr></table>'
        '<p style="margin:0 0 4px;font-size:14px;color:#475569;line-height:1.7">'
        'We appreciate your patience and thank you for helping us serve the community better.</p>'
        '</td></tr>'
        # Signature
        '<tr><td style="padding:0 32px 28px">'
        '<p style="margin:0;font-size:14px;color:#1e293b;line-height:1.8">'
        '<strong>Sincerely,</strong><br>'
        '<strong style="color:#1e3a5f">Barangay Hulo</strong><br>'
        '<span style="color:#64748b;font-size:13px">Municipality of Obando, Bulacan<br>'
        'Official Barangay Digital Platform</span></p>'
        '</td></tr>'
        # Footer
        '<tr><td style="background:#f8fafc;border-top:1px solid #e2e8f0;padding:16px 32px;text-align:center">'
        '<p style="margin:0;font-size:11px;color:#94a3b8;line-height:1.7">'
        'This is an automated acknowledgement from the Barangay Hulo Digital Platform.<br>'
        'For additional questions, simply reply to this email or contact us at '
        '<a href="mailto:contact@huloobando.com" style="color:#2563eb;text-decoration:none">contact@huloobando.com</a>.'
        '</p>'
        '</td></tr>'
        '</table></td></tr></table></body></html>'
    )
    try:
        send({'sender': {'name': sn, 'email': se}, 'to': [{'email': email, 'name': name}], 'replyTo': {'email': pe, 'name': sn}, 'subject': 'We Have Received Your Inquiry – Barangay Hulo', 'htmlContent': ack_html})
        print(f'[contact] Acknowledgment sent to {email}', flush=True)
    except Exception:
        import traceback
        print('[contact] WARNING: acknowledgment email failed (admin email was sent):', traceback.format_exc(), flush=True)
    return jsonify({'success': True})

def _ensure_initial_user():
    """
    Create the initial admin account only when no users exist in Supabase.
    Never called when users already exist — never resets a changed password.
    """
    try:
        res = supabase.table('users').select('id').limit(1).execute()
        if res.data:
            return
    except Exception as exc:
        print(f'[BHOB] WARNING: Could not check users table: {exc}')
        return

    username  = os.environ.get('ADMIN_USERNAME', 'admin')
    plain_pw  = os.environ.get('ADMIN_PASSWORD', '')
    force_pw  = True
    if not plain_pw:
        plain_pw = f'Barangay@{datetime.now().year}'
        print('[BHOB] -------------------------------------------------')
        print('[BHOB] WARNING: No ADMIN_PASSWORD set.')
        print(f'[BHOB] Auto-generated password: {plain_pw}')
        print('[BHOB] Log in and change your password immediately.')
    else:
        print('[BHOB] -------------------------------------------------')
        print('[BHOB] Admin account created from ADMIN_PASSWORD env var.')
        print(f'[BHOB] Username : {username}')
        print('[BHOB] Log in and change your password immediately.')
    pw_hash = _hash_pw(plain_pw)
    print('[BHOB] -------------------------------------------------')

    now = datetime.now(timezone.utc).isoformat()
    row = {
        'id':                    uuid.uuid4().hex,
        'full_name':             'Barangay Admin',
        'username':              username,
        'email':                 '',
        'password_hash':         pw_hash,
        'role':                  'admin',
        'status':                'active',
        'force_password_change': force_pw,
        'failed_login_count':    0,
        'locked_until':          None,
        'last_login_at':         None,
        'created_at':            now,
        'updated_at':            now,
    }
    try:
        supabase.table('users').insert(row).execute()
        print(f'[BHOB] Initial admin user created: {username}')
    except Exception as exc:
        print(f'[BHOB] ERROR: Could not create initial admin user: {exc}')


# ── Audit logging — no-op (temporarily disabled; restore after migration stable) ──
def _audit(*args, **kwargs):
    pass


# ── Session helpers ───────────────────────────────────────────────────────────
def _session_valid():
    """
    Return True if the current session is authenticated and not idle-expired.
    Updates last_active on each valid check (sliding window).
    """
    if not session.get('admin_logged_in'):
        return False
    last = session.get('last_active', 0)
    if time.time() - last > SESSION_IDLE_MINUTES * 60:
        session.clear()
        return False
    session['last_active'] = time.time()
    return True


# ── Auth decorators ───────────────────────────────────────────────────────────
def admin_required(f):
    """
    Full admin guard: session valid + user active + forcePasswordChange NOT set.
    Use on all admin API routes except change-password.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _session_valid():
            return jsonify({'error': 'unauthorized'}), 401
        user = _get_user_by_id(session.get('admin_user_id'))
        if not user or user.get('status') != 'active':
            session.clear()
            return jsonify({'error': 'unauthorized'}), 401
        if user.get('forcePasswordChange', False):
            return jsonify({
                'error': 'password_change_required',
                'message': 'You must change your password before continuing.',
            }), 403
        return f(*args, **kwargs)
    return decorated


def admin_auth_only(f):
    """
    Auth guard without forcePasswordChange enforcement.
    Use on /admin/api/change-password so admins can change during forced-change flow.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _session_valid():
            return jsonify({'error': 'unauthorized'}), 401
        user = _get_user_by_id(session.get('admin_user_id'))
        if not user or user.get('status') != 'active':
            session.clear()
            return jsonify({'error': 'unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated


# ── General helpers ───────────────────────────────────────────────────────────
def _clean(val, maxlen=500):
    return str(val or '').strip()[:maxlen]


def _order_key(item):
    """Safe displayOrder sort key — None/missing items sort last."""
    v = item.get('displayOrder')
    return v if isinstance(v, (int, float)) else 9999


# ── Announcement data helpers (Supabase) ──────────────────────────────────────
def _load_ann():
    try:
        res = supabase.table('announcements').select('*').execute()
        return [_row_to_ann(r) for r in (res.data or [])]
    except Exception:
        return []


def _ann_create(ann_dict):
    row = {
        'id':                ann_dict['id'],
        'title':             ann_dict.get('title', ''),
        'date':              ann_dict.get('date', ''),
        'category':          ann_dict.get('category', ''),
        'short_description': ann_dict.get('shortDescription', ''),
        'full_details':      ann_dict.get('fullDetails', ''),
        'image_url':         ann_dict.get('imageUrl', ''),
        'status':            ann_dict.get('status', 'draft'),
        'featured':          bool(ann_dict.get('featured', False)),
        'display_order':     int(ann_dict.get('displayOrder', 0)),
        'created_at':        ann_dict.get('createdAt', ''),
        'updated_at':        ann_dict.get('updatedAt', ''),
    }
    res = supabase.table('announcements').insert(row).execute()
    return _row_to_ann(res.data[0]) if res.data else ann_dict


def _ann_update(ann_id, patch_dict):
    now = datetime.now(timezone.utc).isoformat()
    row = {'updated_at': now}
    field_map = {
        'title': 'title', 'date': 'date', 'category': 'category',
        'shortDescription': 'short_description', 'fullDetails': 'full_details',
        'imageUrl': 'image_url', 'status': 'status',
        'featured': 'featured', 'displayOrder': 'display_order',
    }
    for camel, snake in field_map.items():
        if camel in patch_dict:
            row[snake] = patch_dict[camel]
    res = (supabase.table('announcements')
           .update(row)
           .eq('id', ann_id)
           .execute())
    return _row_to_ann(res.data[0]) if res.data else None


def _ann_delete(ann_id):
    res = supabase.table('announcements').delete().eq('id', ann_id).execute()
    return bool(res.data)


def _ann_bulk_order(order_map):
    now = datetime.now(timezone.utc).isoformat()
    for ann_id, order in order_map.items():
        supabase.table('announcements').update(
            {'display_order': order, 'updated_at': now}
        ).eq('id', ann_id).execute()


# ── Community initiatives data helpers (Supabase) ────────────────────────────
def _load_proj():
    try:
        res = supabase.table('community_initiatives').select('*').execute()
        return [_row_to_proj(r) for r in (res.data or [])]
    except Exception:
        return []


def _proj_create(proj_dict):
    row = {
        'id':                proj_dict['id'],
        'title':             proj_dict.get('title', ''),
        'category':          proj_dict.get('category', ''),
        'subtitle':          proj_dict.get('subtitle', ''),
        'short_description': proj_dict.get('shortDescription', ''),
        'full_details':      proj_dict.get('fullDetails', ''),
        'image_url':         proj_dict.get('imageUrl', ''),
        'status':            proj_dict.get('status', 'draft'),
        'featured':          bool(proj_dict.get('featured', False)),
        'display_order':     int(proj_dict.get('displayOrder', 0)),
        'button_label':      proj_dict.get('buttonLabel', ''),
        'button_link':       proj_dict.get('buttonLink', ''),
        'created_at':        proj_dict.get('createdAt', ''),
        'updated_at':        proj_dict.get('updatedAt', ''),
    }
    res = supabase.table('community_initiatives').insert(row).execute()
    return _row_to_proj(res.data[0]) if res.data else proj_dict


def _proj_update(proj_id, patch_dict):
    now = datetime.now(timezone.utc).isoformat()
    row = {'updated_at': now}
    field_map = {
        'title': 'title', 'category': 'category', 'subtitle': 'subtitle',
        'shortDescription': 'short_description', 'fullDetails': 'full_details',
        'imageUrl': 'image_url', 'status': 'status',
        'featured': 'featured', 'displayOrder': 'display_order',
        'buttonLabel': 'button_label', 'buttonLink': 'button_link',
    }
    for camel, snake in field_map.items():
        if camel in patch_dict:
            row[snake] = patch_dict[camel]
    res = (supabase.table('community_initiatives')
           .update(row)
           .eq('id', proj_id)
           .execute())
    return _row_to_proj(res.data[0]) if res.data else None


def _proj_delete(proj_id):
    res = supabase.table('community_initiatives').delete().eq('id', proj_id).execute()
    return bool(res.data)


def _proj_bulk_order(order_map):
    now = datetime.now(timezone.utc).isoformat()
    for proj_id, order in order_map.items():
        supabase.table('community_initiatives').update(
            {'display_order': order, 'updated_at': now}
        ).eq('id', proj_id).execute()


# ── Forms data helpers (Supabase) ─────────────────────────────────────────────
def _load_forms():
    try:
        res = supabase.table('forms').select('*').execute()
        return [_row_to_form(r) for r in (res.data or [])]
    except Exception:
        return []


def _form_create(form_dict):
    row = {
        'id':            form_dict['id'],
        'title':         form_dict.get('title', ''),
        'description':   form_dict.get('description', ''),
        'file_url':      form_dict.get('fileUrl', ''),
        'file_name':     form_dict.get('fileName', ''),
        'file_type':     form_dict.get('fileType', ''),
        'file_size':     int(form_dict.get('fileSize', 0)),
        'status':        form_dict.get('status', 'draft'),
        'display_order': int(form_dict.get('displayOrder', 0)),
        'created_at':    form_dict.get('createdAt', ''),
        'updated_at':    form_dict.get('updatedAt', ''),
    }
    res = supabase.table('forms').insert(row).execute()
    return _row_to_form(res.data[0]) if res.data else form_dict


def _form_update(form_id, patch_dict):
    now = datetime.now(timezone.utc).isoformat()
    row = {'updated_at': now}
    field_map = {
        'title': 'title', 'description': 'description',
        'fileUrl': 'file_url', 'fileName': 'file_name',
        'fileType': 'file_type', 'fileSize': 'file_size',
        'status': 'status', 'displayOrder': 'display_order',
    }
    for camel, snake in field_map.items():
        if camel in patch_dict:
            row[snake] = patch_dict[camel]
    res = (supabase.table('forms')
           .update(row)
           .eq('id', form_id)
           .execute())
    return _row_to_form(res.data[0]) if res.data else None


def _form_delete(form_id):
    res = supabase.table('forms').delete().eq('id', form_id).execute()
    return bool(res.data)


def _form_bulk_order(order_map):
    now = datetime.now(timezone.utc).isoformat()
    for form_id, order in order_map.items():
        supabase.table('forms').update(
            {'display_order': order, 'updated_at': now}
        ).eq('id', form_id).execute()


# ── Officials helpers ─────────────────────────────────────────────────────────
def _row_to_official(row):
    return {
        'id':              row['id'],
        'fullName':        row.get('full_name', ''),
        'position':        row.get('position', ''),
        'roleDescription': row.get('role_description', ''),
        'photoUrl':        row.get('photo_url', ''),
        'quote':           row.get('quote', ''),
        'isPunong':        bool(row.get('is_punong', False)),
        'displayOrder':    row.get('display_order', 99),
        'status':          row.get('status', 'draft'),
        'createdAt':       row.get('created_at', ''),
        'updatedAt':       row.get('updated_at', ''),
    }


def _load_officials():
    try:
        res = supabase.table('officials').select('*').execute()
        return [_row_to_official(r) for r in (res.data or [])]
    except Exception as exc:
        print(f'[BHOB] ERROR loading officials: {exc}')
        return []


def _official_create(data):
    now = datetime.now(timezone.utc).isoformat()
    record = {
        'full_name':        str(data.get('fullName', '')).strip(),
        'position':         str(data.get('position', '')).strip(),
        'role_description': str(data.get('roleDescription', '')).strip(),
        'photo_url':        str(data.get('photoUrl', '')).strip(),
        'quote':            str(data.get('quote', '')).strip(),
        'is_punong':        bool(data.get('isPunong', False)),
        'display_order':    int(data.get('displayOrder', 99)),
        'status':           data.get('status', 'draft'),
        'created_at':       now,
        'updated_at':       now,
    }
    res = supabase.table('officials').insert(record).execute()
    return _row_to_official(res.data[0]) if res.data else data


def _official_update(official_id, patch):
    now = datetime.now(timezone.utc).isoformat()
    record = {'updated_at': now}
    field_map = [
        ('fullName',        'full_name'),
        ('position',        'position'),
        ('roleDescription', 'role_description'),
        ('photoUrl',        'photo_url'),
        ('quote',           'quote'),
        ('isPunong',        'is_punong'),
        ('displayOrder',    'display_order'),
        ('status',          'status'),
    ]
    for src, dst in field_map:
        if src in patch:
            val = patch[src]
            if src == 'isPunong':
                val = bool(val)
            elif src == 'displayOrder':
                val = int(val)
            record[dst] = val
    try:
        res = (supabase.table('officials')
               .update(record).eq('id', official_id).execute())
        return _row_to_official(res.data[0]) if res.data else None
    except Exception:
        return None


def _official_delete(official_id):
    res = supabase.table('officials').delete().eq('id', official_id).execute()
    return bool(res.data)


def _official_bulk_order(order_map):
    now = datetime.now(timezone.utc).isoformat()
    for official_id, order in order_map.items():
        supabase.table('officials').update(
            {'display_order': order, 'updated_at': now}
        ).eq('id', official_id).execute()


def _official_set_punong(official_id):
    """Enforce exactly one Punong Barangay: clear all others, set the target."""
    now = datetime.now(timezone.utc).isoformat()
    supabase.table('officials').update(
        {'is_punong': False, 'updated_at': now}
    ).neq('id', official_id).execute()
    supabase.table('officials').update(
        {'is_punong': True, 'updated_at': now}
    ).eq('id', official_id).execute()


# ── Public routes — weather & tide ────────────────────────────────────────────
@app.route('/api/weather')
def api_weather():
    now_unix = time.time()
    if _weather_cache['data'] and (now_unix - _weather_cache['ts']) < WEATHER_TTL:
        return jsonify(_weather_cache['data'])
    try:
        url = 'https://wttr.in/Obando,Bulacan?format=j1'
        req = urllib.request.Request(url, headers={'User-Agent': 'curl/7.88'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            import json as _json
            raw = _json.loads(resp.read().decode('utf-8'))
        cc    = raw['current_condition'][0]
        temp  = int(cc['temp_C'])
        code  = cc.get('weatherCode', '113')
        label = cc['weatherDesc'][0]['value']
        color = _wttr_color(code)
        result = {'status': 'ok', 'temp': temp, 'code': code, 'label': label, 'color': color}
        _weather_cache['data'] = result
        _weather_cache['ts']   = now_unix
        return jsonify(result)
    except Exception:
        return jsonify({'status': 'unavailable'})


@app.route('/api/tide')
def api_tide():
    now_unix = time.time()
    if _tide_cache['data'] and (now_unix - _tide_cache['ts']) < TIDE_TTL:
        return jsonify(_tide_cache['data'])
    try:
        manila = _manila_now()
        url = (
            'https://marine-api.open-meteo.com/v1/marine'
            f'?latitude={TIDE_LAT}&longitude={TIDE_LON}'
            '&hourly=sea_level_height_msl&forecast_days=2&timezone=Asia%2FManila'
        )
        req = urllib.request.Request(url, headers={'User-Agent': 'BHOB-Site/1.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            import json as _json
            raw = _json.loads(resp.read().decode('utf-8'))
        times   = (raw.get('hourly') or {}).get('time', [])
        heights = (raw.get('hourly') or {}).get('sea_level_height_msl', [])
        valid   = [h for h in heights if h is not None]
        if not times or not valid:
            return jsonify({'status': 'unavailable'})
        current_iso = manila.strftime('%Y-%m-%dT%H:00')
        start_idx   = next((i for i, t in enumerate(times) if t == current_iso), 0)
        end_idx     = min(start_idx + 25, len(times))
        window      = [(times[i], heights[i]) for i in range(start_idx, end_idx)
                       if heights[i] is not None]
        if not window:
            return jsonify({'status': 'unavailable'})
        high_pair = max(window, key=lambda x: x[1])
        low_pair  = min(window, key=lambda x: x[1])

        def fmt_time(iso_str):
            h = int(iso_str[11:13])
            return f'{h % 12 or 12}:00 {"AM" if h < 12 else "PM"}'

        result = {
            'status': 'ok', 'estimated': True,
            'high': {'time': fmt_time(high_pair[0]), 'height': f'{high_pair[1]:.1f} m'},
            'low':  {'time': fmt_time(low_pair[0]),  'height': f'{low_pair[1]:.1f} m'},
            'source': 'Open-Meteo Marine',
        }
        _tide_cache['data'] = result
        _tide_cache['ts']   = now_unix
        return jsonify(result)
    except Exception:
        return jsonify({'status': 'unavailable'})


# ── Public announcements API ──────────────────────────────────────────────────
@app.route('/api/announcements')
def api_announcements():
    all_ann   = _load_ann()
    published = [a for a in all_ann if a.get('status') == 'published']
    published.sort(key=lambda x: x.get('date', ''), reverse=True)
    published.sort(key=_order_key)
    return jsonify({'status': 'ok', 'announcements': published})


# ── Public community initiatives API ─────────────────────────────────────────
@app.route('/api/community-initiatives')
def api_community_initiatives():
    all_proj  = _load_proj()
    published = [p for p in all_proj if p.get('status') == 'published']
    published.sort(key=lambda x: x.get('createdAt', ''), reverse=True)
    published.sort(key=_order_key)
    return jsonify({'status': 'ok', 'initiatives': published})


# ── Public forms API ─────────────────────────────────────────────────────────
@app.route('/api/forms')
def api_forms():
    all_forms = _load_forms()
    published = [f for f in all_forms if f.get('status') == 'published' and f.get('fileUrl', '')]
    published.sort(key=lambda x: x.get('updatedAt', ''), reverse=True)
    published.sort(key=_order_key)
    return jsonify({'status': 'ok', 'forms': published})


# ── Public page clean URLs (no .html required) ───────────────────────────────
_PUBLIC_PAGES = [
    'about', 'officials', 'announcements',
    'transparency', 'downloads', 'contact',
]

_PAGE_ALIASES = {
    'service-standards': 'citizens-charter',
    'community-initiatives': 'projects',
    'public-services': 'services',
}

@app.route('/citizens-charter')
def redirect_citizens_charter():
    return redirect('/service-standards', code=301)


@app.route('/projects')
def redirect_projects():
    return redirect('/community-initiatives', code=301)

@app.route('/services')
def redirect_services():
    return redirect('/public-services', code=301)

@app.route('/<page_name>')
def public_page(page_name):
    page_file = _PAGE_ALIASES.get(page_name, page_name)
    if page_file in _PUBLIC_PAGES or page_name in _PAGE_ALIASES:
        f = os.path.join(BASE_DIR, page_file + '.html')
        if os.path.exists(f):
            return send_from_directory(BASE_DIR, page_file + '.html')
    abort(404)


# ── Admin page serving ────────────────────────────────────────────────────────
@app.route('/admin')
def admin_index():
    return send_from_directory(os.path.join(BASE_DIR, 'admin'), 'index.html')


@app.route('/admin/<path:filename>')
def admin_files(filename):
    return send_from_directory(os.path.join(BASE_DIR, 'admin'), filename)


# ── Admin — session / auth ────────────────────────────────────────────────────
@app.route('/admin/login', methods=['POST'])
def admin_login():
    d        = request.get_json(silent=True) or {}
    username = str(d.get('username', '')).strip()
    password = str(d.get('password', ''))
    if not username or not password:
        return jsonify({'error': 'Username and password are required.'}), 400

    user = _get_user_by_username(username)
    if not user:
        _audit('login_failed', f'Unknown username: {username}', success=False)
        return jsonify({'error': 'Invalid username or password.'}), 401

    # Account lock check
    locked_until = user.get('lockedUntil')
    if locked_until:
        try:
            lock_dt = datetime.fromisoformat(locked_until)
            if datetime.now(timezone.utc) < lock_dt:
                mins = int((lock_dt - datetime.now(timezone.utc)).total_seconds() / 60) + 1
                return jsonify({'error': f'Account locked. Try again in {mins} minute(s).'}), 403
        except Exception:
            pass

    if not _check_pw(password, user.get('passwordHash', '')):
        user['failedLoginCount'] = user.get('failedLoginCount', 0) + 1
        if user['failedLoginCount'] >= MAX_FAILED_ATTEMPTS:
            user['lockedUntil'] = (
                datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)
            ).isoformat()
        _update_user(user)
        _audit('login_failed', f'Bad password for {username}', user_id=user['id'], success=False)
        return jsonify({'error': 'Invalid username or password.'}), 401

    if user.get('status') != 'active':
        return jsonify({'error': 'Account is not active. Contact the administrator.'}), 403

    # Successful login
    user['failedLoginCount'] = 0
    user['lockedUntil']      = None
    user['lastLoginAt']      = datetime.now(timezone.utc).isoformat()
    _update_user(user)
    _audit('login_success', f'Login: {username}', user_id=user['id'])

    session['admin_logged_in'] = True
    session['admin_user_id']   = user['id']
    session['last_active']     = time.time()

    return jsonify({
        'ok':                  True,
        'forcePasswordChange': user.get('forcePasswordChange', False),
        'user': {
            'id':       user['id'],
            'username': user['username'],
            'fullName': user['fullName'],
            'role':     user['role'],
        },
    })


@app.route('/admin/logout', methods=['POST'])
def admin_logout():
    uid = session.get('admin_user_id')
    _audit('logout', 'Admin logged out', user_id=uid)
    session.clear()
    return jsonify({'ok': True})


@app.route('/admin/check')
def admin_me():
    if not _session_valid():
        return jsonify({'error': 'unauthorized'}), 401
    user = _get_user_by_id(session.get('admin_user_id'))
    if not user or user.get('status') != 'active':
        session.clear()
        return jsonify({'error': 'unauthorized'}), 401
    return jsonify({
        'ok': True,
        'user': {
            'id':                  user['id'],
            'username':            user['username'],
            'fullName':            user['fullName'],
            'email':               user.get('email', ''),
            'role':                user['role'],
            'forcePasswordChange': user.get('forcePasswordChange', False),
        },
    })


# ── Admin — change password ───────────────────────────────────────────────────
@app.route('/admin/api/change-password', methods=['POST'])
@admin_auth_only
def admin_change_password():
    d           = request.get_json(silent=True) or {}
    current_pw  = str(d.get('currentPassword', ''))
    new_pw      = str(d.get('newPassword', ''))
    confirm_pw  = str(d.get('confirmPassword', ''))

    user = _get_user_by_id(session.get('admin_user_id'))
    if not user:
        return jsonify({'error': 'User not found.'}), 404

    if not _check_pw(current_pw, user.get('passwordHash', '')):
        _audit('password_change_failed', 'Wrong current password', user_id=user['id'], success=False)
        return jsonify({'error': 'Current password is incorrect.'}), 400
    if new_pw != confirm_pw:
        return jsonify({'error': 'New passwords do not match.'}), 400

    ok, msg = _validate_pw_strength(new_pw, user.get('username', ''), user.get('email', ''))
    if not ok:
        return jsonify({'error': msg}), 400

    user['passwordHash']        = _hash_pw(new_pw)
    user['forcePasswordChange'] = False
    _update_user(user)
    _audit('password_changed', 'Password changed successfully', user_id=user['id'])
    return jsonify({
        'ok':      True,
        'message': 'Password changed successfully. Please log in with your new password.',
    })


# ── Admin — announcement CRUD ─────────────────────────────────────────────────
@app.route('/admin/api/announcements')
@admin_required
def admin_list():
    all_ann = _load_ann()
    all_ann.sort(key=lambda x: x.get('updatedAt', ''), reverse=True)
    all_ann.sort(key=_order_key)
    return jsonify({'status': 'ok', 'announcements': all_ann})


@app.route('/admin/api/announcements', methods=['POST'])
@admin_required
def admin_create():
    d       = request.get_json(silent=True) or {}
    all_ann = _load_ann()
    now     = datetime.now(timezone.utc).isoformat()
    status  = d.get('status', 'draft')
    if status not in ('draft', 'published', 'hidden'):
        status = 'draft'
    min_order = min((a.get('displayOrder', 1) for a in all_ann), default=1)
    ann = {
        'id':               uuid.uuid4().hex,
        'title':            _clean(d.get('title'), 200),
        'date':             _clean(d.get('date'), 20),
        'category':         _clean(d.get('category', 'Other'), 50),
        'shortDescription': _clean(d.get('shortDescription'), 500),
        'fullDetails':      _clean(d.get('fullDetails'), 10000),
        'imageUrl':         _clean(d.get('imageUrl'), 300),
        'status':           status,
        'featured':         bool(d.get('featured', False)),
        'displayOrder':     min_order - 1,
        'createdAt':        now,
        'updatedAt':        now,
    }
    ann = _ann_create(ann)
    return jsonify({'status': 'ok', 'announcement': ann}), 201


@app.route('/admin/api/announcements/reorder', methods=['PUT'])
@admin_required
def admin_reorder():
    items = request.get_json(silent=True) or []
    if not isinstance(items, list):
        return jsonify({'error': 'Invalid payload'}), 400
    order_map = {}
    for item in items:
        if isinstance(item, dict) and 'id' in item:
            try:
                order_map[str(item['id'])] = int(item['displayOrder'])
            except (ValueError, TypeError, KeyError):
                pass
    _ann_bulk_order(order_map)
    return jsonify({'status': 'ok'})


@app.route('/admin/api/announcements/<ann_id>', methods=['PUT'])
@admin_required
def admin_update(ann_id):
    d = request.get_json(silent=True) or {}
    patch = {}
    for field, maxlen in [('title', 200), ('date', 20), ('category', 50),
                          ('shortDescription', 500), ('fullDetails', 10000), ('imageUrl', 300)]:
        if field in d:
            patch[field] = _clean(d[field], maxlen)
    if 'status' in d and d['status'] in ('draft', 'published', 'hidden'):
        patch['status'] = d['status']
    if 'featured' in d:
        patch['featured'] = bool(d['featured'])
    if 'displayOrder' in d:
        try:
            patch['displayOrder'] = int(d['displayOrder'])
        except (ValueError, TypeError):
            pass
    ann = _ann_update(ann_id, patch)
    if ann is None:
        return jsonify({'error': 'Not found'}), 404
    return jsonify({'status': 'ok', 'announcement': ann})


@app.route('/admin/api/announcements/<ann_id>', methods=['DELETE'])
@admin_required
def admin_delete(ann_id):
    if not _ann_delete(ann_id):
        return jsonify({'error': 'Not found'}), 404
    return jsonify({'status': 'ok'})


# ── Admin — community initiatives CRUD ───────────────────────────────────────
@app.route('/admin/api/community-initiatives')
@admin_required
def admin_proj_list():
    all_proj = _load_proj()
    all_proj.sort(key=lambda x: x.get('updatedAt', ''), reverse=True)
    all_proj.sort(key=_order_key)
    return jsonify({'status': 'ok', 'initiatives': all_proj})


@app.route('/admin/api/community-initiatives', methods=['POST'])
@admin_required
def admin_proj_create():
    d      = request.get_json(silent=True) or {}
    now    = datetime.now(timezone.utc).isoformat()
    status = d.get('status', 'draft')
    if status not in ('draft', 'published', 'hidden'):
        status = 'draft'
    all_proj  = _load_proj()
    min_order = min((p.get('displayOrder', 1) for p in all_proj), default=1)
    proj = {
        'id':               uuid.uuid4().hex,
        'title':            _clean(d.get('title'), 200),
        'category':         _clean(d.get('category'), 100),
        'subtitle':         _clean(d.get('subtitle'), 300),
        'shortDescription': _clean(d.get('shortDescription'), 500),
        'fullDetails':      _clean(d.get('fullDetails'), 10000),
        'imageUrl':         _clean(d.get('imageUrl'), 300),
        'status':           status,
        'featured':         bool(d.get('featured', False)),
        'displayOrder':     min_order - 1,
        'buttonLabel':      _clean(d.get('buttonLabel'), 100),
        'buttonLink':       _clean(d.get('buttonLink'), 300),
        'createdAt':        now,
        'updatedAt':        now,
    }
    proj = _proj_create(proj)
    return jsonify({'status': 'ok', 'initiative': proj}), 201


@app.route('/admin/api/community-initiatives/reorder', methods=['PUT'])
@admin_required
def admin_proj_reorder():
    items = request.get_json(silent=True) or []
    if not isinstance(items, list):
        return jsonify({'error': 'Invalid payload'}), 400
    order_map = {}
    for item in items:
        if isinstance(item, dict) and 'id' in item:
            try:
                order_map[str(item['id'])] = int(item['displayOrder'])
            except (ValueError, TypeError, KeyError):
                pass
    _proj_bulk_order(order_map)
    return jsonify({'status': 'ok'})


@app.route('/admin/api/community-initiatives/<proj_id>', methods=['PUT'])
@admin_required
def admin_proj_update(proj_id):
    d = request.get_json(silent=True) or {}
    patch = {}
    for field, maxlen in [('title', 200), ('category', 100), ('subtitle', 300),
                          ('shortDescription', 500), ('fullDetails', 10000),
                          ('imageUrl', 300), ('buttonLabel', 100), ('buttonLink', 300)]:
        if field in d:
            patch[field] = _clean(d[field], maxlen)
    if 'status' in d and d['status'] in ('draft', 'published', 'hidden'):
        patch['status'] = d['status']
    if 'featured' in d:
        patch['featured'] = bool(d['featured'])
    if 'displayOrder' in d:
        try:
            patch['displayOrder'] = int(d['displayOrder'])
        except (ValueError, TypeError):
            pass
    proj = _proj_update(proj_id, patch)
    if proj is None:
        return jsonify({'error': 'Not found'}), 404
    return jsonify({'status': 'ok', 'initiative': proj})


@app.route('/admin/api/community-initiatives/<proj_id>', methods=['DELETE'])
@admin_required
def admin_proj_delete(proj_id):
    if not _proj_delete(proj_id):
        return jsonify({'error': 'Not found'}), 404
    return jsonify({'status': 'ok'})


# ── Admin — download forms CRUD ──────────────────────────────────────────────
@app.route('/admin/api/forms')
@admin_required
def admin_forms_list():
    all_forms = _load_forms()
    all_forms.sort(key=lambda x: x.get('updatedAt', ''), reverse=True)
    all_forms.sort(key=_order_key)
    return jsonify({'status': 'ok', 'forms': all_forms})


@app.route('/admin/api/forms', methods=['POST'])
@admin_required
def admin_forms_create():
    d         = request.get_json(silent=True) or {}
    all_forms = _load_forms()
    now       = datetime.now(timezone.utc).isoformat()
    status    = d.get('status', 'draft')
    if status not in ('draft', 'published', 'hidden'):
        status = 'draft'
    min_order = min((f.get('displayOrder', 1) for f in all_forms), default=1)
    form = {
        'id':           uuid.uuid4().hex,
        'title':        _clean(d.get('title'), 200),
        'description':  _clean(d.get('description'), 500),
        'fileUrl':      _clean(d.get('fileUrl'), 300),
        'fileName':     _clean(d.get('fileName'), 200),
        'fileType':     _clean(d.get('fileType'), 10),
        'fileSize':     int(d.get('fileSize', 0)),
        'status':       status,
        'displayOrder': min_order - 1,
        'createdAt':    now,
        'updatedAt':    now,
    }
    form = _form_create(form)
    return jsonify({'status': 'ok', 'form': form}), 201


@app.route('/admin/api/forms/reorder', methods=['PUT'])
@admin_required
def admin_forms_reorder():
    items = request.get_json(silent=True) or []
    if not isinstance(items, list):
        return jsonify({'error': 'Invalid payload'}), 400
    order_map = {}
    for item in items:
        if isinstance(item, dict) and 'id' in item:
            try:
                order_map[str(item['id'])] = int(item['displayOrder'])
            except (ValueError, TypeError, KeyError):
                pass
    _form_bulk_order(order_map)
    return jsonify({'status': 'ok'})


@app.route('/admin/api/forms/<form_id>', methods=['PUT'])
@admin_required
def admin_forms_update(form_id):
    d = request.get_json(silent=True) or {}
    patch = {}
    for field, maxlen in [('title', 200), ('description', 500), ('fileUrl', 300),
                          ('fileName', 200), ('fileType', 10)]:
        if field in d:
            patch[field] = _clean(d[field], maxlen)
    if 'fileSize' in d:
        try:
            patch['fileSize'] = int(d['fileSize'])
        except (ValueError, TypeError):
            pass
    if 'status' in d and d['status'] in ('draft', 'published', 'hidden'):
        patch['status'] = d['status']
    if 'displayOrder' in d:
        try:
            patch['displayOrder'] = int(d['displayOrder'])
        except (ValueError, TypeError):
            pass
    form = _form_update(form_id, patch)
    if form is None:
        return jsonify({'error': 'Not found'}), 404
    return jsonify({'status': 'ok', 'form': form})


@app.route('/admin/api/forms/<form_id>', methods=['DELETE'])
@admin_required
def admin_forms_delete(form_id):
    # Retrieve the form to get file_url for storage cleanup
    try:
        res = supabase.table('forms').select('file_url').eq('id', form_id).limit(1).execute()
        if res.data:
            file_url = res.data[0].get('file_url', '')
            if file_url and file_url.startswith('http'):
                # Extract the storage path from the Supabase CDN URL
                # URL pattern: .../storage/v1/object/public/<bucket>/<path>
                marker = f'/object/public/{STORAGE_BUCKET}/'
                idx = file_url.find(marker)
                if idx != -1:
                    storage_path = file_url[idx + len(marker):]
                    try:
                        supabase.storage.from_(STORAGE_BUCKET).remove([storage_path])
                    except Exception:
                        pass
    except Exception:
        pass
    if not _form_delete(form_id):
        return jsonify({'error': 'Not found'}), 404
    return jsonify({'status': 'ok'})


# ── Image upload (Supabase Storage) ──────────────────────────────────────────
ALLOWED_EXT = {'jpg', 'jpeg', 'png', 'webp'}
MAX_BYTES   = 5 * 1024 * 1024

try:
    from PIL import Image as _PILImage
    import io as _io
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


def _optimize_image(data, ext):
    """Preserve good image quality for announcement/initiative uploads.

    Resize only very large images and save at high quality so uploaded
    graphics with text do not look pixelated on public cards.
    Falls back to the original file if PIL is unavailable or processing fails.
    """
    if not _HAS_PIL:
        return data, ext
    try:
        img = _PILImage.open(_io.BytesIO(data))
        ext = (ext or '').lower()

        max_w = 1800
        if img.width > max_w:
            new_h = int(img.height * max_w / img.width)
            img = img.resize((max_w, new_h), _PILImage.LANCZOS)

        out = _io.BytesIO()

        if ext == 'png':
            img.save(out, format='PNG', optimize=True)
            return out.getvalue(), 'png'

        if ext == 'webp':
            img.save(out, format='WEBP', quality=94, method=6)
            return out.getvalue(), 'webp'

        if img.mode in ('RGBA', 'LA', 'P'):
            if img.mode == 'P':
                img = img.convert('RGBA')
            bg = _PILImage.new('RGB', img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = bg
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        img.save(out, format='JPEG', quality=94, optimize=True, progressive=True, subsampling=0)
        return out.getvalue(), 'jpg'
    except Exception:
        return data, ext


def _upload_to_storage(data, folder, ext):
    """Upload bytes to Supabase Storage and return the public CDN URL."""
    fname   = uuid.uuid4().hex + '.' + ext
    path    = f'{folder}/{fname}'
    mime    = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
               'png': 'image/png', 'webp': 'image/webp',
               'pdf': 'application/pdf',
               'doc': 'application/msword',
               'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
               }.get(ext, 'application/octet-stream')
    supabase.storage.from_(STORAGE_BUCKET).upload(
        path, data, {'content-type': mime, 'upsert': 'false'}
    )
    res = supabase.storage.from_(STORAGE_BUCKET).get_public_url(path)
    # get_public_url returns the URL string directly in supabase-py >=2
    return res if isinstance(res, str) else res.get('publicUrl', '')


@app.route('/admin/api/upload', methods=['POST'])
@admin_required
def admin_upload():
    f = request.files.get('image')
    if not f or not f.filename:
        return jsonify({'error': 'No file selected'}), 400
    ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
    if ext not in ALLOWED_EXT:
        return jsonify({'error': 'Invalid file type. Use JPG, PNG, or WebP.'}), 400
    data = f.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        return jsonify({'error': 'File too large (max 5 MB)'}), 400
    data, ext = _optimize_image(data, ext)
    try:
        url = _upload_to_storage(data, 'announcements', ext)
    except Exception as exc:
        return jsonify({'error': f'Upload failed: {exc}'}), 500
    return jsonify({'status': 'ok', 'url': url})


@app.route('/admin/api/upload-initiative', methods=['POST'])
@admin_required
def admin_upload_initiative():
    f = request.files.get('image')
    if not f or not f.filename:
        return jsonify({'error': 'No file selected'}), 400
    ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
    if ext not in ALLOWED_EXT:
        return jsonify({'error': 'Invalid file type. Use JPG, PNG, or WebP.'}), 400
    data = f.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        return jsonify({'error': 'File too large (max 5 MB)'}), 400
    data, ext = _optimize_image(data, ext)
    try:
        url = _upload_to_storage(data, 'initiatives', ext)
    except Exception as exc:
        return jsonify({'error': f'Upload failed: {exc}'}), 500
    return jsonify({'status': 'ok', 'url': url})


@app.route('/admin/api/upload-form-file', methods=['POST'])
@admin_required
def admin_upload_form_file():
    """Upload a downloadable form file (PDF, DOC, DOCX). Max 10 MB."""
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'error': 'No file selected'}), 400
    ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
    allowed = {'pdf', 'doc', 'docx'}
    if ext not in allowed:
        return jsonify({'error': 'Invalid file type. Only PDF, DOC, and DOCX are allowed.'}), 400
    max_bytes = 10 * 1024 * 1024
    data = f.read(max_bytes + 1)
    if len(data) > max_bytes:
        return jsonify({'error': 'File too large (max 10 MB)'}), 400
    original_name = os.path.basename(f.filename)
    try:
        url = _upload_to_storage(data, 'forms', ext)
    except Exception as exc:
        return jsonify({'error': f'Upload failed: {exc}'}), 500
    return jsonify({
        'status':   'ok',
        'url':      url,
        'fileName': original_name,
        'fileType': ext,
        'fileSize': len(data),
    })


# ── Officials routes ──────────────────────────────────────────────────────────
@app.route('/api/officials')
def api_officials():
    all_officials = _load_officials()
    published = [o for o in all_officials if o.get('status') == 'published']
    published.sort(key=lambda x: x.get('displayOrder', 99))
    return jsonify({'status': 'ok', 'officials': published})


@app.route('/admin/api/officials')
@admin_required
def admin_officials_list():
    all_officials = _load_officials()
    all_officials.sort(key=lambda x: x.get('displayOrder', 99))
    return jsonify({'status': 'ok', 'officials': all_officials})


@app.route('/admin/api/officials', methods=['POST'])
@admin_required
def admin_officials_create():
    data = request.get_json(silent=True) or {}
    if not str(data.get('fullName', '')).strip():
        return jsonify({'error': 'Full name is required.'}), 400
    if not str(data.get('position', '')).strip():
        return jsonify({'error': 'Position is required.'}), 400
    official = _official_create(data)
    if data.get('isPunong'):
        _official_set_punong(official['id'])
        official['isPunong'] = True
    return jsonify({'status': 'ok', 'official': official}), 201


@app.route('/admin/api/officials/reorder', methods=['PUT'])
@admin_required
def admin_officials_reorder():
    data = request.get_json(silent=True) or {}
    order_map = data.get('order', {})
    if not isinstance(order_map, dict):
        return jsonify({'error': 'Invalid order payload'}), 400
    _official_bulk_order(order_map)
    return jsonify({'status': 'ok'})


@app.route('/admin/api/officials/<official_id>', methods=['PUT'])
@admin_required
def admin_officials_update(official_id):
    data = request.get_json(silent=True) or {}
    if 'fullName' in data and not str(data['fullName']).strip():
        return jsonify({'error': 'Full name is required.'}), 400
    if 'position' in data and not str(data['position']).strip():
        return jsonify({'error': 'Position is required.'}), 400
    official = _official_update(official_id, data)
    if not official:
        return jsonify({'error': 'Not found'}), 404
    if data.get('isPunong'):
        _official_set_punong(official_id)
        official['isPunong'] = True
    return jsonify({'status': 'ok', 'official': official})


@app.route('/admin/api/officials/<official_id>', methods=['DELETE'])
@admin_required
def admin_officials_delete(official_id):
    try:
        res = (supabase.table('officials')
               .select('photo_url').eq('id', official_id).limit(1).execute())
        if res.data:
            photo_url = res.data[0].get('photo_url', '')
            if photo_url and photo_url.startswith('http'):
                marker = f'/object/public/{STORAGE_BUCKET}/'
                idx = photo_url.find(marker)
                if idx != -1:
                    storage_path = photo_url[idx + len(marker):]
                    try:
                        supabase.storage.from_(STORAGE_BUCKET).remove([storage_path])
                    except Exception:
                        pass
    except Exception:
        pass
    if not _official_delete(official_id):
        return jsonify({'error': 'Not found'}), 404
    return jsonify({'status': 'ok'})


@app.route('/admin/api/upload/official-photo', methods=['POST'])
@admin_required
def admin_upload_official_photo():
    f = request.files.get('image')
    if not f or not f.filename:
        return jsonify({'error': 'No file selected'}), 400
    ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
    if ext not in ALLOWED_EXT:
        return jsonify({'error': 'Invalid file type. Use JPG, PNG, or WebP.'}), 400
    data = f.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        return jsonify({'error': 'File too large (max 5 MB)'}), 400
    data, ext = _optimize_image(data, ext)
    try:
        url = _upload_to_storage(data, 'officials', ext)
    except Exception as exc:
        return jsonify({'error': f'Upload failed: {exc}'}), 500
    return jsonify({'status': 'ok', 'url': url})


# ── Site settings helpers ─────────────────────────────────────────────────────
def _load_site_settings():
    """Return site_settings as a flat {key: value} dict. Empty dict on error.
    Orders by updated_at desc so the most recent value wins if duplicates exist."""
    try:
        res = supabase.table('site_settings').select('key,value').order('updated_at', desc=True).execute()
        seen = {}
        for row in (res.data or []):
            if row['key'] not in seen:
                seen[row['key']] = row['value']
        return seen
    except Exception:
        return {}


def _upsert_site_settings(patch):
    """Save each key/value into site_settings using update-then-insert to avoid
    relying on a unique constraint for ON CONFLICT resolution."""
    now = datetime.now(timezone.utc).isoformat()
    for key, value in patch.items():
        val = str(value)
        res = supabase.table('site_settings').update(
            {'value': val, 'updated_at': now}
        ).eq('key', key).execute()
        if res.data:
            print(f'[settings] updated {key}={repr(val)}', flush=True)
        else:
            supabase.table('site_settings').insert(
                {'key': key, 'value': val, 'updated_at': now}
            ).execute()
            print(f'[settings] inserted {key}={repr(val)}', flush=True)


# ── Emergency hotlines helpers ────────────────────────────────────────────────
def _row_to_hotline(row):
    return {
        'id':           row['id'],
        'label':        row.get('label', ''),
        'number':       row.get('number', ''),
        'description':  row.get('description', ''),
        'category':     row.get('category', ''),
        'displayOrder': row.get('display_order', 99),
        'status':       row.get('status', 'published'),
        'createdAt':    row.get('created_at', ''),
        'updatedAt':    row.get('updated_at', ''),
    }


def _load_hotlines(published_only=False):
    try:
        q = supabase.table('emergency_hotlines').select('*')
        if published_only:
            q = q.eq('status', 'published')
        res = q.order('display_order').execute()
        return [_row_to_hotline(r) for r in (res.data or [])]
    except Exception:
        return []


def _hotline_bulk_order(order_map):
    now = datetime.now(timezone.utc).isoformat()
    for hotline_id, order in order_map.items():
        supabase.table('emergency_hotlines').update(
            {'display_order': order, 'updated_at': now}
        ).eq('id', hotline_id).execute()


# ── Public — site settings & emergency hotlines ───────────────────────────────
@app.route('/api/site-settings')
def api_site_settings():
    return jsonify(_load_site_settings())


@app.route('/api/emergency-hotlines')
def api_emergency_hotlines():
    hotlines = _load_hotlines(published_only=True)
    return jsonify({'hotlines': hotlines})


# ── Admin — site settings ─────────────────────────────────────────────────────
@app.route('/admin/api/site-settings')
@admin_required
def admin_site_settings_get():
    return jsonify(_load_site_settings())


@app.route('/admin/api/site-settings', methods=['PUT'])
@admin_required
def admin_site_settings_put():
    d = request.get_json(silent=True) or {}
    ALLOWED_KEYS = {
        'footer_phone', 'footer_email',
        'copyright_year', 'copyright_owner', 'copyright_suffix',
        'barangay_phone', 'barangay_email',
        'barangay_facebook', 'barangay_social', 'barangay_address',
        'homepage_hotline_label', 'homepage_hotline_number', 'homepage_hotline_description',
        'emergency_card_label', 'emergency_card_number',
        'police_card_label', 'police_card_number',
        'social_facebook_url', 'social_linkedin_url', 'social_instagram_url',
        'sk_facebook_title', 'sk_facebook_subtitle', 'sk_facebook_url',
    }
    patch = {k: _clean(v, 300) for k, v in d.items() if k in ALLOWED_KEYS}
    if not patch:
        return jsonify({'error': 'No valid fields provided'}), 400
    try:
        _upsert_site_settings(patch)
    except Exception:
        import traceback
        print('[settings] FAILED to save:', traceback.format_exc(), flush=True)
        return jsonify({'error': 'Database write failed — check Render logs'}), 500
    # Verify write by re-reading
    saved = _load_site_settings()
    failed = [k for k, v in patch.items() if v and saved.get(k) != v]
    if failed:
        print(f'[settings] WARNING: keys not confirmed in DB after write: {failed}', flush=True)
    return jsonify({'ok': True, 'updated': list(patch.keys())})


# ── Admin — emergency hotlines CRUD ──────────────────────────────────────────
@app.route('/admin/api/emergency-hotlines')
@admin_required
def admin_hotlines_list():
    hotlines = _load_hotlines()
    return jsonify({'hotlines': hotlines})


@app.route('/admin/api/emergency-hotlines', methods=['POST'])
@admin_required
def admin_hotlines_create():
    d = request.get_json(silent=True) or {}
    if not str(d.get('label', '')).strip():
        return jsonify({'error': 'Label is required.'}), 400
    if not str(d.get('number', '')).strip():
        return jsonify({'error': 'Number is required.'}), 400
    status = d.get('status', 'published')
    if status not in ('draft', 'published', 'hidden'):
        status = 'published'
    now = datetime.now(timezone.utc).isoformat()
    row = {
        'label':         _clean(d.get('label'), 100),
        'number':        _clean(d.get('number'), 50),
        'description':   _clean(d.get('description', ''), 300),
        'category':      _clean(d.get('category', ''), 100),
        'status':        status,
        'created_at':    now,
        'updated_at':    now,
    }
    try:
        row['display_order'] = int(d.get('displayOrder', 99))
    except (ValueError, TypeError):
        row['display_order'] = 99
    res = supabase.table('emergency_hotlines').insert(row).execute()
    if not res.data:
        return jsonify({'error': 'Create failed'}), 500
    return jsonify({'ok': True, 'hotline': _row_to_hotline(res.data[0])}), 201


@app.route('/admin/api/emergency-hotlines/reorder', methods=['PUT'])
@admin_required
def admin_hotlines_reorder():
    items = request.get_json(silent=True) or []
    if not isinstance(items, list):
        return jsonify({'error': 'Invalid payload'}), 400
    order_map = {}
    for item in items:
        if isinstance(item, dict) and 'id' in item:
            try:
                order_map[str(item['id'])] = int(item['displayOrder'])
            except (ValueError, TypeError, KeyError):
                pass
    _hotline_bulk_order(order_map)
    return jsonify({'ok': True})


@app.route('/admin/api/emergency-hotlines/<hotline_id>', methods=['PUT'])
@admin_required
def admin_hotlines_update(hotline_id):
    d = request.get_json(silent=True) or {}
    now = datetime.now(timezone.utc).isoformat()
    patch = {'updated_at': now}
    if 'label' in d:
        if not str(d['label']).strip():
            return jsonify({'error': 'Label is required.'}), 400
        patch['label'] = _clean(d['label'], 100)
    if 'number' in d:
        if not str(d['number']).strip():
            return jsonify({'error': 'Number is required.'}), 400
        patch['number'] = _clean(d['number'], 50)
    for field, snake, maxlen in [
        ('description', 'description',   300),
        ('category',    'category',      100),
    ]:
        if field in d:
            patch[snake] = _clean(d[field], maxlen)
    if 'status' in d and d['status'] in ('draft', 'published', 'hidden'):
        patch['status'] = d['status']
    if 'displayOrder' in d:
        try:
            patch['display_order'] = int(d['displayOrder'])
        except (ValueError, TypeError):
            pass
    res = (supabase.table('emergency_hotlines')
           .update(patch).eq('id', hotline_id).execute())
    if not res.data:
        return jsonify({'error': 'Not found'}), 404
    return jsonify({'ok': True, 'hotline': _row_to_hotline(res.data[0])})


@app.route('/admin/api/emergency-hotlines/<hotline_id>', methods=['DELETE'])
@admin_required
def admin_hotlines_delete(hotline_id):
    res = (supabase.table('emergency_hotlines')
           .delete().eq('id', hotline_id).execute())
    if not res.data:
        return jsonify({'error': 'Not found'}), 404
    return jsonify({'ok': True})


# ── Calendar activities helpers ───────────────────────────────────────────────
def _row_to_cal(row):
    return {
        'id':               row['id'],
        'title':            row.get('title', ''),
        'category':         row.get('category', ''),
        'date':             row.get('date', ''),
        'startTime':        row.get('start_time', ''),
        'endTime':          row.get('end_time', ''),
        'location':         row.get('location', ''),
        'shortDescription': row.get('short_description', ''),
        'fullDescription':  row.get('full_description', ''),
        'requirements':     row.get('requirements', ''),
        'attachmentUrl':    row.get('attachment_url', ''),
        'attachmentName':   row.get('attachment_name', ''),
        'photos':           row.get('photos') or [],
        'documents':        row.get('documents') or [],
        'summary':          row.get('summary', ''),
        'status':           row.get('status', 'draft'),
        'createdAt':        row.get('created_at', ''),
        'updatedAt':        row.get('updated_at', ''),
    }


_CAL_PUBLIC_STATUSES = ['scheduled', 'ongoing', 'completed', 'cancelled']


def _load_cal_activities(status_filter=None):
    try:
        res = supabase.table('calendar_activities').select('*').order('date').execute()
        rows = res.data or []
        if status_filter:
            if isinstance(status_filter, list):
                rows = [r for r in rows if r.get('status') in status_filter]
            else:
                rows = [r for r in rows if r.get('status') == status_filter]
        return [_row_to_cal(r) for r in rows]
    except Exception as exc:
        app.logger.error('_load_cal_activities error: %s', exc)
        return []


# ── Public — calendar activities ──────────────────────────────────────────────
@app.route('/api/calendar-activities')
def api_calendar_activities():
    activities = _load_cal_activities(status_filter=_CAL_PUBLIC_STATUSES)
    return jsonify({'status': 'ok', 'activities': activities})


# ── Admin — calendar activities ──────────────────────────────────────────────
_CAL_VALID_STATUSES = {'draft', 'scheduled', 'ongoing', 'completed', 'cancelled', 'archived'}


def _cal_create(data):
    payload = {
        'title':             data.get('title', ''),
        'category':          data.get('category', ''),
        'date':              data.get('date') or None,
        'start_time':        data.get('startTime', ''),
        'end_time':          data.get('endTime', ''),
        'location':          data.get('location', ''),
        'short_description': data.get('shortDescription', ''),
        'full_description':  data.get('fullDescription', ''),
        'requirements':      data.get('requirements', ''),
        'summary':           data.get('summary', ''),
        'photos':            data.get('photos') or [],
        'documents':         data.get('documents') or [],
        'status':            data.get('status', 'draft'),
    }
    res = supabase.table('calendar_activities').insert(payload).execute()
    return res.data[0] if res.data else None


def _cal_update(act_id, patch):
    payload = {}
    if 'title'            in patch: payload['title']             = patch['title']
    if 'category'         in patch: payload['category']          = patch['category']
    if 'date'             in patch: payload['date']              = patch['date'] or None
    if 'startTime'        in patch: payload['start_time']        = patch['startTime']
    if 'endTime'          in patch: payload['end_time']          = patch['endTime']
    if 'location'         in patch: payload['location']          = patch['location']
    if 'shortDescription' in patch: payload['short_description'] = patch['shortDescription']
    if 'fullDescription'  in patch: payload['full_description']  = patch['fullDescription']
    if 'requirements'     in patch: payload['requirements']      = patch['requirements']
    if 'summary'          in patch: payload['summary']           = patch['summary']
    if 'photos'           in patch: payload['photos']            = patch['photos'] or []
    if 'documents'        in patch: payload['documents']         = patch['documents'] or []
    if 'status'           in patch: payload['status']            = patch['status']
    if not payload:
        return None
    res = supabase.table('calendar_activities').update(payload).eq('id', act_id).execute()
    return res.data[0] if res.data else None


def _cal_delete(act_id):
    supabase.table('calendar_activities').delete().eq('id', act_id).execute()


@app.route('/admin/api/calendar-activities', methods=['GET'])
@admin_required
def admin_cal_list():
    activities = _load_cal_activities()
    return jsonify({'status': 'ok', 'activities': activities})


@app.route('/admin/api/calendar-activities', methods=['POST'])
@admin_required
def admin_cal_create():
    data = request.get_json(force=True) or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'error': 'Title is required.'}), 400
    status = data.get('status', 'draft')
    if status not in _CAL_VALID_STATUSES:
        return jsonify({'error': 'Invalid status.'}), 400
    try:
        row = _cal_create(data)
        return jsonify({'status': 'ok', 'activity': _row_to_cal(row)}), 201
    except Exception as exc:
        app.logger.error('admin_cal_create error: %s', exc)
        return jsonify({'error': 'Server error.'}), 500


@app.route('/admin/api/calendar-activities/<act_id>', methods=['PUT'])
@admin_required
def admin_cal_update(act_id):
    data = request.get_json(force=True) or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'error': 'Title is required.'}), 400
    status = data.get('status', 'draft')
    if status not in _CAL_VALID_STATUSES:
        return jsonify({'error': 'Invalid status.'}), 400
    try:
        row = _cal_update(act_id, data)
        if not row:
            return jsonify({'error': 'Not found.'}), 404
        return jsonify({'status': 'ok', 'activity': _row_to_cal(row)})
    except Exception as exc:
        app.logger.error('admin_cal_update error: %s', exc)
        return jsonify({'error': 'Server error.'}), 500


@app.route('/admin/api/calendar-activities/<act_id>', methods=['PATCH'])
@admin_required
def admin_cal_patch(act_id):
    data = request.get_json(force=True) or {}
    if 'status' in data and data['status'] not in _CAL_VALID_STATUSES:
        return jsonify({'error': 'Invalid status.'}), 400
    try:
        row = _cal_update(act_id, data)
        if not row:
            return jsonify({'error': 'Not found.'}), 404
        return jsonify({'status': 'ok', 'activity': _row_to_cal(row)})
    except Exception as exc:
        app.logger.error('admin_cal_patch error: %s', exc)
        return jsonify({'error': 'Server error.'}), 500


@app.route('/admin/api/calendar-activities/<act_id>', methods=['DELETE'])
@admin_required
def admin_cal_delete(act_id):
    try:
        _cal_delete(act_id)
        return jsonify({'status': 'ok'})
    except Exception as exc:
        app.logger.error('admin_cal_delete error: %s', exc)
        return jsonify({'error': 'Server error.'}), 500


@app.route('/admin/api/upload/calendar-attachment', methods=['POST'])
@admin_required
def admin_upload_calendar_attachment():
    f = request.files.get('file')
    if not f:
        return jsonify({'error': 'No file provided.'}), 400
    ext = os.path.splitext(f.filename or '')[1].lower().lstrip('.')
    allowed = {'jpg', 'jpeg', 'png', 'webp', 'pdf', 'doc', 'docx'}
    if ext not in allowed:
        return jsonify({'error': 'File type not allowed.'}), 400
    data = f.read()
    if len(data) > 10 * 1024 * 1024:
        return jsonify({'error': 'File exceeds 10 MB limit.'}), 400
    try:
        url = _upload_to_storage(data, 'calendar', ext)
        return jsonify({'status': 'ok', 'url': url, 'fileName': f.filename})
    except Exception as exc:
        app.logger.error('admin_upload_calendar_attachment error: %s', exc)
        return jsonify({'error': 'Upload failed.'}), 500


# ── Resolved message config helpers ──────────────────────────────────────────
def _row_to_resolved_msg(row):
    return {
        'priority':        row['priority'],
        'useCustom':       bool(row.get('use_custom', False)),
        'customMessage':   row.get('custom_message', ''),
        'updatedBy':       row.get('updated_by', ''),
        'updatedAt':       str(row.get('updated_at', '') or ''),
        'previousMessage': row.get('previous_message', ''),
    }


def _load_resolved_message_config():
    try:
        res = supabase.table('ea_resolved_messages').select('*').execute()
        return {row['priority']: _row_to_resolved_msg(row) for row in (res.data or [])}
    except Exception:
        return {}


def _get_resolved_message(priority):
    try:
        cfg = _load_resolved_message_config().get(priority)
        if cfg and cfg.get('useCustom') and cfg.get('customMessage', '').strip():
            return cfg['customMessage'].strip()
    except Exception:
        pass
    return None


# ── Emergency Alert helpers ───────────────────────────────────────────────────
def _current_admin_name():
    user = _get_user_by_id(session.get('admin_user_id'))
    if user:
        return user.get('fullName') or user.get('username') or 'Admin'
    return 'Admin'


def _compute_banner_popup(priority):
    if (priority or '').strip() == 'Critical':
        return True, True
    return True, False


def _row_to_alert(row):
    return {
        'id':                 row['id'],
        'title':              row.get('title', ''),
        'alertType':          row.get('alert_type', 'Other'),
        'priority':           row.get('priority', 'Advisory'),
        'targetAudience':     row.get('target_audience', 'All Residents'),
        'targetArea':         row.get('target_area', ''),
        'message':            row.get('message', ''),
        'instructions':       row.get('instructions', ''),
        'startDatetime':      row.get('start_datetime', ''),
        'expirationDatetime': row.get('expiration_datetime', ''),
        'status':             row.get('status', 'draft'),
        'version':            row.get('version', 1),
        'showBanner':         bool(row.get('show_banner', False)),
        'enablePopup':        bool(row.get('enable_popup', False)),
        'createdBy':          row.get('created_by', ''),
        'createdAt':          str(row.get('created_at', '') or ''),
        'updatedBy':          row.get('updated_by', ''),
        'updatedAt':          str(row.get('updated_at', '') or ''),
        'resolvedBy':         row.get('resolved_by', ''),
        'resolvedAt':         str(row.get('resolved_at', '') or ''),
    }


def _load_alerts():
    try:
        res = (supabase.table('emergency_alerts')
               .select('*')
               .order('created_at', desc=True)
               .execute())
        return [_row_to_alert(r) for r in (res.data or [])]
    except Exception as exc:
        app.logger.error('_load_alerts error: %s', exc)
        return []


def _auto_expire_alerts():
    try:
        now_manila = _manila_now().strftime('%Y-%m-%dT%H:%M')
        res = (supabase.table('emergency_alerts')
               .select('id,expiration_datetime')
               .eq('status', 'active')
               .execute())
        now_utc = datetime.now(timezone.utc).isoformat()
        for row in (res.data or []):
            exp = (row.get('expiration_datetime') or '')[:16]
            if exp and exp <= now_manila:
                supabase.table('emergency_alerts').update({
                    'status':     'expired',
                    'updated_at': now_utc,
                }).eq('id', row['id']).execute()
    except Exception as exc:
        app.logger.error('_auto_expire_alerts error: %s', exc)


# ── Admin — emergency alerts CRUD ─────────────────────────────────────────────
@app.route('/admin/api/emergency-alerts')
@admin_required
def admin_alerts_list():
    _auto_expire_alerts()
    alerts = _load_alerts()
    return jsonify({'status': 'ok', 'alerts': alerts})


@app.route('/admin/api/emergency-alerts', methods=['POST'])
@admin_required
def admin_alerts_create():
    d = request.get_json(silent=True) or {}
    title   = _clean(d.get('title'), 200)
    message = _clean(d.get('message'), 5000)
    if not title:
        return jsonify({'error': 'Alert title is required.'}), 400
    if not message:
        return jsonify({'error': 'Emergency message is required.'}), 400
    start  = _clean(d.get('startDatetime'), 30) or None
    expiry = _clean(d.get('expirationDatetime'), 30) or None
    req_status = d.get('status', 'draft')
    if req_status == 'active':
        if not start:
            return jsonify({'error': 'Start date and time is required.'}), 400
        if not expiry:
            return jsonify({'error': 'Expiration date and time is required.'}), 400
    if start and expiry and expiry <= start:
        return jsonify({'error': 'Expiration must be after Start date/time.'}), 400

    priority = _clean(d.get('priority', 'Advisory'), 20)
    if priority not in ('Advisory', 'Warning', 'Critical'):
        priority = 'Advisory'
    show_banner, enable_popup = _compute_banner_popup(priority)
    status = 'active' if req_status == 'active' else 'draft'
    admin_name = _current_admin_name()
    now = datetime.now(timezone.utc).isoformat()
    row = {
        'id':                  uuid.uuid4().hex,
        'title':               title,
        'alert_type':          _clean(d.get('alertType', 'Other'), 50),
        'priority':            priority,
        'target_audience':     _clean(d.get('targetAudience', 'All Residents'), 50),
        'target_area':         _clean(d.get('targetArea', ''), 200),
        'message':             message,
        'instructions':        _clean(d.get('instructions', ''), 5000),
        'start_datetime':      start,
        'expiration_datetime': expiry,
        'status':              status,
        'version':             1,
        'show_banner':         show_banner,
        'enable_popup':        enable_popup,
        'created_by':          admin_name,
        'created_at':          now,
        'updated_by':          admin_name,
        'updated_at':          now,
        'resolved_by':         '',
        'resolved_at':         None,
    }
    try:
        res = supabase.table('emergency_alerts').insert(row).select().execute()
        alert = _row_to_alert(res.data[0]) if res.data else row
        return jsonify({'status': 'ok', 'alert': alert}), 201
    except Exception as exc:
        return jsonify({'error': f'Create failed: {exc}'}), 500


@app.route('/admin/api/emergency-alerts/<alert_id>', methods=['PUT'])
@admin_required
def admin_alerts_update(alert_id):
    d = request.get_json(silent=True) or {}
    try:
        cur_res = (supabase.table('emergency_alerts')
                   .select('*').eq('id', alert_id).limit(1).execute())
        if not cur_res.data:
            return jsonify({'error': 'Alert not found.'}), 404
        cur = cur_res.data[0]
    except Exception as exc:
        return jsonify({'error': f'Fetch failed: {exc}'}), 500

    start  = _clean(d.get('startDatetime',      cur.get('start_datetime',  '')), 30) or None
    expiry = _clean(d.get('expirationDatetime', cur.get('expiration_datetime', '')), 30) or None
    if expiry and start and expiry <= start:
        return jsonify({'error': 'Expiration must be after Start date/time.'}), 400

    priority = _clean(d.get('priority', cur.get('priority', 'Advisory')), 20)
    if priority not in ('Advisory', 'Warning', 'Critical'):
        priority = cur.get('priority', 'Advisory')
    show_banner, enable_popup = _compute_banner_popup(priority)
    admin_name = _current_admin_name()
    now = datetime.now(timezone.utc).isoformat()
    patch = {
        'title':               _clean(d.get('title',           cur.get('title', '')), 200),
        'alert_type':          _clean(d.get('alertType',       cur.get('alert_type', 'Other')), 50),
        'priority':            priority,
        'target_audience':     _clean(d.get('targetAudience',  cur.get('target_audience', 'All Residents')), 50),
        'target_area':         _clean(d.get('targetArea',      cur.get('target_area', '')), 200),
        'message':             _clean(d.get('message',         cur.get('message', '')), 5000),
        'instructions':        _clean(d.get('instructions',    cur.get('instructions', '')), 5000),
        'start_datetime':      start,
        'expiration_datetime': expiry,
        'show_banner':         show_banner,
        'enable_popup':        enable_popup,
        'version':             int(cur.get('version', 1)) + 1,
        'updated_by':          admin_name,
        'updated_at':          now,
    }
    try:
        res = (supabase.table('emergency_alerts')
               .update(patch).eq('id', alert_id).select().execute())
        if not res.data:
            return jsonify({'error': 'Alert not found.'}), 404
        return jsonify({'status': 'ok', 'alert': _row_to_alert(res.data[0])})
    except Exception as exc:
        return jsonify({'error': f'Update failed: {exc}'}), 500


@app.route('/admin/api/emergency-alerts/<alert_id>/activate', methods=['POST'])
@admin_required
def admin_alerts_activate(alert_id):
    admin_name = _current_admin_name()
    now = datetime.now(timezone.utc).isoformat()
    try:
        res = (supabase.table('emergency_alerts')
               .update({'status': 'active', 'updated_by': admin_name, 'updated_at': now})
               .eq('id', alert_id).select().execute())
        if not res.data:
            return jsonify({'error': 'Alert not found.'}), 404
        return jsonify({'status': 'ok', 'alert': _row_to_alert(res.data[0])})
    except Exception as exc:
        return jsonify({'error': f'Activate failed: {exc}'}), 500


@app.route('/admin/api/emergency-alerts/<alert_id>/resolve', methods=['POST'])
@admin_required
def admin_alerts_resolve(alert_id):
    admin_name = _current_admin_name()
    now = datetime.now(timezone.utc).isoformat()
    try:
        res = (supabase.table('emergency_alerts')
               .update({
                   'status':      'resolved',
                   'resolved_by': admin_name,
                   'resolved_at': now,
                   'updated_by':  admin_name,
                   'updated_at':  now,
               })
               .eq('id', alert_id).select().execute())
        if not res.data:
            return jsonify({'error': 'Alert not found.'}), 404
        return jsonify({'status': 'ok', 'alert': _row_to_alert(res.data[0])})
    except Exception as exc:
        return jsonify({'error': f'Resolve failed: {exc}'}), 500


@app.route('/admin/api/emergency-alerts/<alert_id>/archive', methods=['POST'])
@admin_required
def admin_alerts_archive(alert_id):
    admin_name = _current_admin_name()
    now = datetime.now(timezone.utc).isoformat()
    try:
        res = (supabase.table('emergency_alerts')
               .update({'status': 'archived', 'updated_by': admin_name, 'updated_at': now})
               .eq('id', alert_id).select().execute())
        if not res.data:
            return jsonify({'error': 'Alert not found.'}), 404
        return jsonify({'status': 'ok', 'alert': _row_to_alert(res.data[0])})
    except Exception as exc:
        return jsonify({'error': f'Archive failed: {exc}'}), 500


@app.route('/admin/api/emergency-alerts/<alert_id>', methods=['DELETE'])
@admin_required
def admin_alerts_delete(alert_id):
    try:
        res = supabase.table('emergency_alerts').delete().eq('id', alert_id).execute()
        if not res.data:
            return jsonify({'error': 'Not found'}), 404
        return jsonify({'status': 'ok'})
    except Exception as exc:
        return jsonify({'error': f'Delete failed: {exc}'}), 500


# ── Admin — resolved message config ──────────────────────────────────────────
@app.route('/admin/api/emergency-alerts/resolved-messages')
@admin_required
def admin_resolved_messages_get():
    config = _load_resolved_message_config()
    for p in ('Critical', 'Warning', 'Advisory'):
        if p not in config:
            config[p] = {'priority': p, 'useCustom': False, 'customMessage': '',
                         'updatedBy': '', 'updatedAt': '', 'previousMessage': ''}
    return jsonify({'ok': True, 'config': config})


@app.route('/admin/api/emergency-alerts/resolved-messages/<priority>', methods=['PUT'])
@admin_required
def admin_resolved_messages_put(priority):
    if priority not in ('Critical', 'Warning', 'Advisory'):
        return jsonify({'error': 'Invalid priority. Must be Critical, Warning, or Advisory.'}), 400
    d = request.get_json(silent=True) or {}
    use_custom     = bool(d.get('useCustom', False))
    custom_message = _clean(d.get('customMessage', ''), 2000)
    if use_custom and not custom_message.strip():
        return jsonify({'error': 'Custom message cannot be empty when enabled.'}), 400
    admin_name = _current_admin_name()
    now = datetime.now(timezone.utc).isoformat()
    try:
        prev = supabase.table('ea_resolved_messages').select('custom_message').eq('priority', priority).execute()
        previous_message = (prev.data[0].get('custom_message', '') if prev.data else '')
    except Exception:
        previous_message = ''
    row = {
        'priority':         priority,
        'use_custom':       use_custom,
        'custom_message':   custom_message,
        'updated_by':       admin_name,
        'updated_at':       now,
        'previous_message': previous_message,
    }
    try:
        supabase.table('ea_resolved_messages').upsert(row, on_conflict='priority').execute()
        return jsonify({'ok': True})
    except Exception as exc:
        return jsonify({'error': f'Save failed: {exc}'}), 500


# ── Public — emergency alert endpoints ────────────────────────────────────────
@app.route('/api/emergency-alerts/resolved-message')
def api_resolved_message():
    priority = request.args.get('priority', 'Advisory')
    if priority not in ('Critical', 'Warning', 'Advisory'):
        priority = 'Advisory'
    resp = jsonify({'message': _get_resolved_message(priority)})
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.route('/api/emergency-alerts')
def api_emergency_alerts_public():
    _auto_expire_alerts()
    alerts = _load_alerts()
    active = [a for a in alerts if a.get('status') == 'active']
    return jsonify({'status': 'ok', 'alerts': active})


_PRIORITY_ORDER = {'Critical': 0, 'Warning': 1, 'Advisory': 2}


@app.route('/api/emergency-alerts/active')
def api_emergency_alerts_active():
    _auto_expire_alerts()
    now_manila = _manila_now().strftime('%Y-%m-%dT%H:%M')
    alerts = _load_alerts()
    active = [
        a for a in alerts
        if a.get('status') == 'active'
        and (a.get('startDatetime') or '')[:16] <= now_manila
        and (a.get('expirationDatetime') or '')[:16] >= now_manila
    ]
    if not active:
        resp = jsonify({'active': False})
        resp.headers['Cache-Control'] = 'no-store'
        return resp
    active.sort(key=lambda a: _PRIORITY_ORDER.get(a.get('priority', 'Advisory'), 99))
    top = active[0]
    resp = jsonify({
        'active':             True,
        'id':                 top['id'],
        'title':              top['title'],
        'alertType':          top['alertType'],
        'priority':           top['priority'],
        'targetAudience':     top['targetAudience'],
        'targetArea':         top.get('targetArea', ''),
        'message':            top['message'],
        'instructions':       top.get('instructions', ''),
        'showBanner':         top.get('showBanner', True),
        'enablePopup':        top.get('enablePopup', False),
        'version':            top.get('version', 1),
        'updatedAt':          top.get('updatedAt', ''),
        'updatedBy':          top.get('updatedBy', ''),
        'startDatetime':      top.get('startDatetime', ''),
        'expirationDatetime': top.get('expirationDatetime', ''),
    })
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.route('/api/emergency-alerts/<alert_id>/public')
def api_emergency_alert_detail(alert_id):
    _auto_expire_alerts()
    try:
        res = (supabase.table('emergency_alerts')
               .select('*')
               .eq('id', alert_id)
               .eq('status', 'active')
               .limit(1)
               .execute())
        if not res.data:
            return jsonify({'error': 'Alert not found or no longer active.'}), 404
        alert = _row_to_alert(res.data[0])
        now_manila = _manila_now().strftime('%Y-%m-%dT%H:%M')
        if (alert.get('startDatetime') or '')[:16] > now_manila:
            return jsonify({'error': 'Alert not yet started.'}), 404
        if (alert.get('expirationDatetime') or '')[:16] < now_manila:
            return jsonify({'error': 'Alert has expired.'}), 404
        return jsonify({'active': True, 'alert': alert})
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


@app.route('/emergency-alerts/<slug>')
def emergency_alert_detail_page(slug):
    return send_from_directory(BASE_DIR, 'emergency-alert-detail.html')


# ── Static file serving ───────────────────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'index.html')


@app.route('/<path:filename>')
def static_files(filename):
    if filename.startswith('admin') or filename.startswith('data/'):
        abort(404)
    full = os.path.join(BASE_DIR, filename)
    if not os.path.exists(full):
        abort(404)
    return send_from_directory(BASE_DIR, filename)


# ── Bootstrap ─────────────────────────────────────────────────────────────────
_ensure_initial_user()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
