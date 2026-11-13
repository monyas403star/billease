import os
import sys
import tempfile
import unittest
from pathlib import Path
from flask import Flask, session
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import db
import user_feedback

class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old=os.environ.get('BILLEASE_DB_PATH')
        os.environ['BILLEASE_DB_PATH']=str(Path(self.tmp.name)/'feedback.db')
        db.query('CREATE TABLE users(user_id TEXT PRIMARY KEY,full_name TEXT)')
        db.query('INSERT INTO users VALUES(?,?)',('alice','Alice'))
        root=Path(__file__).resolve().parents[1]
        self.app=Flask(__name__,template_folder=str(root/'templates'));self.app.secret_key='test-only'
        for endpoint in ('root','home_page','logout','admin_page','assistant_page'):
            self.app.add_url_rule('/'+endpoint,endpoint,lambda:'test')
        self.app.context_processor(lambda:dict(t=lambda x:x,locale='en',text_direction='ltr',ui_catalog={},ui_catalogs=None))
        user_feedback.setup(self.app,lambda:bool(session.get('user_id')),
            lambda:dict(user_id=session.get('user_id'),is_admin=session.get('admin',False)),
            lambda:session.get('admin',False))
        self.client=self.app.test_client()
        with self.client.session_transaction() as s:s['user_id']='alice'
        self.client.get('/feedback')
        with self.client.session_transaction() as s:self.csrf=s['feedback_csrf']
        self.data=dict(csrf=self.csrf,rating='5',helpful='Calendar',had_issue='0',issue='',suggestion='More colors')
    def tearDown(self):
        if self.old is None:os.environ.pop('BILLEASE_DB_PATH',None)
        else:os.environ['BILLEASE_DB_PATH']=self.old
        self.tmp.cleanup()
    def test_authentication_and_admin_authorization(self):
        guest=self.app.test_client()
        self.assertEqual(guest.get('/feedback').status_code,302)
        self.assertEqual(guest.post('/feedback',data=self.data).status_code,302)
        self.assertEqual(self.client.get('/admin/feedback').status_code,403)
    def test_csrf(self):
        for token in ('','wrong'):
            self.assertEqual(self.client.post('/feedback',data=dict(self.data,csrf=token)).status_code,403)
    def test_update_does_not_duplicate_or_spoof_owner(self):
        self.client.post('/feedback',data=dict(self.data,user_id='bob'))
        self.client.post('/feedback',data=dict(self.data,rating='3'))
        rows=db.query('SELECT * FROM user_feedback',fetch=True)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['rating'],3);self.assertEqual(rows[0]['user_id'],'alice')
    def test_validation(self):
        for change in (dict(rating='6'),dict(rating='2.5'),dict(helpful=''),dict(had_issue='1',issue=''),dict(suggestion='x'*2001)):
            self.assertEqual(self.client.post('/feedback',data=dict(self.data,**change)).status_code,400)
        self.assertEqual(db.query('SELECT COUNT(*) n FROM user_feedback',fetch=True,one=True)['n'],0)
    def test_escape_feedback_and_admin_stats(self):
        self.client.post('/feedback',data=dict(self.data,helpful='<script>alert(1)</script>'))
        with self.client.session_transaction() as s:s['admin']=True
        page=self.client.get('/admin/feedback')
        self.assertEqual(page.status_code,200)
        html=page.get_data(as_text=True)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;',html)
        self.assertIn('5.0 / 5',html)
    def test_private_saved_answers_and_success(self):
        response=self.client.post('/feedback',data=self.data,follow_redirects=True)
        self.assertIn('Thank you!',response.get_data(as_text=True))
        with self.client.session_transaction() as s:s['user_id']='bob';s.pop('feedback_csrf',None)
        self.assertNotIn('More colors',self.client.get('/feedback').get_data(as_text=True))
    def test_pagination_and_no_problem_discards_details(self):
        self.client.post('/feedback',data=dict(self.data,issue='stale details'))
        self.assertEqual(db.query('SELECT issue FROM user_feedback',fetch=True,one=True)['issue'],'')
        for i in range(21):db.query('INSERT INTO user_feedback(user_id,rating,helpful,had_issue,issue,suggestion) VALUES(?,5,?,0,?,?)',(str(i),'Help','',''))
        with self.client.session_transaction() as s:s['admin']=True
        html=self.client.get('/admin/feedback?page=2').get_data(as_text=True)
        self.assertEqual(html.count('class="card feedback-entry"'),2)

if __name__=='__main__':unittest.main()
