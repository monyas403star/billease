"""Validation and persistent authentication state for the existing SQLite app."""
import hashlib
import hmac
import os
import re
import secrets
import time
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo
from werkzeug.exceptions import BadRequest
from werkzeug.security import generate_password_hash, check_password_hash
import db


def init_schema():
    conn = db.get_conn()
    try:
        with conn:
            conn.executescript('''
            CREATE TABLE IF NOT EXISTS app_security_settings (
                name TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS account_security (
                user_id TEXT PRIMARY KEY, version INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS password_reset_codes (
                user_id TEXT PRIMARY KEY, code_hash TEXT NOT NULL,
                expires REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS auth_rate_limits (
                bucket TEXT PRIMARY KEY, started REAL NOT NULL, attempts INTEGER NOT NULL);
            ''')
            conn.execute('INSERT OR IGNORE INTO app_security_settings VALUES (?, ?)',
                         ('session_secret', secrets.token_hex(32)))
    finally:
        conn.close()


def session_secret():
    # Persistent random fallback replaces the old publicly known config secret.
    # An explicitly configured SECRET_KEY remains preferred.
    return os.environ.get('SECRET_KEY', '').strip() or db.query(
        'SELECT value FROM app_security_settings WHERE name=?',
        ('session_secret',), fetch=True, one=True)['value']


def json_object(request):
    value = request.get_json()
    if not isinstance(value, dict):
        raise BadRequest('נדרש אובייקט JSON')
    return value


def text(data, key, maximum=200, required=False):
    value = data.get(key, '')
    if value is None:
        value = ''
    if not isinstance(value, str):
        raise BadRequest('סוג שדה אינו תקין')
    value = value.strip()
    if len(value) > maximum or any(ord(c) < 32 for c in value) or '<' in value or '>' in value:
        raise BadRequest('תוכן שדה אינו תקין')
    if required and not value:
        raise BadRequest('חסרים שדות חובה')
    return value


def password(data, key, new=False, optional=False):
    value = data.get(key, '')
    if not isinstance(value, str):
        raise BadRequest('סיסמה אינה תקינה')
    if optional and value == '':
        return value
    if len(value) > 256 or not value or (new and len(value) < 8):
        raise BadRequest('סיסמה חדשה חייבת להכיל 8 עד 256 תווים' if new else 'סיסמה אינה תקינה')
    return value


def email(value):
    if len(value) > 254 or not re.fullmatch(r"[^\s@<>]+@[^\s@<>.]+(?:\.[^\s@<>.]+)+", value):
        raise BadRequest('כתובת האימייל אינה תקינה')
    return value


def money(value, allow_zero=False):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise BadRequest('סכום אינו תקין')
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or (amount == 0 and not allow_zero) or amount > Decimal('999999999.99'):
            raise InvalidOperation
        if amount != amount.quantize(Decimal('0.01')):
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        raise BadRequest('יש להזין סכום חיובי ועד שתי ספרות אחרי הנקודה' if not allow_zero
                         else 'יש להזין סכום שאינו שלילי ועד שתי ספרות אחרי הנקודה')
    return float(amount)


def today():
    return datetime.now(ZoneInfo('Asia/Jerusalem')).date()


def due_date(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise BadRequest('תאריך אינו תקין')
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise BadRequest('תאריך אינו קיים בלוח השנה')
    if parsed.year > today().year + 5:
        raise BadRequest(f'שנת התשלום אינה יכולה להיות אחרי {today().year + 5}')
    return parsed.isoformat()


def hash_password(value):
    return generate_password_hash(value, method='scrypt:32768:8:1')


def password_matches(stored, value):
    if not isinstance(stored, str):
        return False
    if re.fullmatch(r'[0-9a-fA-F]{64}', stored):
        return hmac.compare_digest(stored.lower(), hashlib.sha256(value.encode()).hexdigest())
    try:
        return check_password_hash(stored, value)
    except (ValueError, TypeError):
        return False


def legacy_hash(stored):
    return isinstance(stored, str) and re.fullmatch(r'[0-9a-fA-F]{64}', stored) is not None


def version(user_id):
    row = db.query('SELECT version FROM account_security WHERE user_id=?',
                   (user_id,), fetch=True, one=True)
    return row['version'] if row else 0


def bump_version(conn, user_id):
    conn.execute('''INSERT INTO account_security(user_id,version) VALUES (?,1)
                    ON CONFLICT(user_id) DO UPDATE SET version=version+1''', (user_id,))


def rate_allowed(scope, subject, limit, window=900):
    # SQLite makes this counter work across threads/workers/restarts.
    key = hashlib.sha256((scope + ':' + subject).encode()).hexdigest()
    now = time.time()
    conn = db.get_conn()
    try:
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('DELETE FROM auth_rate_limits WHERE started<?', (now - 86400,))
            row = conn.execute('SELECT * FROM auth_rate_limits WHERE bucket=?', (key,)).fetchone()
            if row and now - row['started'] < window:
                if row['attempts'] >= limit:
                    return False
                conn.execute('UPDATE auth_rate_limits SET attempts=attempts+1 WHERE bucket=?', (key,))
            else:
                conn.execute('INSERT OR REPLACE INTO auth_rate_limits VALUES (?,?,1)', (key, now))
        return True
    finally:
        conn.close()


def reset_digest(user_id, code, key):
    return hmac.new(key.encode(), (user_id + ':' + code).encode(), hashlib.sha256).hexdigest()


def save_reset(user_id, code, key):
    digest = reset_digest(user_id, code, key)
    db.query('INSERT OR REPLACE INTO password_reset_codes VALUES (?,?,?,0)',
             (user_id, digest, time.time() + 600))
    return digest


def apply_reset(user_id, code, new_hash, key):
    conn = db.get_conn()
    try:
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT * FROM password_reset_codes WHERE user_id=?', (user_id,)).fetchone()
            if row is None:
                return False
            if row['expires'] < time.time() or row['attempts'] >= 5:
                conn.execute('DELETE FROM password_reset_codes WHERE user_id=?', (user_id,))
                return False
            if not hmac.compare_digest(row['code_hash'], reset_digest(user_id, code, key)):
                conn.execute('UPDATE password_reset_codes SET attempts=attempts+1 WHERE user_id=?', (user_id,))
                return False
            conn.execute('UPDATE users SET password_hash=? WHERE user_id=?', (new_hash, user_id))
            bump_version(conn, user_id)
            conn.execute('DELETE FROM password_reset_codes WHERE user_id=?', (user_id,))
            return True
    finally:
        conn.close()
