"""Request-scoped UI language. Stored in the account, with a cookie fallback before sign-in."""
import json
import re
from pathlib import Path
from flask import request, redirect, url_for, has_request_context, session, g
import db

CATALOG = json.loads(Path(__file__).with_name('translations.json').read_text(encoding='utf-8'))
LANGUAGES = {'he': 'עברית', 'ar': 'العربية', 'en': 'English'}


def language():
    if not has_request_context():
        return 'he'
    if hasattr(g, 'ui_language'):
        return g.ui_language
    value = request.cookies.get('billease_language', 'he')
    if session.get('user_id'):
        row = db.query('SELECT language FROM users WHERE user_id=?', (session['user_id'],), fetch=True, one=True)
        if row:
            value = row['language']
    g.ui_language = value if value in LANGUAGES else 'he'
    return value if value in LANGUAGES else 'he'


def translate(source, **values):
    text = CATALOG[language()].get(source, source)
    for name, value in values.items():
        text = text.replace('{' + name + '}', str(value))
    return text


def translate_message(source):
    if not isinstance(source, str):
        return source
    match = re.fullmatch(r'שנת התשלום אינה יכולה להיות אחרי (\d{4})', source)
    if match:
        return translate('שנת התשלום אינה יכולה להיות אחרי {year}', year=match[1])
    return translate(source)


def setup(app):
    @app.context_processor
    def ui_context():
        locale = language()
        return dict(t=translate, locale=locale, text_direction='ltr' if locale == 'en' else 'rtl',
                    ui_catalog=CATALOG[locale], languages=LANGUAGES)

    @app.post('/language')
    def change_language():
        locale = request.form.get('language')
        if locale not in LANGUAGES:
            return ('Invalid language', 400)
        if session.get('user_id'):
            db.query('UPDATE users SET language=? WHERE user_id=?', (locale, session['user_id']))
        g.ui_language = locale
        target = request.form.get('next', '/')
        if not target.startswith('/') or target.startswith('//') or '\\' in target or any(ord(c) < 32 for c in target):
            target = '/'
        response = redirect(target, code=303)
        response.set_cookie('billease_language', locale, max_age=365 * 24 * 60 * 60,
                            httponly=True, samesite='Lax', secure=app.config.get('SESSION_COOKIE_SECURE', False))
        return response

    @app.after_request
    def localize_response(response):
        response.headers['Content-Language'] = language()
        response.vary.add('Cookie')
        if response.is_json:
            data = response.get_json(silent=True)
            if isinstance(data, dict):
                # Translate application-owned messages only, never names, amounts, IDs or category keys.
                changed = False
                for key in ('error', 'msg', 'ocr_error', 'ocr_notice'):
                    if isinstance(data.get(key), str):
                        data[key] = translate_message(data[key])
                        changed = True
                if changed:
                    response.set_data(app.json.dumps(data))
        return response
