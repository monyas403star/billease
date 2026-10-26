"""Transactional email outbox for BillEase; dates use Asia/Jerusalem.

Status 'sent' means accepted by the email provider, not verified inbox delivery.
The outbox must live on durable storage to survive restarts/redeployments.
"""
import logging
import json
import re
import os
import threading
import time
import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import db
import mailer
import i18n
import email_templates

logger = logging.getLogger(__name__)
_started = False
_start_lock = threading.Lock()
_wake = threading.Event()
_run_lock = threading.Lock()


def local_today():
    return datetime.now(ZoneInfo('Asia/Jerusalem')).date()


def init_schema():
    i18n.init_schema()
    # Expand the existing CHECK constraint without losing event IDs or retry state.
    create_sql = """
                CREATE TABLE IF NOT EXISTS bill_email_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    bill_id INTEGER NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('paid', 'seven_days', 'overdue', 'deleted')),
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
    """
    conn = db.get_conn()
    try:
        with conn:
            conn.execute('BEGIN IMMEDIATE')
            existing = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='bill_email_events'").fetchone()
            if existing and "'deleted'" not in existing['sql']:
                conn.execute(create_sql.replace('IF NOT EXISTS bill_email_events', '_bill_email_events_v2'))
                conn.execute('INSERT INTO _bill_email_events_v2 SELECT * FROM bill_email_events')
                conn.execute('DROP TABLE bill_email_events')
                conn.execute('ALTER TABLE _bill_email_events_v2 RENAME TO bill_email_events')
            else:
                conn.execute(create_sql)
            columns = {r['name'] for r in conn.execute('PRAGMA table_info(bill_email_events)')}
            if 'language' not in columns:
                conn.execute("ALTER TABLE bill_email_events ADD COLUMN language TEXT NOT NULL DEFAULT 'he'")
            if 'payload_json' not in columns:
                conn.execute("ALTER TABLE bill_email_events ADD COLUMN payload_json TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_bill_email_pending ON bill_email_events(status,next_attempt,lease_until)")
    finally:
        conn.close()


def _insert_event(conn, row, kind, today):
    due_raw = str(row['due_date'] or '')[:10]
    try:
        due = date.fromisoformat(due_raw)
    except ValueError:
        if kind != 'deleted':
            raise
        due = None
    row = dict(row)
    locale = row.get('preferred_language') or 'he'
    snapshot = dict(full_name=row.get('full_name') or '', supplier=row.get('supplier') or '',
                    amount=f"{float(row['amount']):.2f}",
                    due_text=due.strftime('%d/%m/%Y') if due else due_raw,
                    installment_number=row.get('installment_number'), installment_count=row.get('installment_count'))
    subject, body = email_templates.bill_event(kind, locale, snapshot)
    conn.execute('''
        INSERT INTO bill_email_events
            (user_id, bill_id, kind, due_date, recipient, subject, body,
             idempotency_key, created_at, language, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, bill_id, kind, due_date) DO NOTHING
    ''', (row['user_id'], row['bill_id'], kind, due.isoformat() if due else due_raw, row['email'] or '',
          subject, body, str(uuid.uuid4()), time.time(), locale, json.dumps(snapshot,ensure_ascii=False)))
    event = conn.execute('''SELECT event_id FROM bill_email_events
                            WHERE user_id=? AND bill_id=? AND kind=? AND due_date=?''',
                         (row['user_id'], row['bill_id'], kind, due.isoformat() if due else due_raw)).fetchone()
    return event['event_id']


def queue_payment(conn, bill_id, user_id):
    """Use the same transaction as marking paid, so a failed commit sends no email."""
    row = conn.execute('''
        SELECT b.*, u.email, u.full_name, u.preferred_language FROM bills b
        JOIN users u ON u.user_id=b.user_id
        WHERE b.bill_id=? AND b.user_id=? AND b.is_paid=1
    ''', (bill_id, user_id)).fetchone()
    if row is None:
        return None
    conn.execute('''UPDATE bill_email_events SET status='cancelled', claim_token=NULL,
                    lease_until=NULL WHERE bill_id=? AND user_id=?
                    AND kind!='paid' AND status='pending' ''', (bill_id, user_id))
    return _insert_event(conn, row, 'paid', local_today())


def queue_deletion(conn, bill_id, user_id):
    """Capture recipient and bill details before deletion, in its transaction."""
    row = conn.execute("""SELECT b.*,u.email,u.full_name,u.preferred_language FROM bills b
                          JOIN users u ON u.user_id=b.user_id
                          WHERE b.bill_id=? AND b.user_id=?""", (bill_id,user_id)).fetchone()
    if row is None:
        return None
    conn.execute("""UPDATE bill_email_events SET status='cancelled'
                    WHERE bill_id=? AND user_id=? AND kind!='deleted' AND status='pending'""",
                 (bill_id,user_id))
    return _insert_event(conn,row,'deleted',local_today())


def _eligible(conn, event, today):
    if event['kind'] == 'deleted':
        return conn.execute('SELECT 1 FROM users WHERE user_id=?', (event['user_id'],)).fetchone() is not None
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
            rows = conn.execute('''SELECT b.*, u.email, u.full_name, u.preferred_language FROM bills b
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
            sql += " ORDER BY CASE WHEN kind IN ('paid','deleted') THEN 0 ELSE 1 END, event_id LIMIT 25"
            for event in conn.execute(sql, args).fetchall():
                if not _eligible(conn, event, today):
                    conn.execute("UPDATE bill_email_events SET status='cancelled' WHERE event_id=?",
                                 (event['event_id'],))
                    continue
                if not event['recipient'].strip():
                    conn.execute("UPDATE bill_email_events SET status='failed' WHERE event_id=?",
                                 (event['event_id'],))
                    continue
                event = dict(event)
                if event['attempts'] == 0:
                    user = conn.execute('SELECT preferred_language,full_name FROM users WHERE user_id=?', (event['user_id'],)).fetchone()
                    locale = user['preferred_language'] if user else 'he'
                    try:
                        snapshot = json.loads(event.get('payload_json') or 'null')
                    except (ValueError,TypeError):
                        snapshot = None
                    if not isinstance(snapshot,dict):
                        # Compatibility for pending events created by the previous Hebrew-only release.
                        supplier = re.search(r'^ספק: (.*)$', event['body'], re.M)
                        amount = re.search(r'^סכום: ([0-9.]+) ש״ח$', event['body'], re.M)
                        due = re.search(r'^מועד לתשלום: (.*)$', event['body'], re.M)
                        if supplier and amount and due:
                            snapshot = dict(full_name=user['full_name'] if user else '', supplier=supplier[1], amount=amount[1], due_text=due[1])
                    if isinstance(snapshot,dict):
                        subject, body = email_templates.bill_event(event['kind'], locale, snapshot)
                        conn.execute('UPDATE bill_email_events SET subject=?,body=?,language=? WHERE event_id=?',
                                     (subject,body,locale,event['event_id']))
                        event.update(subject=subject,body=body,language=locale)
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
