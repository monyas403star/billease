"""One-way, opt-in Google Calendar sync. Durable SQLite queue; no bill writes."""
import hashlib
import json
import os
import secrets
import threading
import time
from datetime import date, timedelta
from urllib.parse import quote

import db

SCOPE = 'https://www.googleapis.com/auth/calendar.app.created'
API = 'https://www.googleapis.com/calendar/v3'
TOKEN = 'https://oauth2.googleapis.com/token'
WAKE = threading.Event()


def configured():
    return all(os.environ.get(k) for k in ('GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET',
               'GOOGLE_REDIRECT_URI', 'CALENDAR_TOKEN_KEY'))


def cipher():
    from cryptography.fernet import Fernet
    return Fernet(os.environ['CALENDAR_TOKEN_KEY'].encode())


def init_schema():
    conn = db.get_conn()
    try:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS google_calendar_links (
          user_id TEXT PRIMARY KEY, refresh_cipher TEXT NOT NULL, calendar_id TEXT NOT NULL,
          namespace TEXT NOT NULL, revision INTEGER DEFAULT 1, synced_revision INTEGER DEFAULT 0,
          next_attempt REAL DEFAULT 0, lease_until REAL DEFAULT 0, lease_owner TEXT,
          last_sync REAL, error TEXT, attempts INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS google_calendar_events (
          namespace TEXT, bill_id INTEGER, event_id TEXT, fingerprint TEXT,
          PRIMARY KEY(namespace,bill_id));
        CREATE TRIGGER IF NOT EXISTS gcal_bill_insert AFTER INSERT ON bills BEGIN
          UPDATE google_calendar_links SET revision=revision+1,next_attempt=0 WHERE user_id=NEW.user_id;
        END;
        CREATE TRIGGER IF NOT EXISTS gcal_bill_update AFTER UPDATE ON bills BEGIN
          UPDATE google_calendar_links SET revision=revision+1,next_attempt=0
          WHERE user_id=OLD.user_id OR user_id=NEW.user_id;
        END;
        CREATE TRIGGER IF NOT EXISTS gcal_bill_delete AFTER DELETE ON bills BEGIN
          UPDATE google_calendar_links SET revision=revision+1,next_attempt=0 WHERE user_id=OLD.user_id;
        END;
        CREATE TRIGGER IF NOT EXISTS gcal_language_update AFTER UPDATE OF preferred_language ON users BEGIN
          UPDATE google_calendar_links SET revision=revision+1,next_attempt=0 WHERE user_id=NEW.user_id;
        END;
        ''')
        conn.commit()
    finally:
        conn.close()


def event_body(bill, locale='en'):
    start = date.fromisoformat(bill['due_date'])
    labels = {'ar': ('مدفوعة', 'للدفع', 'قسط', 'من', 'موعد استحقاق؛ حالة الدفع مسجلة في BillEase.'),
              'he': ('שולם', 'לתשלום', 'תשלום', 'מתוך', 'מועד פירעון; מצב התשלום נרשם ב-BillEase.'),
              'en': ('Paid', 'Due', 'Installment', 'of', 'Due date; payment status recorded in BillEase.')}
    paid, due, installment, of, description = labels.get(locale, labels['en'])
    summary = f"{paid if bill['is_paid'] else due} · {bill['supplier']} · {float(bill['amount']):.2f} ₪"
    if bill.get('payment_plan_id'):
        summary += f" · {installment} {bill['installment_number']} {of} {bill['installment_count']}"
    return dict(summary=summary, description=description, start={'date': start.isoformat()},
                end={'date': (start + timedelta(days=1)).isoformat()},
                transparency='transparent', visibility='private',
                reminders={'useDefault': False}, colorId='10' if bill['is_paid'] else '5')


class SyncError(Exception):
    pass


def google(method, path, access, body=None):
    import requests
    return requests.request(method, API + path, headers={'Authorization': 'Bearer ' + access},
                            json=body, timeout=(5, 15), allow_redirects=False)


def claim():
    conn = db.get_conn()
    try:
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('''SELECT * FROM google_calendar_links
              WHERE revision>synced_revision AND next_attempt<=? AND lease_until<=?
              ORDER BY next_attempt LIMIT 1''', (time.time(), time.time())).fetchone()
            if not row:
                return None
            row = dict(row)
            row['lease_owner'] = secrets.token_hex(16)
            conn.execute('UPDATE google_calendar_links SET lease_owner=?,lease_until=? WHERE user_id=?',
                         (row['lease_owner'], time.time()+180, row['user_id']))
            return row
    finally:
        conn.close()


def still_linked(link):
    return bool(db.query('SELECT 1 FROM google_calendar_links WHERE user_id=? AND namespace=? AND lease_owner=?',
                        (link['user_id'], link['namespace'], link['lease_owner']), fetch=True, one=True))


def sync_one():
    import requests
    link = claim()
    if not link:
        return False
    error = None
    complete = False
    try:
        refresh = cipher().decrypt(link['refresh_cipher'].encode()).decode()
        response = requests.post(TOKEN, data=dict(grant_type='refresh_token', refresh_token=refresh,
            client_id=os.environ['GOOGLE_CLIENT_ID'], client_secret=os.environ['GOOGLE_CLIENT_SECRET']),
            timeout=(5,15), allow_redirects=False)
        if response.status_code != 200:
            raise SyncError('reconnect' if response.status_code in (400,401) else 'retry')
        access = response.json()['access_token']
        locale = db.query('SELECT preferred_language FROM users WHERE user_id=?',
                          (link['user_id'],), fetch=True, one=True) or {}
        rows = db.query('SELECT * FROM bills WHERE user_id=? ORDER BY bill_id',
                        (link['user_id'],), fetch=True)
        existing = {r['bill_id']: r for r in db.query('SELECT * FROM google_calendar_events WHERE namespace=?',
                    (link['namespace'],), fetch=True)}
        prefix = '/calendars/' + quote(link['calendar_id'], safe='') + '/events'
        operations = []
        for b in rows:
            body = event_body(b, locale.get('preferred_language','en'))
            fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
            old = existing.pop(b['bill_id'], None)
            if not old or old['fingerprint'] != fingerprint:
                eid = 'b' + hashlib.sha256(f"{link['namespace']}:{b['bill_id']}".encode()).hexdigest()
                operations.append((b['bill_id'], eid, body, fingerprint, bool(old)))
        operations += [(bid,r['event_id'],None,None,True) for bid,r in existing.items()]
        # Bounded batches keep the database lease longer than all possible HTTP calls.
        for bid,eid,body,fp,known in operations[:3]:
            if not still_linked(link):
                return True
            path = prefix + '/' + eid
            if body is None:
                response = google('DELETE', path, access)
                if response.status_code not in (204,404,410):
                    raise SyncError('retry')
                db.query('DELETE FROM google_calendar_events WHERE namespace=? AND bill_id=?', (link['namespace'],bid))
            else:
                response = google('PUT', path, access, body) if known else google('POST', prefix, access, dict(body,id=eid))
                if response.status_code == 409:
                    response = google('PUT', path, access, body)
                if response.status_code == 404 and known:
                    response = google('POST', prefix, access, dict(body,id=eid))
                if response.status_code not in (200,201):
                    raise SyncError('reconnect' if response.status_code in (401,403,404,410) else 'retry')
                db.query('INSERT OR REPLACE INTO google_calendar_events VALUES(?,?,?,?)',
                         (link['namespace'],bid,eid,fp))
        complete = len(operations) <= 3
    except SyncError as exc:
        error = str(exc)
    except Exception:
        # Never log OAuth tokens, codes, response bodies or bill contents.
        error = 'retry'
    finally:
        delay = min(3600, 30 * 2**min(link['attempts'],7)) if error else 0
        if error == 'reconnect':
            delay = 86400
        db.query('''UPDATE google_calendar_links SET synced_revision=?,next_attempt=?,lease_until=0,
          lease_owner=NULL,last_sync=CASE WHEN ? THEN ? ELSE last_sync END,error=?,attempts=?
          WHERE user_id=? AND namespace=? AND lease_owner=?''',
          (link['revision'] if complete and not error else link['synced_revision'], time.time()+delay,
           complete and not error,time.time(),error,link['attempts']+1 if error else 0,
           link['user_id'],link['namespace'],link['lease_owner']))
    return True


def setup(app, need_login):
    from flask import jsonify, redirect, request, session
    init_schema()

    def oauth(**kwargs):
        from requests_oauthlib import OAuth2Session
        return OAuth2Session(os.environ['GOOGLE_CLIENT_ID'], scope=[SCOPE],
                             redirect_uri=os.environ['GOOGLE_REDIRECT_URI'], **kwargs)

    @app.get('/api/calendar/google/status')
    def google_status():
        if not need_login():
            return jsonify(ok=False),401
        row = db.query('SELECT error,last_sync,revision,synced_revision FROM google_calendar_links WHERE user_id=?',
                       (session['user_id'],),fetch=True,one=True)
        return jsonify(ok=True, configured=configured(), connected=bool(row),
                       pending=bool(row and row['revision']>row['synced_revision']),
                       error=row['error'] if row else None, last_sync=row['last_sync'] if row else None)

    @app.post('/api/calendar/google/connect')
    def google_connect():
        if not need_login():
            return jsonify(ok=False),401
        if not configured():
            return jsonify(ok=False),503
        if db.query('SELECT 1 FROM google_calendar_links WHERE user_id=?',(session['user_id'],),fetch=True,one=True):
            return jsonify(ok=False),409
        verifier = secrets.token_urlsafe(48)
        import base64
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        url,state = oauth().authorization_url('https://accounts.google.com/o/oauth2/v2/auth',
            access_type='offline', prompt='consent select_account', code_challenge=challenge, code_challenge_method='S256')
        session['gcal_oauth'] = dict(state=state, verifier=verifier, user_id=session['user_id'],
                                    version=session.get('auth_version'), expires=time.time()+600)
        return jsonify(ok=True,url=url)

    @app.get('/oauth/google/calendar/callback')
    def google_callback():
        saved = session.pop('gcal_oauth', {})
        valid = (need_login() and saved.get('user_id')==session.get('user_id') and
                 saved.get('version')==session.get('auth_version') and saved.get('expires',0)>time.time() and
                 secrets.compare_digest(saved.get('state',''),request.args.get('state','')) and bool(saved.get('state')))
        target = '/calendar?google=error'
        app.logger.warning(
            "[Google Calendar] callback check: valid=%s saved=%s denied=%s configured=%s",
            bool(valid),
            bool(saved),
            bool(request.args.get('error')),
            configured()
        )
        if valid and not request.args.get('error') and configured():
            # One OAuth flow at a time per account; existing links must be disconnected explicitly.
            conn=db.get_conn()
            try:
                with conn:
                    conn.execute('BEGIN IMMEDIATE')
                    if conn.execute('SELECT 1 FROM google_calendar_links WHERE user_id=?',(session['user_id'],)).fetchone():
                        return redirect('/calendar?google=connected',303)
                    token = oauth(state=saved['state']).fetch_token(TOKEN,code=request.args.get('code'),
                         client_secret=os.environ['GOOGLE_CLIENT_SECRET'],code_verifier=saved['verifier'],timeout=20)
                    if not token.get('refresh_token') or SCOPE not in token.get('scope',[]):
                        raise ValueError('grant')
                    encrypted = cipher().encrypt(token['refresh_token'].encode()).decode()
                    response = google('POST','/calendars',token['access_token'],
                        dict(summary='BillEase',timeZone='Asia/Jerusalem',description='BillEase bill due dates'))
                    if response.status_code not in (200,201):
                        raise ValueError('calendar')
                    conn.execute('INSERT INTO google_calendar_links(user_id,refresh_cipher,calendar_id,namespace) VALUES(?,?,?,?)',
                        (session['user_id'],encrypted,response.json()['id'],secrets.token_hex(16)))
                    target='/calendar?google=connected'
                WAKE.set()
            except Exception as exc:
                app.logger.error(
                    "[Google Calendar] callback failed: %s",
                    type(exc).__name__
                )
            finally:
                conn.close()
        response=redirect(target,303)
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Cache-Control']='no-store'
        return response

    @app.post('/api/calendar/google/disconnect')
    def google_disconnect():
        if not need_login():
            return jsonify(ok=False),401
        conn=db.get_conn()
        try:
            with conn:
                row=conn.execute('SELECT * FROM google_calendar_links WHERE user_id=?',(session['user_id'],)).fetchone()
                if row:
                    conn.execute('DELETE FROM google_calendar_links WHERE user_id=?',(session['user_id'],))
                    conn.execute('DELETE FROM google_calendar_events WHERE namespace=?',(row['namespace'],))
        finally:
            conn.close()
        revoked=False
        if row:
            try:
                import requests
                token=cipher().decrypt(row['refresh_cipher'].encode()).decode()
                revoked=requests.post('https://oauth2.googleapis.com/revoke',data={'token':token},timeout=(5,10)).status_code==200
            except Exception:
                pass
        return jsonify(ok=True,revoked=revoked)

    @app.after_request
    def wake_calendar(response):
        if request.method in ('POST','PUT','PATCH','DELETE') and response.status_code<400:
            WAKE.set()
        if request.path.startswith('/oauth/google/calendar/'):
            response.headers['Referrer-Policy']='no-referrer'
            response.headers['Cache-Control']='no-store'
        return response

    def loop():
        while True:
            WAKE.wait(10)
            WAKE.clear()
            if configured():
                try:
                    for _ in range(10):
                        if not sync_one():
                            break
                except Exception:
                    pass
    if os.environ.get('CALENDAR_BACKGROUND','1')=='1':
        threading.Thread(target=loop,daemon=True,name='google-calendar').start()
