"""Finite installment schedules are materialized once, never cloned when marked paid."""
import json
import hashlib
import re
import secrets
from decimal import Decimal
from datetime import date
from calendar import monthrange
from werkzeug.exceptions import BadRequest
import db
import billease_security as security

MAX_PAYMENTS = 60


def init_schema():
    conn = db.get_conn()
    try:
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('''CREATE TABLE IF NOT EXISTS payment_plans (
                plan_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, request_key TEXT,
                first_number INTEGER NOT NULL, payment_count INTEGER NOT NULL,
                total_cents INTEGER NOT NULL, request_hash TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id,request_key))''')
            plan_columns = {r['name'] for r in conn.execute('PRAGMA table_info(payment_plans)')}
            if 'request_hash' not in plan_columns:
                conn.execute('ALTER TABLE payment_plans ADD COLUMN request_hash TEXT')
            columns = {r['name'] for r in conn.execute('PRAGMA table_info(bills)')}
            for name, kind in [('payment_plan_id', 'TEXT'), ('installment_number', 'INTEGER'), ('installment_count', 'INTEGER'), ('recurrence_day', 'INTEGER')]:
                if name not in columns:
                    conn.execute(f'ALTER TABLE bills ADD COLUMN {name} {kind}')
            conn.execute('''CREATE UNIQUE INDEX IF NOT EXISTS idx_bill_plan_number
                         ON bills(payment_plan_id,installment_number) WHERE payment_plan_id IS NOT NULL''')
    finally:
        conn.close()


def integer(value, minimum=1, maximum=MAX_PAYMENTS):
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not re.fullmatch(r'\d{1,3}', str(value)):
        raise BadRequest('מספר התשלומים אינו תקין')
    result = int(value)
    if not minimum <= result <= maximum:
        raise BadRequest('מספר התשלומים אינו תקין')
    return result


def money_cents(value):
    return int(Decimal(str(security.money(value))) * 100)


def monthly_dates(first, count):
    # Always use the original anchor day; 31 Jan -> 28 Feb -> 31 Mar.
    first = date.fromisoformat(first)
    result = []
    for offset in range(count):
        month = first.month - 1 + offset
        year, month = first.year + month // 12, month % 12 + 1
        result.append(date(year, month, min(first.day, monthrange(year, month)[1])).isoformat())
    return result


def validate(data):
    count = integer(data.get('installment_count'))
    start = integer(data.get('installment_start', 1), maximum=count)
    rows = data.get('installments')
    if not isinstance(rows, list) or not rows or len(rows) != count - start + 1:
        raise BadRequest('יש להזין סכום ותאריך לכל התשלומים שנותרו')
    schedule = []
    for item in rows:
        if not isinstance(item, dict):
            raise BadRequest('פרטי התשלומים אינם תקינים')
        amount = money_cents(item.get('amount'))
        due = security.due_date(security.text(item, 'due_date', 10, required=True))
        if schedule and due < schedule[-1]['due_date']:
            raise BadRequest('יש לסדר את התשלומים לפי תאריך')
        schedule.append(dict(amount_cents=amount, due_date=due))
    total = sum(row['amount_cents'] for row in schedule)
    if total > 99999999999:
        raise BadRequest('סכום התשלומים הכולל גדול מדי')
    expected = data.get('installment_total')
    if expected not in (None, '') and money_cents(expected) != total:
        raise BadRequest('סכום התשלומים אינו תואם לסכום הכולל. בדקו ותקנו לפני השמירה')
    key = data.get('request_key')
    if key is not None and (not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,80}', key)):
        raise BadRequest('מזהה הבקשה אינו תקין')
    return count, start, schedule, total, key


def create(user_id, supplier, category, image_path, source, data):
    count, start, schedule, total, key = validate(data)
    fingerprint = hashlib.sha256(json.dumps([supplier,category,image_path,source,count,start,schedule,total],sort_keys=True).encode()).hexdigest()
    conn = db.get_conn()
    try:
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            if key:
                existing = conn.execute('SELECT plan_id,request_hash FROM payment_plans WHERE user_id=? AND request_key=?', (user_id, key)).fetchone()
                if existing:
                    if existing['request_hash'] and existing['request_hash'] != fingerprint:
                        raise BadRequest('בקשה זו כבר נשמרה עם פרטים אחרים. בדקו את החשבונות לפני ניסיון נוסף')
                    rows = conn.execute('SELECT bill_id FROM bills WHERE payment_plan_id=? AND user_id=? ORDER BY installment_number', (existing['plan_id'], user_id)).fetchall()
                    return dict(ok=True, plan_id=existing['plan_id'], bill_ids=[r['bill_id'] for r in rows], already_created=True)
            plan_id = secrets.token_hex(16)
            conn.execute('INSERT INTO payment_plans(plan_id,user_id,request_key,first_number,payment_count,total_cents,request_hash) VALUES (?,?,?,?,?,?,?)',
                         (plan_id,user_id,key,start,count,total,fingerprint))
            ids = []
            for number, row in enumerate(schedule, start):
                cursor = conn.execute('''INSERT INTO bills(user_id,supplier,amount,category,due_date,is_paid,
                       is_recurring,recurrence,image_path,source,payment_plan_id,installment_number,installment_count)
                       VALUES (?,?,?,?,?,0,0,NULL,?,?,?,?,?)''',
                       (user_id,supplier,row['amount_cents']/100,category,row['due_date'],image_path,source,plan_id,number,count))
                ids.append(cursor.lastrowid)
            return dict(ok=True, plan_id=plan_id, bill_id=ids[0], bill_ids=ids, category=category, total=total/100)
    finally:
        conn.close()
