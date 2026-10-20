"""Transactional email outbox for BillEase; dates use Asia/Jerusalem.

Status 'sent' means accepted by the email provider, not verified inbox delivery.
The outbox must live on durable storage to survive restarts/redeployments.
"""
import logging
import os
import threading
import time
import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import db
import mailer

logger = logging.getLogger(__name__)
_started = False
_start_lock = threading.Lock()
_wake = threading.Event()
_run_lock = threading.Lock()


def local_today():
    return datetime.now(ZoneInfo('Asia/Jerusalem')).date()


def init_schema():
    conn = db.get_conn()
    try:
        with conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS bill_email_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    bill_id INTEGER NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('paid', 'seven_days', 'overdue')),
                    due_date TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK(status IN ('pending', 'sending', 'sent', 'cancelled', 'failed')),
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt REAL NOT NULL DEFAULT 0,
                    claim_token TEXT,
                    lease_until REAL,
                    created_at REAL NOT NULL,
                    sent_at REAL,
                    UNIQUE(user_id, bill_id, kind, due_date)
                )
            ''')
            conn.execute('''CREATE INDEX IF NOT EXISTS idx_bill_email_pending
                            ON bill_email_events(status, next_attempt, lease_until)''')
    finally:
        conn.close()


def _insert_event(conn, row, kind, today):
    due = date.fromisoformat(str(row['due_date'])[:10])
    full_name = row['full_name'] or ''
    supplier = row['supplier'] or 'הספק'
    amount = f"{float(row['amount']):.2f}"
    due_text = due.strftime('%d/%m/%Y')
    details = f'ספק: {supplier}\nסכום: {amount} ש״ח\nמועד לתשלום: {due_text}'
    if kind == 'paid':
        subject = 'BillEase — החשבון סומן כשולם'
        body = (f'שלום {full_name},\n\nהחשבון הבא סומן כשולם במערכת BillEase:\n'
                f'{details}\n\nזהו אישור רישום במערכת, ולא אישור סליקה מהספק.')
    elif kind == 'seven_days':
        subject = 'BillEase — תזכורת: מועד התשלום מתקרב'
        body = (f'שלום {full_name},\n\nמועד התשלום חל במהלך שבעת הימים הקרובים:\n{details}\n\n'
                'אם שילמתם, סמנו את החשבון כשולם באתר.')
    else:
        subject = 'BillEase — חשבון באיחור בתשלום'
        body = (f'שלום {full_name},\n\nמועד התשלום של החשבון הבא עבר והוא עדיין מסומן כפתוח:\n'
                f'{details}\n\nאם שילמתם, עדכנו את מצב החשבון באתר.')
    conn.execute('''
        INSERT INTO bill_email_events
            (user_id, bill_id, kind, due_date, recipient, subject, body,
             idempotency_key, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, bill_id, kind, due_date) DO NOTHING
    ''', (row['user_id'], row['bill_id'], kind, due.isoformat(), row['email'] or '',
          subject, body, str(uuid.uuid4()), time.time()))
    event = conn.execute('''SELECT event_id FROM bill_email_events
                            WHERE user_id=? AND bill_id=? AND kind=? AND due_date=?''',
                         (row['user_id'], row['bill_id'], kind, due.isoformat())).fetchone()
    return event['event_id']


def queue_payment(conn, bill_id, user_id):
    """Use the same transaction as marking paid, so a failed commit sends no email."""
    row = conn.execute('''
        SELECT b.*, u.email, u.full_name FROM bills b
        JOIN users u ON u.user_id=b.user_id
        WHERE b.bill_id=? AND b.user_id=? AND b.is_paid=1
    ''', (bill_id, user_id)).fetchone()
    if row is None:
        return None
    conn.execute('''UPDATE bill_email_events SET status='cancelled', claim_token=NULL,
                    lease_until=NULL WHERE bill_id=? AND user_id=?
                    AND kind!='paid' AND status='pending' ''', (bill_id, user_id))
    return _insert_event(conn, row, 'paid', local_today())


def _eligible(conn, event, today):
    row = conn.execute('''SELECT is_paid, due_date FROM bills
                          WHERE bill_id=? AND user_id=?''',
                       (event['bill_id'], event['user_id'])).fetchone()
    if row is None:
        return False
    if event['kind'] == 'paid':
        return bool(row['is_paid'])
    if row['is_paid'] or str(row['due_date'])[:10] != event['due_date']:
        return False
    due = date.fromisoformat(event['due_date'])
    if event['kind'] == 'overdue':
        return due < today
    return 1 <= (due - today).days <= 7


def queue_reminders(today=None):
    today = today or local_today()
    conn = db.get_conn()
    queued = 0
    try:
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            rows = conn.execute('''SELECT b.*, u.email, u.full_name FROM bills b
                                    JOIN users u ON u.user_id=b.user_id
                                    WHERE b.is_paid=0''').fetchall()
            for row in rows:
                try:
                    due = date.fromisoformat(str(row['due_date'])[:10])
                    amount = float(row['amount'])
                    if amount <= 0 or not (amount < float('inf')):
                        continue
                except (TypeError, ValueError):
                    continue
                days = (due - today).days
                kind = 'overdue' if days < 0 else 'seven_days' if 1 <= days <= 7 else None
                if kind is None:
                    continue
                before = conn.total_changes
                _insert_event(conn, row, kind, today)
                queued += conn.total_changes - before
    finally:
        conn.close()
    return queued


def _claim(event_id=None, today=None):
    today = today or local_today()
    conn = db.get_conn()
    now = time.time()
    try:
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute("""UPDATE bill_email_events SET status='failed', claim_token=NULL,
                         lease_until=NULL WHERE status='sending' AND lease_until<?
                         AND attempts>=8""", (now,))
            sql = '''SELECT * FROM bill_email_events WHERE attempts < 8
                     AND next_attempt<=? AND (status='pending' OR
                     (status='sending' AND lease_until<?))'''
            args = [now, now]
            if event_id is not None:
                sql += ' AND event_id=?'
                args.append(event_id)
            sql += " ORDER BY CASE WHEN kind='paid' THEN 0 ELSE 1 END, event_id LIMIT 25"
            for event in conn.execute(sql, args).fetchall():
                if not _eligible(conn, event, today):
                    conn.execute("UPDATE bill_email_events SET status='cancelled' WHERE event_id=?",
                                 (event['event_id'],))
                    continue
                if not event['recipient'].strip():
                    conn.execute("UPDATE bill_email_events SET status='failed' WHERE event_id=?",
                                 (event['event_id'],))
                    continue
                token = str(uuid.uuid4())
                conn.execute('''UPDATE bill_email_events SET status='sending',
                                attempts=attempts+1, claim_token=?, lease_until=?
                                WHERE event_id=?''', (token, now + 180, event['event_id']))
                return dict(event, claim_token=token, attempts=event['attempts'] + 1)
    finally:
        conn.close()
    return None


def deliver_pending(event_id=None, today=None, max_seconds=45):
    """Claim briefly in SQLite; release its lock before making network requests."""
    today = today or local_today()
    stats = dict(sent=0, failed=0, attempted=0)
    deadline = time.monotonic() + max_seconds
    while time.monotonic() < deadline:
        event = _claim(event_id, today)
        if event is None:
            break
        try:
            # Recheck eligibility after the claim and before the network call.
            conn = db.get_conn()
            try:
                eligible = _eligible(conn, event, today)
            finally:
                conn.close()
            accepted = eligible and mailer.send_email(
                event['recipient'], event['subject'], event['body'],
                idempotency_key=event['idempotency_key'])
        except Exception:
            eligible, accepted = True, False
            logger.exception('[notifications] email attempt failed')
        now = time.time()
        conn = db.get_conn()
        try:
            with conn:
                if not eligible:
                    state = 'cancelled'
                elif accepted:
                    state = 'sent'
                else:
                    state = 'failed' if event['attempts'] >= 8 else 'pending'
                retry_after = min(3600, 60 * (2 ** (event['attempts'] - 1)))
                conn.execute('''UPDATE bill_email_events SET status=?, sent_at=?,
                                next_attempt=?, claim_token=NULL, lease_until=NULL
                                WHERE event_id=? AND claim_token=?''',
                             (state, now if accepted else None, now + retry_after,
                              event['event_id'], event['claim_token']))
        finally:
            conn.close()
        stats['attempted'] += 1
        stats['sent' if accepted else 'failed'] += int(eligible)
        if event_id is not None:
            break
    return stats


def run_notifications(today=None, max_seconds=45):
    today = today or local_today()
    if not _run_lock.acquire(blocking=False):
        return dict(queued=0, sent=0, failed=0, attempted=0, busy=True)
    try:
        queued = queue_reminders(today)
        stats = deliver_pending(today=today, max_seconds=max_seconds)
        return dict(queued=queued, busy=False, **stats)
    finally:
        _run_lock.release()


def _run_reminders_once():
    return run_notifications()


def wake():
    _wake.set()


def _loop():
    _wake.wait(15)
    while True:
        _wake.clear()
        try:
            result = run_notifications()
            logger.info('[notifications] completed: %s', result)
        except Exception:
            logger.exception('[notifications] check failed')
        _wake.wait(300)


def start():
    global _started
    if os.environ.get('NOTIFICATIONS_BACKGROUND', '1') != '1':
        return
    with _start_lock:
        if _started:
            return
        _started = True
        threading.Thread(target=_loop, daemon=True, name='bill-notifications').start()
