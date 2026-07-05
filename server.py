"""
BHOB Site — Flask server
Serves static files, weather/tide proxy, announcement management API, and secure admin auth.
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
from flask import Flask, jsonify, send_from_directory, abort, request, session

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Persistent storage root ───────────────────────────────────────────────────
# On Render (or any ephemeral host): set DATA_ROOT env var to a mounted
# persistent disk path (e.g. /var/data).  Locally: defaults to data/ in repo.
_DATA_ROOT = os.environ.get('DATA_ROOT', '').strip()
DATA_DIR        = _DATA_ROOT if _DATA_ROOT else os.path.join(BASE_DIR, 'data')
# Local dev → assets/ (Flask serves directly); Render → DATA_DIR (persistent disk)
UPLOAD_DIR      = (os.path.join(DATA_DIR, 'images', 'announcements') if _DATA_ROOT
                   else os.path.join(BASE_DIR, 'assets', 'images', 'announcements'))
PROJ_UPLOAD_DIR = (os.path.join(DATA_DIR, 'images', 'initiatives') if _DATA_ROOT
                   else os.path.join(BASE_DIR, 'assets', 'images', 'initiatives'))
FORMS_UPLOAD_DIR = (os.path.join(DATA_DIR, 'documents', 'forms') if _DATA_ROOT
                    else os.path.join(BASE_DIR, 'assets', 'documents', 'forms'))
ANN_FILE    = os.path.join(DATA_DIR, 'announcements.json')
PROJ_FILE   = os.path.join(DATA_DIR, 'community-initiatives.json')
FORMS_FILE  = os.path.join(DATA_DIR, 'forms.json')
USERS_FILE  = os.path.join(DATA_DIR, 'users.json')
AUDIT_FILE  = os.path.join(DATA_DIR, 'audit_logs.json')

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


# ── User management ───────────────────────────────────────────────────────────
def _load_users():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(USERS_FILE):
        return []
    try:
        with open(USERS_FILE, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def _save_users(users):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


def _get_user_by_username(username):
    for u in _load_users():
        if u.get('username', '').strip().lower() == username.strip().lower():
            return u
    return None


def _get_user_by_id(uid):
    if not uid:
        return None
    for u in _load_users():
        if u.get('id') == uid:
            return u
    return None


def _update_user(updated_user):
    """Persist changes to a single user record."""
    users = _load_users()
    for i, u in enumerate(users):
        if u.get('id') == updated_user.get('id'):
            updated_user['updatedAt'] = datetime.now(timezone.utc).isoformat()
            users[i] = updated_user
            _save_users(users)
            return True
    return False


def _ensure_initial_user():
    """
    Create the initial admin account on first startup (when users.json does not exist).

    Priority order for the password source:
      1. ADMIN_PWHASH env var — set this in your Render dashboard after changing
         the admin password so the change survives future redeploys.
      2. ADMIN_PASSWORD env var — plain-text initial password (force-change required).
      3. Auto-generated fallback Barangay@<year> (force-change required).

    IMPORTANT: users.json must NOT be committed to git (it is in .gitignore).
    If it is still tracked, run:
        git rm --cached data/users.json data/audit_logs.json
    and push — otherwise every deploy overwrites the live password.
    """
    users = _load_users()
    if users:
        return

    username   = os.environ.get('ADMIN_USERNAME', 'admin')
    saved_hash = os.environ.get('ADMIN_PWHASH', '').strip()
    force_pw   = False

    # Validate ADMIN_PWHASH format: must be "iterations:salt_hex:hash_hex"
    if saved_hash and len(saved_hash.split(':')) != 3:
        print('[BHOB] WARNING: ADMIN_PWHASH format invalid — falling back to ADMIN_PASSWORD.')
        saved_hash = ''

    if saved_hash:
        pw_hash  = saved_hash
        force_pw = False   # Already a user-chosen password; no forced change needed
        login_hint = '(restored from ADMIN_PWHASH env var)'
    else:
        plain_pw = os.environ.get('ADMIN_PASSWORD', '')
        if not plain_pw:
            plain_pw = f'Barangay@{datetime.now().year}'
            login_hint = f'Password  : {plain_pw}  ← auto-generated, CHANGE THIS'
        else:
            login_hint = 'Password  : (value of ADMIN_PASSWORD env var)'
        pw_hash  = _hash_pw(plain_pw)
        force_pw = True    # Plain-text credential — force change on first login

    now = datetime.now(timezone.utc).isoformat()
    user = {
        'id':                 uuid.uuid4().hex,
        'fullName':           'Barangay Admin',
        'username':           username,
        'email':              '',
        'passwordHash':       pw_hash,
        'role':               'admin',
        'status':             'active',
        'forcePasswordChange': force_pw,
        'failedLoginCount':   0,
        'lockedUntil':        None,
        'lastLoginAt':        None,
        'createdAt':          now,
        'updatedAt':          now,
    }
    _save_users([user])
    print('[BHOB] -------------------------------------------------')
    if saved_hash:
        print(f'[BHOB] Admin account restored from ADMIN_PWHASH env var.')
        print(f'[BHOB] Username : {username}')
    else:
        print(f'[BHOB] Initial admin account created.')
        print(f'[BHOB] Username : {username}')
        print(f'[BHOB] {login_hint}')
        print(f'[BHOB] Log in and change your password immediately.')
        if not os.environ.get('ADMIN_PASSWORD'):
            print(f'[BHOB] TIP: Set ADMIN_PASSWORD env var to control the initial password.')
    print('[BHOB] -------------------------------------------------')


# ── Audit logging ─────────────────────────────────────────────────────────────
def _audit(event_type, description, user_id=None, success=True):
    """
    Write a tamper-evident audit log entry.
    Never logs plain passwords, hashes, tokens, or secrets.
    """
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        logs = []
        if os.path.exists(AUDIT_FILE):
            try:
                with open(AUDIT_FILE, encoding='utf-8') as f:
                    logs = json.load(f)
            except Exception:
                logs = []
        entry = {
            'id':          uuid.uuid4().hex,
            'userId':      user_id,
            'eventType':   event_type,
            'description': description,
            'success':     success,
            'ipAddress':   request.remote_addr if request else None,
            'userAgent':   (request.headers.get('User-Agent', '')[:200]) if request else None,
            'createdAt':   datetime.now(timezone.utc).isoformat(),
        }
        logs.append(entry)
        if len(logs) > 2000:
            logs = logs[-2000:]
        with open(AUDIT_FILE, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # Audit failures must never break the application


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
def _load_ann():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(ANN_FILE):
        return []
    try:
        with open(ANN_FILE, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def _save_ann(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(ANN_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_proj():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(PROJ_FILE):
        return []
    try:
        with open(PROJ_FILE, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def _save_proj(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(PROJ_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_forms():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(FORMS_FILE):
        return []
    try:
        with open(FORMS_FILE, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def _save_forms(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(FORMS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _form_file_path(file_url):
    """Return absolute filesystem path for a stored form file URL."""
    if not file_url:
        return None
    if _DATA_ROOT and file_url.startswith('assets/documents/forms/'):
        rel = file_url[len('assets/'):]
        return os.path.join(DATA_DIR, rel)
    return os.path.join(BASE_DIR, file_url)


def _form_file_available(file_url):
    path = _form_file_path(file_url)
    return bool(path and os.path.isfile(path))


def _clean(val, maxlen=500):
    return str(val or '').strip()[:maxlen]


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
            raw = json.loads(resp.read().decode('utf-8'))
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
            raw = json.loads(resp.read().decode('utf-8'))
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


def _order_key(item):
    """Safe displayOrder sort key — None/missing items sort last."""
    v = item.get('displayOrder')
    return v if isinstance(v, (int, float)) else 9999


# ── Public announcements API ──────────────────────────────────────────────────
@app.route('/api/announcements')
def api_announcements():
    all_ann   = _load_ann()
    published = [a for a in all_ann if a.get('status') == 'published']
    # Two-pass stable sort: date desc (fallback), then displayOrder asc (primary)
    published.sort(key=lambda x: x.get('date', ''), reverse=True)
    published.sort(key=_order_key)
    return jsonify({'status': 'ok', 'announcements': published})


# ── Public community initiatives API ─────────────────────────────────────────
@app.route('/api/community-initiatives')
def api_community_initiatives():
    all_proj  = _load_proj()
    published = [p for p in all_proj if p.get('status') == 'published']
    # Two-pass stable sort: createdAt desc (fallback), then displayOrder asc (primary)
    published.sort(key=lambda x: x.get('createdAt', ''), reverse=True)
    published.sort(key=_order_key)
    return jsonify({'status': 'ok', 'initiatives': published})


# ── Public forms API ─────────────────────────────────────────────────────────
@app.route('/api/forms')
def api_forms():
    all_forms = _load_forms()
    published = [f for f in all_forms if f.get('status') == 'published']
    published.sort(key=lambda x: x.get('updatedAt', ''), reverse=True)
    published.sort(key=_order_key)
    for f in published:
        f['fileAvailable'] = _form_file_available(f.get('fileUrl', ''))
    return jsonify({'status': 'ok', 'forms': published})


# ── Public page clean URLs (no .html required) ───────────────────────────────
_PUBLIC_PAGES = [
    'about', 'officials', 'services', 'citizens-charter',
    'announcements', 'projects', 'transparency', 'downloads', 'contact',
]

@app.route('/<page_name>')
def public_page(page_name):
    if page_name in _PUBLIC_PAGES:
        f = os.path.join(BASE_DIR, page_name + '.html')
        if os.path.exists(f):
            return send_from_directory(BASE_DIR, page_name + '.html')
    # Fall through to static_files handler via abort so Flask picks the next rule
    abort(404)


# ── Admin page serving ────────────────────────────────────────────────────────
@app.route('/admin')
@app.route('/admin/')
@app.route('/admin/settings')
@app.route('/admin/community-initiatives')
@app.route('/admin/download-forms')
def admin_page():
    f = os.path.join(BASE_DIR, 'admin', 'index.html')
    if not os.path.exists(f):
        abort(404)
    return send_from_directory(os.path.join(BASE_DIR, 'admin'), 'index.html')


# ── Admin auth API ────────────────────────────────────────────────────────────
@app.route('/admin/login', methods=['POST'])
def admin_login():
    d        = request.get_json(silent=True) or {}
    username = _clean(d.get('username', ''), 100)
    password = str(d.get('password', ''))

    if not username or not password:
        return jsonify({'error': 'Invalid username or password.'}), 401

    user = _get_user_by_username(username)

    # Check existing lockout before doing anything else
    if user:
        locked_until = user.get('lockedUntil')
        if locked_until:
            try:
                lock_dt = datetime.fromisoformat(locked_until)
                if datetime.now(timezone.utc) < lock_dt:
                    remaining = max(1, int((lock_dt - datetime.now(timezone.utc)).total_seconds() / 60) + 1)
                    _audit('login_failed_locked', f'Login attempt while account locked: {username}',
                           user.get('id'), False)
                    return jsonify({
                        'error': f'Too many failed login attempts. Please try again in {remaining} minute(s).'
                    }), 401
                else:
                    # Lockout period has passed — reset
                    user['lockedUntil']       = None
                    user['failedLoginCount']  = 0
            except Exception:
                user['lockedUntil'] = None

    # Always run password check (prevents timing-based username enumeration)
    dummy_hash = '600000:' + '0' * 64 + ':' + '0' * 64
    pw_ok = bool(user) and _check_pw(password, user.get('passwordHash', dummy_hash))

    if not pw_ok:
        if user:
            user['failedLoginCount'] = user.get('failedLoginCount', 0) + 1
            if user['failedLoginCount'] >= MAX_FAILED_ATTEMPTS:
                user['lockedUntil'] = (
                    datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)
                ).isoformat()
                _update_user(user)
                _audit('account_locked',
                       f'Account locked after {MAX_FAILED_ATTEMPTS} failed attempts: {username}',
                       user.get('id'), False)
                return jsonify({
                    'error': f'Too many failed login attempts. Please try again in {LOCKOUT_MINUTES} minutes.'
                }), 401
            _update_user(user)
        _audit('login_failed', f'Failed login attempt: {username}',
               user.get('id') if user else None, False)
        return jsonify({'error': 'Invalid username or password.'}), 401

    # Check account status after verifying password
    if user.get('status') != 'active':
        _audit('login_failed', f'Login on inactive account: {username}', user.get('id'), False)
        return jsonify({'error': 'Invalid username or password.'}), 401

    # Successful login — reset failure counter and update last login
    user['failedLoginCount'] = 0
    user['lockedUntil']      = None
    user['lastLoginAt']      = datetime.now(timezone.utc).isoformat()
    _update_user(user)

    session.clear()
    session['admin_logged_in'] = True
    session['admin_user_id']   = user['id']
    session['admin_username']  = user['username']
    session['last_active']     = time.time()
    app.permanent_session_lifetime = timedelta(hours=2)
    session.permanent = True

    _audit('login_success', f'Successful login: {username}', user['id'], True)

    return jsonify({
        'ok':                True,
        'user':              user.get('username', ''),
        'fullName':          user.get('fullName', ''),
        'forcePasswordChange': bool(user.get('forcePasswordChange', False)),
    })


@app.route('/admin/logout', methods=['POST'])
def admin_logout():
    user_id  = session.get('admin_user_id')
    username = session.get('admin_username', '')
    _audit('logout', f'Admin logout: {username}', user_id, True)
    session.clear()
    return jsonify({'ok': True})


@app.route('/admin/check')
def admin_check():
    if not _session_valid():
        return jsonify({'logged_in': False})
    user = _get_user_by_id(session.get('admin_user_id'))
    if not user or user.get('status') != 'active':
        session.clear()
        return jsonify({'logged_in': False})
    return jsonify({
        'logged_in':           True,
        'user':                user.get('username', ''),
        'fullName':            user.get('fullName', ''),
        'role':                user.get('role', 'admin'),
        'forcePasswordChange': bool(user.get('forcePasswordChange', False)),
    })


# ── Change password ───────────────────────────────────────────────────────────
@app.route('/admin/api/change-password', methods=['POST'])
@admin_auth_only   # allows forcePasswordChange state — intentional
def admin_change_password():
    d          = request.get_json(silent=True) or {}
    current_pw = str(d.get('currentPassword', ''))
    new_pw     = str(d.get('newPassword', ''))
    confirm_pw = str(d.get('confirmPassword', ''))
    user_id    = session.get('admin_user_id')

    users = _load_users()
    user  = next((u for u in users if u.get('id') == user_id), None)
    if not user:
        return jsonify({'error': 'Unauthorized.'}), 401

    # --- Validate current password ---
    if not current_pw:
        return jsonify({'error': 'Current password is required.'}), 400
    if not _check_pw(current_pw, user.get('passwordHash', '')):
        _audit('password_change_failed', 'Wrong current password supplied', user_id, False)
        return jsonify({'error': 'Current password is incorrect.'}), 400

    # --- Validate new password ---
    if not new_pw:
        return jsonify({'error': 'New password is required.'}), 400
    if not confirm_pw:
        return jsonify({'error': 'Confirm password is required.'}), 400
    if new_pw != confirm_pw:
        return jsonify({'error': 'New password and confirm password do not match.'}), 400

    ok, msg = _validate_pw_strength(new_pw, user.get('username', ''), user.get('email', ''))
    if not ok:
        return jsonify({'error': msg}), 400

    if _check_pw(new_pw, user.get('passwordHash', '')):
        return jsonify({'error': 'New password must be different from your current password.'}), 400

    # --- Update password hash ---
    new_hash = _hash_pw(new_pw)
    for i, u in enumerate(users):
        if u.get('id') == user_id:
            users[i]['passwordHash']       = new_hash
            users[i]['forcePasswordChange'] = False
            users[i]['updatedAt']          = datetime.now(timezone.utc).isoformat()
            break
    _save_users(users)

    # Verify the save actually took effect before telling the client it succeeded
    verify_users = _load_users()
    verify_user  = next((u for u in verify_users if u.get('id') == user_id), None)
    if not verify_user or not _check_pw(new_pw, verify_user.get('passwordHash', '')):
        _audit('password_change_failed', 'Post-save verification failed', user_id, False)
        return jsonify({'error': 'Password update could not be saved. Please try again.'}), 500

    _audit('password_changed', 'Password changed successfully', user_id, True)

    # Log the new hash so it can be set as ADMIN_PWHASH in deployment env vars,
    # ensuring the change survives future redeploys on ephemeral hosting (e.g. Render).
    print('[BHOB] -------------------------------------------------')
    print('[BHOB] Admin password changed successfully.')
    print('[BHOB] To persist this password across redeploys, set the')
    print('[BHOB] following environment variable in your hosting dashboard:')
    print(f'[BHOB] ADMIN_PWHASH={new_hash}')
    print('[BHOB] -------------------------------------------------')

    # Invalidate session — require re-login with new password
    session.clear()

    return jsonify({
        'ok':      True,
        'message': 'Password changed successfully. Please log in with your new password.',
    })


# ── Admin — announcement CRUD ─────────────────────────────────────────────────
@app.route('/admin/api/announcements')
@admin_required
def admin_list():
    all_ann = _load_ann()
    # Sort by displayOrder asc (primary), updatedAt desc (secondary for unordered items)
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
    all_ann.append(ann)
    _save_ann(all_ann)
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
    all_ann = _load_ann()
    for a in all_ann:
        if a.get('id') in order_map:
            a['displayOrder'] = order_map[a['id']]
    _save_ann(all_ann)
    return jsonify({'status': 'ok'})


@app.route('/admin/api/announcements/<ann_id>', methods=['PUT'])
@admin_required
def admin_update(ann_id):
    d       = request.get_json(silent=True) or {}
    all_ann = _load_ann()
    idx     = next((i for i, a in enumerate(all_ann) if a.get('id') == ann_id), None)
    if idx is None:
        return jsonify({'error': 'Not found'}), 404
    a = all_ann[idx]
    for field, maxlen in [('title', 200), ('date', 20), ('category', 50),
                          ('shortDescription', 500), ('fullDetails', 10000), ('imageUrl', 300)]:
        if field in d:
            a[field] = _clean(d[field], maxlen)
    if 'status' in d and d['status'] in ('draft', 'published', 'hidden'):
        a['status'] = d['status']
    if 'featured' in d:
        a['featured'] = bool(d['featured'])
    if 'displayOrder' in d:
        try:
            a['displayOrder'] = int(d['displayOrder'])
        except (ValueError, TypeError):
            pass
    a['updatedAt'] = datetime.now(timezone.utc).isoformat()
    _save_ann(all_ann)
    return jsonify({'status': 'ok', 'announcement': a})


@app.route('/admin/api/announcements/<ann_id>', methods=['DELETE'])
@admin_required
def admin_delete(ann_id):
    all_ann  = _load_ann()
    filtered = [a for a in all_ann if a.get('id') != ann_id]
    if len(filtered) == len(all_ann):
        return jsonify({'error': 'Not found'}), 404
    _save_ann(filtered)
    return jsonify({'status': 'ok'})


# ── Admin — community initiatives CRUD ───────────────────────────────────────
@app.route('/admin/api/community-initiatives')
@admin_required
def admin_proj_list():
    all_proj = _load_proj()
    # Sort by displayOrder asc (primary), updatedAt desc (secondary for unordered items)
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
    all_proj = _load_proj()
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
    all_proj.append(proj)
    _save_proj(all_proj)
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
    all_proj = _load_proj()
    for p in all_proj:
        if p.get('id') in order_map:
            p['displayOrder'] = order_map[p['id']]
    _save_proj(all_proj)
    return jsonify({'status': 'ok'})


@app.route('/admin/api/community-initiatives/<proj_id>', methods=['PUT'])
@admin_required
def admin_proj_update(proj_id):
    d        = request.get_json(silent=True) or {}
    all_proj = _load_proj()
    idx      = next((i for i, p in enumerate(all_proj) if p.get('id') == proj_id), None)
    if idx is None:
        return jsonify({'error': 'Not found'}), 404
    p = all_proj[idx]
    for field, maxlen in [('title', 200), ('category', 100), ('subtitle', 300),
                          ('shortDescription', 500), ('fullDetails', 10000),
                          ('imageUrl', 300), ('buttonLabel', 100), ('buttonLink', 300)]:
        if field in d:
            p[field] = _clean(d[field], maxlen)
    if 'status' in d and d['status'] in ('draft', 'published', 'hidden'):
        p['status'] = d['status']
    if 'featured' in d:
        p['featured'] = bool(d['featured'])
    if 'displayOrder' in d:
        try:
            p['displayOrder'] = int(d['displayOrder'])
        except (ValueError, TypeError):
            pass
    p['updatedAt'] = datetime.now(timezone.utc).isoformat()
    _save_proj(all_proj)
    return jsonify({'status': 'ok', 'initiative': p})


@app.route('/admin/api/community-initiatives/<proj_id>', methods=['DELETE'])
@admin_required
def admin_proj_delete(proj_id):
    all_proj = _load_proj()
    filtered = [p for p in all_proj if p.get('id') != proj_id]
    if len(filtered) == len(all_proj):
        return jsonify({'error': 'Not found'}), 404
    _save_proj(filtered)
    return jsonify({'status': 'ok'})


# ── Admin — download forms CRUD ──────────────────────────────────────────────
@app.route('/admin/api/forms')
@admin_required
def admin_forms_list():
    all_forms = _load_forms()
    all_forms.sort(key=lambda x: x.get('updatedAt', ''), reverse=True)
    all_forms.sort(key=_order_key)
    for f in all_forms:
        f['fileAvailable'] = _form_file_available(f.get('fileUrl', ''))
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
    all_forms.append(form)
    _save_forms(all_forms)
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
    all_forms = _load_forms()
    for f in all_forms:
        if f.get('id') in order_map:
            f['displayOrder'] = order_map[f['id']]
    _save_forms(all_forms)
    return jsonify({'status': 'ok'})


@app.route('/admin/api/forms/<form_id>', methods=['PUT'])
@admin_required
def admin_forms_update(form_id):
    d         = request.get_json(silent=True) or {}
    all_forms = _load_forms()
    idx       = next((i for i, f in enumerate(all_forms) if f.get('id') == form_id), None)
    if idx is None:
        return jsonify({'error': 'Not found'}), 404
    f = all_forms[idx]
    for field, maxlen in [('title', 200), ('description', 500), ('fileUrl', 300),
                          ('fileName', 200), ('fileType', 10)]:
        if field in d:
            f[field] = _clean(d[field], maxlen)
    if 'fileSize' in d:
        try:
            f['fileSize'] = int(d['fileSize'])
        except (ValueError, TypeError):
            pass
    if 'status' in d and d['status'] in ('draft', 'published', 'hidden'):
        f['status'] = d['status']
    if 'displayOrder' in d:
        try:
            f['displayOrder'] = int(d['displayOrder'])
        except (ValueError, TypeError):
            pass
    f['updatedAt'] = datetime.now(timezone.utc).isoformat()
    _save_forms(all_forms)
    return jsonify({'status': 'ok', 'form': f})


@app.route('/admin/api/forms/<form_id>', methods=['DELETE'])
@admin_required
def admin_forms_delete(form_id):
    all_forms = _load_forms()
    target    = next((f for f in all_forms if f.get('id') == form_id), None)
    if not target:
        return jsonify({'error': 'Not found'}), 404
    # Delete the physical file if it exists
    file_path = _form_file_path(target.get('fileUrl', ''))
    if file_path and os.path.isfile(file_path):
        try:
            os.remove(file_path)
        except Exception:
            pass
    filtered = [f for f in all_forms if f.get('id') != form_id]
    _save_forms(filtered)
    return jsonify({'status': 'ok'})


# ── Image upload ──────────────────────────────────────────────────────────────
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

        # Downscale only — never upscale. Use a larger display-safe width
        # because cards may be viewed on high-DPI/Retina screens.
        max_w = 1800
        if img.width > max_w:
            new_h = int(img.height * max_w / img.width)
            img = img.resize((max_w, new_h), _PILImage.LANCZOS)

        out = _io.BytesIO()

        # Preserve transparent PNG/WebP when possible.
        if ext == 'png':
            img.save(out, format='PNG', optimize=True)
            return out.getvalue(), 'png'

        if ext == 'webp':
            img.save(out, format='WEBP', quality=94, method=6)
            return out.getvalue(), 'webp'

        # JPEG fallback: flatten transparency and use high quality with
        # 4:4:4 chroma to keep text/lines cleaner.
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
    fname = uuid.uuid4().hex + '.' + ext
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    with open(os.path.join(UPLOAD_DIR, fname), 'wb') as out:
        out.write(data)
    return jsonify({'status': 'ok', 'url': 'assets/images/announcements/' + fname})


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
    fname = uuid.uuid4().hex + '.' + ext
    os.makedirs(FORMS_UPLOAD_DIR, exist_ok=True)
    with open(os.path.join(FORMS_UPLOAD_DIR, fname), 'wb') as out:
        out.write(data)
    # Sanitize the original filename for display (strip path components)
    original_name = os.path.basename(f.filename)
    return jsonify({
        'status':   'ok',
        'url':      'assets/documents/forms/' + fname,
        'fileName': original_name,
        'fileType': ext,
        'fileSize': len(data),
    })


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
    fname = uuid.uuid4().hex + '.' + ext
    os.makedirs(PROJ_UPLOAD_DIR, exist_ok=True)
    with open(os.path.join(PROJ_UPLOAD_DIR, fname), 'wb') as out:
        out.write(data)
    return jsonify({'status': 'ok', 'url': 'assets/images/initiatives/' + fname})


# ── Static file serving ───────────────────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'index.html')


@app.route('/<path:filename>')
def static_files(filename):
    # Block direct filesystem access to admin and data directories
    if filename.startswith('admin') or filename.startswith('data/'):
        abort(404)
    # When DATA_ROOT is set, check DATA_DIR first for uploaded images and form files.
    if _DATA_ROOT and (filename.startswith('assets/images/') or
                       filename.startswith('assets/documents/forms/')):
        rel = filename[len('assets/'):]          # e.g. 'images/announcements/abc.jpg'
        data_file = os.path.join(DATA_DIR, rel)
        if os.path.isfile(data_file):
            return send_from_directory(os.path.dirname(data_file),
                                       os.path.basename(data_file))
    full = os.path.join(BASE_DIR, filename)
    if not os.path.exists(full):
        abort(404)
    return send_from_directory(BASE_DIR, filename)


# ── Bootstrap ─────────────────────────────────────────────────────────────────
def _ensure_seed_data():
    """
    Copy seed JSON files to DATA_DIR on the very first run only.
    Seeds live in data/seed/ (committed to git) so they are never the same
    file as the live data and can never accidentally overwrite it.
    An existing file is NEVER overwritten — runtime-created content is safe.
    """
    import shutil
    os.makedirs(DATA_DIR, exist_ok=True)
    seed_dir = os.path.join(BASE_DIR, 'data', 'seed')
    for fname in ('announcements.json', 'community-initiatives.json', 'forms.json'):
        dest = os.path.join(DATA_DIR, fname)
        if not os.path.exists(dest):
            src = os.path.join(seed_dir, fname)
            if os.path.exists(src):
                shutil.copy2(src, dest)
                print(f'[BHOB] Seeded {fname} -> {dest}')
    if _DATA_ROOT:
        print(f'[BHOB] Persistent storage: {DATA_DIR}')
    else:
        print(f'[BHOB] Local storage: {DATA_DIR}')
        print('[BHOB] Set DATA_ROOT env var to a Render persistent disk path to keep data across deploys.')


_ensure_seed_data()
_ensure_initial_user()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8768))
    print(f'BHOB Site server running at http://localhost:{port}')
    app.run(host='0.0.0.0', port=port, debug=False)
