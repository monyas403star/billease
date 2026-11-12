import os
import sys
import tempfile
import unittest
from pathlib import Path
from flask import Flask, session
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import db
import budget_planner as bp

class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.previous=os.environ.get('BILLEASE_DB_PATH')
        os.environ['BILLEASE_DB_PATH']=str(Path(self.tmp.name)/'test.db')
        db.query('CREATE TABLE bills(bill_id INTEGER PRIMARY KEY,user_id TEXT,supplier TEXT,amount REAL,category TEXT,due_date TEXT,is_paid INTEGER)')
        self.app=Flask(__name__);self.app.secret_key='test-only'
        bp.setup(self.app,lambda: bool(session.get('user_id')),lambda: {})
        self.client=self.app.test_client()
        with self.client.session_transaction() as s:s['user_id']='alice'
        self.plan={'mode':'household','month':'2026-11','expenses':[], 'incomes':[]}
    def tearDown(self):
        if self.previous is None:os.environ.pop('BILLEASE_DB_PATH',None)
        else:os.environ['BILLEASE_DB_PATH']=self.previous
        self.tmp.cleanup()
    def row(self,amount,period='monthly',due='',category='other'):
        return dict(name='Test',amount=amount,period=period,date=due,category=category)
    def save(self):return self.client.put('/api/budget-planner',json=self.plan)
    def test_login_required(self):
        c=self.app.test_client()
        self.assertEqual(c.get('/api/budget-planner').status_code,401)
        self.assertEqual(c.put('/api/budget-planner',json=self.plan).status_code,401)
    def test_bills_count_once_paid_and_unpaid_and_isolated(self):
        for uid,amt,due,paid in [('alice',100,'2026-11-01',1),('alice',200,'2026-11-15',0),('bob',900,'2026-11-01',0),('alice',800,'2026-12-01',0)]:
            db.query('INSERT INTO bills(user_id,supplier,amount,due_date,is_paid) VALUES(?,?,?,?,?)',(uid,'Supplier',amt,due,paid))
        self.plan['incomes']=[self.row('1000')];self.plan['expenses']=[self.row('50')]
        for _ in range(2):
            data=self.save().json
            self.assertEqual(data['summary']['balance'],'650.00')
            self.assertEqual(len(data['bills']),2)
        self.assertEqual(db.query('SELECT COUNT(*) n FROM bills',fetch=True,one=True)['n'],4)
    def test_periods_and_one_time_month(self):
        self.plan['incomes']=[self.row('8000')]
        self.plan['expenses']=[self.row('1200','yearly'),self.row('120','weekly'),self.row('20','once','2026-11-30'),self.row('999','once','2026-12-01')]
        self.assertEqual(self.save().json['summary']['expenses'],'640.00')
    def test_shortfall(self):
        self.plan['incomes']=[self.row('10000')];self.plan['expenses']=[self.row('11500')]
        s=self.save().json['summary'];self.assertEqual(s['shortfall'],'1500.00');self.assertEqual(s['surplus'],'0')
    def test_invalid_inputs_do_not_overwrite(self):
        self.assertEqual(self.save().status_code,200)
        for value in ['NaN','Infinity','-1',True,'10000001','garbage']:
            self.plan['expenses']=[self.row(value)]
            self.assertEqual(self.save().status_code,400)
        self.assertEqual(self.client.get('/api/budget-planner').json['plan']['expenses'],[])
        self.plan['expenses']=[self.row(10,'once','2026-02-30')]
        self.assertEqual(self.save().status_code,400)
    def test_plans_are_account_private(self):
        self.plan['incomes']=[self.row(1234)];self.plan['user_id']='bob';self.save()
        with self.client.session_transaction() as s:s['user_id']='bob'
        self.assertEqual(self.client.get('/api/budget-planner').json['plan']['incomes'],[])
    def test_edit_and_reload(self):
        self.plan['expenses']=[self.row('10.005')];self.save()
        self.assertEqual(self.client.get('/api/budget-planner').json['plan']['expenses'][0]['amount'],'10.01')
        self.plan['expenses']=[];self.save()
        self.assertEqual(self.client.get('/api/budget-planner').json['summary']['expenses'],'0')

if __name__=='__main__':unittest.main()
