"""Account language is authoritative after sign-in; cookie is only an anonymous fallback."""
import json
import re
from pathlib import Path
from flask import request, redirect, has_request_context, g, session
from werkzeug.exceptions import BadRequest
import db

CATALOG = json.loads(Path(__file__).with_name('translations.json').read_text(encoding='utf-8'))
LANGUAGES = {'he': 'עברית', 'ar': 'العربية', 'en': 'English'}


def init_schema():
    conn = db.get_conn()
    try:
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            columns = {r['name'] for r in conn.execute('PRAGMA table_info(users)')}
            if 'preferred_language' not in columns:
                conn.execute("ALTER TABLE users ADD COLUMN preferred_language TEXT NOT NULL DEFAULT 'he'")
    finally:
        conn.close()


def parse_language(value):
    if not isinstance(value, str) or value not in LANGUAGES:
        raise BadRequest('בחרו עברית, ערבית או אנגלית')
    return value


def account_language(user_id):
    row = db.query('SELECT preferred_language FROM users WHERE user_id=?', (user_id,), fetch=True, one=True)
    return row['preferred_language'] if row and row['preferred_language'] in LANGUAGES else 'he'


def language():
    if not has_request_context():
        return 'he'
    value = getattr(g, 'ui_language', None) or request.cookies.get('billease_language', 'he')
    return value if value in LANGUAGES else 'he'


def use_language(value):
    if has_request_context():
        g.ui_language = parse_language(value)


def translate_in(locale, source, **values):
    text = CATALOG[locale if locale in LANGUAGES else 'he'].get(source, source)
    for name, value in values.items():
        text = text.replace('{' + name + '}', str(value))
    return text


def translate(source, **values):
    return translate_in(language(), source, **values)


def translate_message(source):
    if not isinstance(source, str):
        return source
    match = re.fullmatch(r'שנת התשלום אינה יכולה להיות אחרי (\d{4})', source)
    if match:
        return translate('שנת התשלום אינה יכולה להיות אחרי {year}', year=match[1])
    return translate(source)


def setup(app):
    @app.before_request
    def load_account_language():
        user_id = session.get('user_id')
        if isinstance(user_id, str) and user_id:
            # A signed cookie identifies the account; no client-provided user ID controls this preference.
            g.ui_language = account_language(user_id)

    @app.context_processor
    def ui_context():
        locale = language()
        return dict(t=translate, locale=locale, text_direction='ltr' if locale == 'en' else 'rtl',
                    ui_catalog=CATALOG[locale], languages=LANGUAGES,
                    ui_catalogs=CATALOG if request.endpoint in ('register_page', 'root') else None)

    @app.post('/language')
    def change_language():
        # Compatibility with an already-open page from the previous release.
        locale = parse_language(request.form.get('language'))
        user_id = session.get('user_id')
        if user_id:
            import billease_security as security
            if session.get('auth_version') != security.version(user_id):
                raise BadRequest('יש להתחבר מחדש לפני שינוי שפה')
            db.query('UPDATE users SET preferred_language=? WHERE user_id=?', (locale, user_id))
        use_language(locale)
        target = request.form.get('next', '/')
        if not target.startswith('/') or target.startswith('//') or '\\' in target or any(ord(c) < 32 for c in target):
            target = '/'
        return redirect(target, code=303)

    @app.after_request
    def localize_response(response):
        locale = language()
        response.headers['Content-Language'] = locale
        response.vary.add('Cookie')
        if getattr(g, 'ui_language', None) and request.cookies.get('billease_language') != locale:
            response.set_cookie('billease_language', locale, max_age=365 * 24 * 60 * 60,
                                httponly=True, samesite='Lax', secure=app.config.get('SESSION_COOKIE_SECURE', False))
        if response.is_json:
            data = response.get_json(silent=True)
            if isinstance(data, dict):
                changed = False
                for key in ('error', 'msg', 'ocr_error', 'ocr_notice'):
                    if isinstance(data.get(key), str):
                        data[key] = translate_message(data[key]); changed = True
                if changed:
                    response.set_data(app.json.dumps(data))
        return response
