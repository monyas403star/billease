"""Account-private monthly planning. Saved bills plus explicitly additional costs."""
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from flask import request, session, jsonify, render_template, redirect
import db

CATEGORIES = ['housing', 'utilities', 'food', 'transport', 'communications', 'insurance',
              'health', 'children', 'education', 'pets', 'debt', 'clothes', 'leisure',
              'subscriptions', 'gifts', 'care', 'other']
PERIODS = ('monthly', 'weekly', 'yearly', 'once')


def money(value):
    if isinstance(value, bool):
        raise ValueError('amount')
    try:
        n = Decimal(str(value))
        if not n.is_finite() or n < 0 or n > 10000000:
            raise ValueError('amount')
        return n.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError):
        raise ValueError('amount')


def validate(data):
    if not isinstance(data, dict) or data.get('mode') not in ('personal', 'household'):
        raise ValueError('mode')
    month = data.get('month', '')
    if not isinstance(month, str) or not re.fullmatch(r'\d{4}-\d{2}', month):
        raise ValueError('month')
    date.fromisoformat(month + '-01')
    if not 2000 <= int(month[:4]) <= 2300:
        raise ValueError('month')
    result = dict(mode=data['mode'], month=month)
    for group in ('expenses', 'incomes'):
        rows = data.get(group, [])
        if not isinstance(rows, list) or len(rows) > 150:
            raise ValueError('rows')
        result[group] = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError('row')
            name = row.get('name', '')
            category = row.get('category', 'other')
            period = row.get('period', '')
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
                raise ValueError('name')
            if category not in CATEGORIES or period not in PERIODS:
                raise ValueError('period')
            due = row.get('date', '')
            if period == 'once':
                if not isinstance(due, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', due):
                    raise ValueError('date')
                date.fromisoformat(due)
            else:
                due = ''
            result[group].append(dict(name=name.strip(), category=category,
                amount=str(money(row.get('amount'))), period=period, date=due))
    return result


def equivalent(row, month):
    amount = money(row['amount'])
    if row['period'] == 'weekly':
        amount *= Decimal(52) / Decimal(12)
    elif row['period'] == 'yearly':
        amount /= 12
    elif row['period'] == 'once' and row['date'][:7] != month:
        amount = Decimal(0)
    return amount.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)


def summarize(plan, bills):
    income = sum((equivalent(r, plan['month']) for r in plan['incomes']), Decimal(0))
    additional = sum((equivalent(r, plan['month']) for r in plan['expenses']), Decimal(0))
    saved = sum((money(b['amount']) for b in bills), Decimal(0))
    balance = income - additional - saved
    return {k: str(v) for k, v in dict(income=income, additional=additional, bills=saved,
            expenses=additional+saved, balance=balance, surplus=max(balance, Decimal(0)),
            shortfall=max(-balance, Decimal(0))).items()}


def setup(app, need_login, current_user):
    db.query('''CREATE TABLE IF NOT EXISTS budget_plans (
        user_id TEXT PRIMARY KEY, payload TEXT NOT NULL,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP)''')

    @app.get('/budget-planner')
    def budget_planner_page():
        if not need_login():
            return redirect('/')
        return render_template('budget_planner.html', user=current_user())

    @app.route('/api/budget-planner', methods=['GET', 'PUT'])
    def budget_planner_api():
        if not need_login():
            return jsonify(ok=False), 401
        uid = session['user_id']
        if request.method == 'PUT':
            try:
                plan = validate(request.get_json(silent=True))
            except (ValueError, TypeError, OverflowError):
                return jsonify(ok=False, error='Check the names, amounts and dates.'), 400
            db.query('''INSERT INTO budget_plans(user_id,payload) VALUES(?,?)
                ON CONFLICT(user_id) DO UPDATE SET payload=excluded.payload,updated_at=CURRENT_TIMESTAMP''',
                (uid, json.dumps(plan, ensure_ascii=False)))
        else:
            row = db.query('SELECT payload FROM budget_plans WHERE user_id=?', (uid,), fetch=True, one=True)
            plan = json.loads(row['payload']) if row else dict(mode='personal', month=date.today().strftime('%Y-%m'), expenses=[], incomes=[])
        bills = db.query('''SELECT bill_id,supplier,amount,category,due_date,is_paid FROM bills
            WHERE user_id=? AND substr(due_date,1,7)=? ORDER BY due_date,bill_id''',
            (uid, plan['month']), fetch=True)
        return jsonify(ok=True, plan=plan, bills=bills, summary=summarize(plan, bills))
