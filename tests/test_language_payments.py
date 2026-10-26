import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
TEMP = tempfile.TemporaryDirectory()
os.environ['BILLEASE_DB_PATH'] = str(Path(TEMP.name) / 'test.db')
os.environ['BILLEASE_UPLOAD_DIR'] = str(Path(TEMP.name) / 'uploads')
os.environ['NOTIFICATIONS_BACKGROUND'] = '0'
os.environ['SECRET_KEY'] = 'test-key-not-used-in-production'
import app
import db
import ocr
import scheduler
import email_text


class LanguagePayments(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()
        self.mail = patch('mailer.send_email', return_value=True).start()
        self.addCleanup(patch.stopall)

    def register(self, locale='ar', uid='test-user'):
        return self.client.post('/api/register', json=dict(user_id=uid, full_name='Test', email='test@example.com', phone='', password='Password123!', language=locale))

    def test_registration_persistence_and_email(self):
        self.assertEqual(self.register().status_code, 200)
        self.assertIn('أهلاً', self.mail.call_args.args[1])
        self.client.set_cookie('billease_language', 'en')
        self.assertIn('<html lang="ar"', self.client.get('/dashboard').text)
        self.client.get('/logout')
        other = app.app.test_client()
        self.assertEqual(other.post('/api/login', json={'user_id':'test-user','password':'Password123!'}).status_code, 200)
        self.assertIn('<html lang="ar"', other.get('/dashboard').text)
        other.get('/logout')
        response = other.get('/register')
        self.assertEqual(response.text.count('name="language" value='), 4)
        self.assertNotIn('language-select', response.text)

    def test_finite_schedule_and_transaction(self):
        self.assertEqual(self.register('en', 'payments-user').status_code, 200)
        payload=dict(supplier='Supplier', amount=1200, due_date='2026-11-30', installments=[{'amount':100,'due_date':'2026-11-30'},{'amount':99.5,'due_date':'2026-12-31'}])
        r=self.client.post('/api/bills',json=payload)
        self.assertEqual(r.status_code,200, r.text)
        rows=db.query('SELECT * FROM bills WHERE user_id=?',('payments-user',),fetch=True)
        self.assertEqual([x['amount'] for x in rows],[100,99.5])
        self.assertTrue(all(not x['is_recurring'] for x in rows))
        payload['installments'][1]['due_date']='2026-02-30'
        self.assertEqual(self.client.post('/api/bills',json=payload).status_code,400)
        self.assertEqual(len(db.query('SELECT * FROM bills WHERE user_id=?',('payments-user',),fetch=True)),2)
        conn=db.get_conn()
        with conn:
            conn.execute('UPDATE bills SET is_paid=1 WHERE bill_id=?',(rows[0]['bill_id'],))
            event=scheduler.queue_payment(conn,rows[0]['bill_id'],'payments-user')
        conn.close()
        saved=db.query('SELECT * FROM bill_email_events WHERE event_id=?',(event,),fetch=True,one=True)
        self.assertIn('marked as paid',saved['subject'])
        self.assertIn('100.00',saved['body'])

    def test_ocr_payment_evidence(self):
        field=lambda value:{'value':value,'evidence':'visible label and value'}
        payload=dict(document_type='invoice', supplier=field('Supplier'), amount=field('1200'), due_date=field('2026-11-30'), currency='ILS', category=None, installments=[{'amount':field('100'),'due_date':field('2026-11-30')},{'amount':field('100'),'due_date':field('2026-12-31')}])
        result=ocr._validated(payload)
        self.assertEqual(result['amount'],100)
        self.assertEqual(len(result['installments']),2)
        payload['installments'][1]['amount']['evidence']=''
        self.assertEqual(ocr._validated(payload)['installments'],[])
        payload['currency']='USD'
        self.assertEqual(ocr._validated(payload)['installments'],[])

    def test_recovery_uses_account_language(self):
        self.assertEqual(self.register('en','recover-user').status_code,200)
        self.client.get('/logout')
        self.client.set_cookie('billease_language','he')
        self.assertEqual(self.client.post('/api/recover/request',json={'user_id':'recover-user'}).status_code,200)
        self.assertIn('Reset your',self.mail.call_args.args[1])

    def test_all_mail_types_in_three_languages(self):
        for locale, greeting in [('he', 'שלום'), ('ar', 'مرحباً'), ('en', 'Hello')]:
            for kind in ('paid', 'deleted', 'seven_days', 'overdue'):
                with self.subTest(locale=locale, kind=kind):
                    subject, body = email_text.bill(locale, kind, 'Name', 'Supplier', '99.50', '30/11/2026')
                    self.assertIn(greeting, body)
                    self.assertIn('99.50', body)
                    self.assertIn('30/11/2026', body)
                    self.assertIn('BillEase', subject)

    def test_invalid_language_and_recurring_installments(self):
        self.assertEqual(self.register(['ar'], 'bad-locale').status_code, 400)
        self.assertEqual(self.register('he', 'validation-user').status_code, 200)
        payload=dict(supplier='Supplier', amount=100, due_date='2026-11-30', is_recurring=True, installments=[{'amount':100,'due_date':'2026-11-30'}])
        self.assertEqual(self.client.post('/api/bills',json=payload).status_code,400)
        self.assertEqual(db.query('SELECT COUNT(*) AS n FROM bills WHERE user_id=?',('validation-user',),fetch=True,one=True)['n'],0)

    def test_language_route_and_account_override(self):
        self.assertEqual(self.register('he', 'switch-user').status_code, 200)
        response=self.client.post('/language',data={'language':'en','next':'//example.com'})
        self.assertEqual(response.location,'/')
        self.assertEqual(db.query('SELECT language FROM users WHERE user_id=?',('switch-user',),fetch=True,one=True)['language'],'en')
        self.assertIn('<html lang="en" dir="ltr">',self.client.get('/dashboard').text)

    def test_explicit_shekel_symbols_and_amount_formats(self):
        for currency in ('ILS', 'NIS', '₪', 'ש״ח', 'ש"ח', 'שח', 'شيكل', 'شيقل'):
            with self.subTest(currency=currency):
                result=ocr._validated(dict(document_type='invoice', currency=currency,
                    amount={'value':'1,234.50','evidence':'Total 1,234.50'}, installments=[]))
                self.assertEqual(result['amount'],1234.50)
        self.assertTrue(ocr._is_ils(None, {'evidence':'לתשלום 120.00 ש״ח'}))
        self.assertFalse(ocr._is_ils(None, {'evidence':'Total 120.00'}))
        self.assertFalse(ocr._is_ils('USD', {'evidence':'120 ₪'}))
        self.assertIsNone(ocr._amount_value('1,23'))
        self.assertIsNone(ocr._amount_value('1,234,50'))


if __name__ == '__main__':
    unittest.main()
