# tiny background scheduler - runs the reminder check once a day
import threading
import time
import traceback
from datetime import date, timedelta

import db
import mailer
import config


_started = False  # so the thread doesn't start twice in debug-reload mode


def _run_reminders_once():
    target = (date.today() + timedelta(days=config.REMINDER_DAYS)).isoformat()
    rows = db.query(
        "SELECT b.bill_id, b.supplier, b.amount, b.due_date, u.email, u.full_name "
        "FROM bills b JOIN users u ON b.user_id = u.user_id "
        "WHERE b.is_paid=0 AND b.due_date=%s",
        (target,), fetch=True,
    )
    sent = 0
    for r in rows:
        body = (f"שלום {r['full_name']},\n\n"
                f"תזכורת: החשבון מ-{r['supplier']} "
                f"בסך {r['amount']} ש\"ח לתשלום עד {r['due_date']}.")
        if mailer.send_email(r["email"], "תזכורת תשלום מ-BillEase", body):
            sent += 1
    print(f"[scheduler] reminders run: {sent}/{len(rows)} sent")


def _loop():
    # run every 24h. first run after a short delay so the app finishes booting.
    time.sleep(15)
    while True:
        try:
            _run_reminders_once()
        except Exception:
            traceback.print_exc()
        time.sleep(24 * 60 * 60)


def start():
    global _started
    if _started:
        return
    _started = True
    t = threading.Thread(target=_loop, daemon=True, name="bill-reminder")
    t.start()
    print("[scheduler] background reminder thread started")
