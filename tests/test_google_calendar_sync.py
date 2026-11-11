import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cryptography.fernet import Fernet
TEMP=tempfile.TemporaryDirectory()
os.environ.update(BILLEASE_DB_PATH=str(Path(TEMP.name)/'calendar.db'),
    BILLEASE_UPLOAD_DIR=str(Path(TEMP.name)/'uploads'),CALENDAR_BACKGROUND='0',NOTIFICATIONS_BACKGROUND='0',
    SECRET_KEY='isolated-test-secret',GOOGLE_CLIENT_ID='test-client',GOOGLE_CLIENT_SECRET='test-secret',
    GOOGLE_REDIRECT_URI='https://example.com/oauth/google/calendar/callback',
    CALENDAR_TOKEN_KEY=Fernet.generate_key().decode())
import app
import db
import google_calendar_sync as g
import billease_security as security


def response(status=200,body=None):
    r=Mock(status_code=status)
    r.json.return_value=body or {'access_token':'test-access'}
    return r


class CalendarSync(unittest.TestCase):
    def setUp(self):
        for table in ('google_calendar_events','google_calendar_links','bills','users'):
            db.query('DELETE FROM '+table)
        for uid in ('alice','bob'):
            db.query('INSERT INTO users(user_id,full_name,email,preferred_language) VALUES(?,?,?,?)',
                     (uid,uid,uid+'@example.com','ar'))
        self.client=app.app.test_client()
        with self.client.session_transaction() as s:
            s['user_id']='alice';s['auth_version']=security.version('alice')

    def link(self,uid='alice'):
        db.query('INSERT INTO google_calendar_links(user_id,refresh_cipher,calendar_id,namespace) VALUES(?,?,?,?)',
                 (uid,g.cipher().encrypt(b'refresh').decode(),'test-calendar',uid+'-namespace'))

    def bill(self,uid='alice',due='2026-12-31'):
        return db.query('INSERT INTO bills(user_id,supplier,amount,due_date,is_paid) VALUES(?,?,?,?,0)',
                        (uid,'מים العربية',12.34,due))

    def test_no_login_and_isolation(self):
        self.assertEqual(app.app.test_client().get('/api/calendar/google/status').status_code,401)
        self.link('bob');self.bill('bob');self.bill()
        with patch('requests.post',return_value=response()),patch.object(g,'google',return_value=response()) as api:
            g.sync_one()
            self.assertEqual(api.call_count,1)
        self.assertFalse(self.client.get('/api/calendar/google/status').json['connected'])

    def test_callback_rejects_state_without_google_calls(self):
        with patch('requests_oauthlib.OAuth2Session.fetch_token') as fetch:
            r=self.client.get('/oauth/google/calendar/callback?state=wrong&code=secret')
            self.assertEqual(r.status_code,303);self.assertIn('error',r.location);fetch.assert_not_called()

    def test_connect_uses_state_pkce_offline_and_minimal_scope(self):
        from urllib.parse import urlsplit,parse_qs
        r=self.client.post('/api/calendar/google/connect')
        args=parse_qs(urlsplit(r.json['url']).query)
        self.assertEqual(args['scope'],[g.SCOPE]);self.assertEqual(args['access_type'],['offline'])
        self.assertEqual(args['code_challenge_method'],['S256'])
        with self.client.session_transaction() as s:
            self.assertEqual(args['state'],[s['gcal_oauth']['state']])
        self.assertEqual(self.client.post('/api/calendar/google/connect',headers={'Origin':'https://evil.example'}).status_code,403)

    def test_callback_stores_encrypted_refresh_and_queues_existing_bills(self):
        self.bill()
        self.client.post('/api/calendar/google/connect')
        with self.client.session_transaction() as s:state=s['gcal_oauth']['state']
        with patch('requests_oauthlib.OAuth2Session.fetch_token',return_value=dict(access_token='access',refresh_token='refresh',scope=[g.SCOPE])),patch.object(g,'google',return_value=response(200,{'id':'calendar'})):
            r=self.client.get('/oauth/google/calendar/callback?state='+state+'&code=code')
        self.assertIn('connected',r.location)
        row=db.query('SELECT * FROM google_calendar_links',fetch=True,one=True)
        self.assertNotEqual(row['refresh_cipher'],'refresh');self.assertEqual(g.cipher().decrypt(row['refresh_cipher'].encode()),b'refresh')
        self.assertGreater(row['revision'],row['synced_revision'])
        self.assertNotIn('refresh',str(self.client.get('/api/calendar/google/status').json))

    def test_create_pay_delete_and_idempotency(self):
        self.link();bid=self.bill()
        with patch('requests.post',return_value=response()),patch.object(g,'google',return_value=response()) as api:
            g.sync_one();self.assertEqual(api.call_count,1)
            body=api.call_args.args[3]
            self.assertEqual(body['start'],{'date':'2026-12-31'})
            self.assertEqual(body['end'],{'date':'2027-01-01'})
            self.assertIn('للدفع',body['summary']);eid=body['id']
            self.assertFalse(g.sync_one());self.assertEqual(api.call_count,1)
            db.query('UPDATE bills SET is_paid=1 WHERE bill_id=?',(bid,));g.sync_one()
            self.assertEqual(api.call_args.args[0],'PUT');self.assertTrue(api.call_args.args[1].endswith(eid))
            self.assertIn('مدفوعة',api.call_args.args[3]['summary'])
            db.query('DELETE FROM bills WHERE bill_id=?',(bid,))
            api.return_value=response(204);g.sync_one()
            self.assertEqual(api.call_args.args[0],'DELETE')
            self.assertEqual(db.query('SELECT * FROM google_calendar_events',fetch=True),[])

    def test_lost_insert_response_reuses_deterministic_id(self):
        self.link();self.bill()
        with patch('requests.post',return_value=response()),patch.object(g,'google',side_effect=[response(409),response()]) as api:
            g.sync_one()
            self.assertEqual(api.call_args_list[0].args[3]['id'],api.call_args_list[1].args[1].split('/')[-1])

    def test_failure_keeps_bills_and_retries(self):
        self.link();self.bill()
        with patch('requests.post',side_effect=TimeoutError):g.sync_one()
        row=db.query('SELECT * FROM google_calendar_links',fetch=True,one=True)
        self.assertEqual(row['error'],'retry');self.assertGreater(row['next_attempt'],0)
        self.assertGreater(row['revision'],row['synced_revision'])
        self.assertEqual(len(db.query('SELECT * FROM bills',fetch=True)),1)

    def test_lease_prevents_two_workers_and_batches_all_installments(self):
        self.link()
        for _ in range(5):self.bill()
        first=g.claim();self.assertIsNotNone(first);self.assertIsNone(g.claim())
        db.query('UPDATE google_calendar_links SET lease_until=0')
        with patch('requests.post',return_value=response()),patch.object(g,'google',return_value=response()) as api:
            g.sync_one();self.assertEqual(api.call_count,3)
            g.sync_one();self.assertEqual(api.call_count,5)
            self.assertFalse(g.sync_one())

    def test_disconnect_preserves_bills_and_other_account(self):
        self.link();self.link('bob');self.bill()
        with patch('requests.post',return_value=response()):
            self.assertTrue(self.client.post('/api/calendar/google/disconnect').json['ok'])
        self.assertEqual(len(db.query('SELECT * FROM bills',fetch=True)),1)
        self.assertEqual(db.query('SELECT user_id FROM google_calendar_links',fetch=True),[{'user_id':'bob'}])

    def test_ui_three_languages(self):
        for language in ('ar','he','en'):
            db.query('UPDATE users SET preferred_language=? WHERE user_id=?',(language,'alice'))
            r=self.client.get('/calendar')
            self.assertEqual(r.status_code,200)
            self.assertIn('google-cal-connect',r.text);self.assertIn('js/google_calendar.js',r.text)


if __name__=='__main__':unittest.main()
