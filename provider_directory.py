"""Curated outbound destinations. No payment execution or user-supplied URLs."""
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

CATEGORIES = {
    'electricity': 'Electricity providers', 'gas': 'Gas providers', 'water': 'Water corporations',
    'telecom': 'Telecom, internet and TV', 'municipal': 'Municipalities and property tax',
    'insurance': 'Insurance providers', 'health': 'Health funds', 'transport': 'Tolls and parking',
    'government': 'Government fees and services', 'education': 'Universities and tuition',
    'subscriptions': 'Digital subscriptions',
}
CATALOG_PATH = Path(__file__).with_name('provider_catalog.json')


def safe_url(value):
    if not isinstance(value, str) or any(ord(c) < 33 for c in value) or '\\' in value:
        raise ValueError('Invalid destination URL')
    parts = urlsplit(value)
    if (parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.port
            or parts.fragment or not re.fullmatch(r'[a-z0-9.-]+', parts.hostname)):
        raise ValueError('Invalid destination URL')
    return value


def validate(catalog):
    if not isinstance(catalog, dict) or catalog.get('version') != 1 or not isinstance(catalog.get('providers'), list):
        raise ValueError('Invalid catalog')
    seen = set()
    for provider in catalog['providers']:
        if not isinstance(provider, dict):
            raise ValueError('Invalid provider')
        identifier = provider.get('id', '')
        if not re.fullmatch(r'[a-z0-9-]{1,60}', identifier) or identifier in seen:
            raise ValueError('Invalid provider ID')
        seen.add(identifier)
        if provider.get('category') not in CATEGORIES or provider.get('kind') not in ('official_site', 'payment_guidance', 'payment_page'):
            raise ValueError('Invalid provider type')
        names = provider.get('name', {})
        if not isinstance(names, dict) or set(names) != {'he', 'ar', 'en'} or any(not isinstance(n, str) or not n.strip() or len(n)>150 for n in names.values()):
            raise ValueError('Invalid provider names')
        safe_url(provider.get('url'));safe_url(provider.get('source_url'))
        if not isinstance(provider.get('aliases'), list) or any(not isinstance(v,str) or len(v)>120 for v in provider['aliases']):
            raise ValueError('Invalid provider aliases')
    return catalog


def get_catalog():
    return validate(json.loads(CATALOG_PATH.read_text(encoding='utf-8')))


def init_schema():
    import db
    conn = db.get_conn()
    try:
        with conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS provider_favorites (
                user_id TEXT NOT NULL, provider_id TEXT NOT NULL,
                PRIMARY KEY(user_id,provider_id))''')
            conn.execute('''CREATE TABLE IF NOT EXISTS provider_visits (
                visit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL, provider_id TEXT NOT NULL,
                requested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_provider_visits_user ON provider_visits(user_id,visit_id)')
    finally:
        conn.close()


def account_state(user_id):
    import db
    return dict(favorites=[r['provider_id'] for r in db.query('SELECT provider_id FROM provider_favorites WHERE user_id=?',(user_id,),fetch=True)],
                recent=db.query('''SELECT provider_id,MAX(visit_id) AS last_visit FROM provider_visits
                                WHERE user_id=? GROUP BY provider_id ORDER BY last_visit DESC LIMIT 8''',(user_id,),fetch=True))


def known(identifier):
    return any(p['id'] == identifier for p in get_catalog()['providers'])
