# BillEase - Flask backend
import os
import hashlib
import random
import string
from datetime import datetime, timedelta, date
from collections import defaultdict

from flask import (
    Flask, request, jsonify, session, render_template,
    send_file, redirect, url_for, send_from_directory
)
from werkzeug.utils import secure_filename

import config
import bootstrap
import db
import ocr
import mailer
import pdfgen
import categorize
import scheduler

# auto-create DB + tables + demo data on first start (idempotent)
bootstrap.init_db()


# build the app, pointing to ../templates and ../static
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = HERE

app = Flask(
    __name__,
    template_folder=os.path.join(ROOT, "templates"),
    static_folder=os.path.join(ROOT, "static"),
)
app.secret_key = config.SECRET_KEY
# keep Hebrew as-is in JSON responses
app.config["JSON_AS_ASCII"] = False
app.json.ensure_ascii = False

# folder for uploaded images
UPLOAD_FULL = os.path.join(HERE, config.UPLOAD_DIR)
os.makedirs(UPLOAD_FULL, exist_ok=True)

# simple in-memory OTP store: user_id -> (code, expires_at)
OTP_STORE = {}


# ------------------ helpers ------------------

def hash_pw(pw):
    # sha256 hash for password storage
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()


def need_login():
    # check if a user is logged in
    return "user_id" in session


def gen_otp():
    # 6 digit one-time code
    return "".join(random.choices(string.digits, k=6))


def current_user():
    if not need_login():
        return None
    row = db.query(
        "SELECT user_id, full_name, email, phone, is_admin FROM users WHERE user_id=%s",
        (session["user_id"],),
        fetch=True, one=True,
    )
    if row:
        row["is_admin"] = bool(row["is_admin"])
    return row


def is_admin():
    u = current_user()
    return bool(u and u.get("is_admin"))


def add_months(d, months):
    # add N months to a date (handles month overflow)
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    # clamp day if next month is shorter
    from calendar import monthrange
    day = min(d.day, monthrange(y, m)[1])
    return d.replace(year=y, month=m, day=day)


# ------------------ page routes ------------------

@app.route("/")
def root():
    if need_login():
        return redirect(url_for("dashboard_page"))
    return render_template("login.html")


@app.route("/register")
def register_page():
    return render_template("register.html")


@app.route("/recover")
def recover_page():
    return render_template("recover.html")


@app.route("/dashboard")
def dashboard_page():
    if not need_login():
        return redirect(url_for("root"))
    return render_template("dashboard.html", user=current_user())


@app.route("/add-bill")
def add_bill_page():
    if not need_login():
        return redirect(url_for("root"))
    return render_template("add_bill.html", user=current_user())


@app.route("/bills")
def bills_page():
    if not need_login():
        return redirect(url_for("root"))
    return render_template("bills.html", user=current_user())


@app.route("/reports")
def reports_page():
    if not need_login():
        return redirect(url_for("root"))
    return render_template("reports.html", user=current_user())


@app.route("/profile")
def profile_page():
    if not need_login():
        return redirect(url_for("root"))
    return render_template("profile.html", user=current_user())


@app.route("/ocr-log")
def ocr_log_page():
    if not need_login():
        return redirect(url_for("root"))
    return render_template("ocr_log.html", user=current_user())


@app.route("/admin")
def admin_page():
    if not need_login():
        return redirect(url_for("root"))
    if not is_admin():
        return redirect(url_for("dashboard_page"))
    return render_template("admin.html", user=current_user())


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("root"))


# expose upload files
@app.route("/uploads/<path:fname>")
def uploaded_file(fname):
    return send_from_directory(UPLOAD_FULL, fname)


# ------------------ auth api ------------------

@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json() or {}
    user_id = (data.get("user_id") or "").strip()
    name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip()
    phone = (data.get("phone") or "").strip()
    pw = data.get("password") or ""

    if not user_id or not name or not email or not pw:
        return jsonify(ok=False, error="חסרים שדות חובה"), 400
    if len(pw) < 4:
        return jsonify(ok=False, error="הסיסמה קצרה מדי"), 400

    # check if id already used
    found = db.query("SELECT user_id FROM users WHERE user_id=%s",
                     (user_id,), fetch=True, one=True)
    if found:
        return jsonify(ok=False, error="מספר הזהות כבר רשום במערכת"), 400

    db.query(
        "INSERT INTO users (user_id, full_name, email, phone, password_hash) "
        "VALUES (%s, %s, %s, %s, %s)",
        (user_id, name, email, phone, hash_pw(pw)),
    )
    mailer.send_email(email, "ברוך הבא ל-BillEase",
                    f"שלום {name}, החשבון שלך ב-BillEase מוכן לשימוש!")

    session.clear()
    session["user_id"] = user_id
    session["full_name"] = name

    return jsonify(ok=True, redirect=url_for("dashboard_page"))

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    user_id = (data.get("user_id") or "").strip()
    pw = data.get("password") or ""

    row = db.query(
        "SELECT user_id, full_name, password_hash FROM users WHERE user_id=%s",
        (user_id,), fetch=True, one=True,
    )
    if not row:
        return jsonify(ok=False, error="המשתמש לא נמצא"), 401
    if row["password_hash"] != hash_pw(pw):
        return jsonify(ok=False, error="סיסמה שגויה"), 401

    session["user_id"] = row["user_id"]
    session["full_name"] = row["full_name"]
    return jsonify(ok=True, name=row["full_name"])


@app.route("/api/recover/request", methods=["POST"])
def api_recover_request():
    data = request.get_json() or {}
    user_id = (data.get("user_id") or "").strip()

    row = db.query(
        "SELECT user_id, email FROM users WHERE user_id=%s",
        (user_id,),
        fetch=True,
        one=True,
    )

    if not row:
        return jsonify(ok=False, error="המשתמש לא נמצא"), 404

    code = gen_otp()
    OTP_STORE[user_id] = (
        code,
        datetime.utcnow() + timedelta(minutes=10),
    )

    sent = mailer.send_email(
        row["email"],
        "איפוס סיסמה ל-BillEase",
        f"קוד החד-פעמי שלך: {code}\nתוקפו 10 דקות.",
    )

    if not sent:
        OTP_STORE.pop(user_id, None)
        return jsonify(
            ok=False,
            error="שליחת הקוד נכשלה. נסו שוב מאוחר יותר.",
        ), 502

    return jsonify(
        ok=True,
        msg="הקוד הועבר לשליחה. בדקו גם בתיקיית הספאם.",
    )

@app.route("/api/recover/reset", methods=["POST"])
def api_recover_reset():
    # step 2 of password recovery - verify OTP and set new password
    data = request.get_json() or {}
    user_id = (data.get("user_id") or "").strip()
    otp_code = (data.get("otp") or "").strip()
    new_pw = data.get("new_password") or ""

    if not user_id or not otp_code or not new_pw:
        return jsonify(ok=False, error="חסרים שדות חובה"), 400
    if len(new_pw) < 4:
        return jsonify(ok=False, error="הסיסמה קצרה מדי"), 400

    saved = OTP_STORE.get(user_id)
    if not saved:
        return jsonify(ok=False, error="לא הוגשה בקשת איפוס"), 400
    code, expires = saved
    if datetime.utcnow() > expires:
        OTP_STORE.pop(user_id, None)
        return jsonify(ok=False, error="קוד החד-פעמי פג תוקף"), 400
    if code != otp_code:
        return jsonify(ok=False, error="קוד החד-פעמי שגוי"), 400

    db.query("UPDATE users SET password_hash=%s WHERE user_id=%s",
             (hash_pw(new_pw), user_id))
    OTP_STORE.pop(user_id, None)
    return jsonify(ok=True)


# ------------------ profile api ------------------

@app.route("/api/profile", methods=["GET"])
def api_profile():
    if not need_login():
        return jsonify(ok=False, error="לא מחובר"), 401
    return jsonify(ok=True, user=current_user())


@app.route("/api/profile", methods=["PUT"])
def api_profile_update():
    if not need_login():
        return jsonify(ok=False, error="לא מחובר"), 401
    data = request.get_json() or {}
    name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip()
    phone = (data.get("phone") or "").strip()
    new_pw = data.get("password") or ""

    if not name or not email:
        return jsonify(ok=False, error="שם ואימייל נדרשים"), 400

    if new_pw:
        if len(new_pw) < 4:
            return jsonify(ok=False, error="הסיسמה קצרה מדי"), 400
        db.query(
            "UPDATE users SET full_name=%s, email=%s, phone=%s, password_hash=%s "
            "WHERE user_id=%s",
            (name, email, phone, hash_pw(new_pw), session["user_id"]),
        )
    else:
        db.query(
            "UPDATE users SET full_name=%s, email=%s, phone=%s WHERE user_id=%s",
            (name, email, phone, session["user_id"]),
        )
    session["full_name"] = name
    return jsonify(ok=True)


# ------------------ bills api ------------------

@app.route("/api/bills", methods=["GET"])
def api_bills_list():
    if not need_login():
        return jsonify(ok=False, error="לא מחובר"), 401
    rows = db.query(
        "SELECT bill_id, supplier, amount, category, due_date, is_paid, "
        "is_recurring, recurrence, image_path, source "
        "FROM bills WHERE user_id=%s ORDER BY due_date ASC",
        (session["user_id"],), fetch=True,
    )
    for r in rows:
        r["due_date"] = str(r["due_date"])
        r["amount"] = float(r["amount"])
        r["is_recurring"] = bool(r["is_recurring"])
    return jsonify(ok=True, bills=rows)


@app.route("/api/bills", methods=["POST"])
def api_bill_add():
    if not need_login():
        return jsonify(ok=False, error="לא מחובר"), 401
    data = request.get_json() or {}
    supplier = (data.get("supplier") or "").strip()
    amount = data.get("amount")
    category = (data.get("category") or "").strip()
    due_date = (data.get("due_date") or "").strip()
    is_recurring = 1 if data.get("is_recurring") else 0
    recurrence = (data.get("recurrence") or "monthly").strip() if is_recurring else None
    image_path = data.get("image_path") or None
    source = "ocr" if image_path else "manual"

    if not supplier or not amount or not due_date:
        return jsonify(ok=False, error="חסרים שדות חובה"), 400
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return jsonify(ok=False, error="סכום לא תקין"), 400

    # if user didn't pick a category, try to guess from supplier
    if not category or category == "אחר":
        guessed = categorize.guess_category(supplier)
        if guessed:
            category = guessed
    if not category:
        category = "אחר"

    bill_id = db.query(
        "INSERT INTO bills (user_id, supplier, amount, category, due_date, "
        "is_paid, is_recurring, recurrence, image_path, source) "
        "VALUES (%s, %s, %s, %s, %s, 0, %s, %s, %s, %s)",
        (session["user_id"], supplier, amount, category, due_date,
         is_recurring, recurrence, image_path, source),
    )
    return jsonify(ok=True, bill_id=bill_id, category=category)


@app.route("/api/bills/<int:bill_id>/pay", methods=["POST"])
def api_bill_pay(bill_id):
    if not need_login():
        return jsonify(ok=False, error="לא מחובר"), 401

    conn = db.get_conn()

    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")

            row = conn.execute(
                "SELECT * FROM bills WHERE bill_id=? AND user_id=?",
                (bill_id, session["user_id"]),
            ).fetchone()

            if row is None:
                return jsonify(
                    ok=False,
                    error="החשבון לא נמצא",
                ), 404

            if row["is_paid"]:
                return jsonify(
                    ok=True,
                    already_paid=True,
                    next_bill_id=None,
                )

            next_bill_id = None

            if row["is_recurring"]:
                months = 12 if row["recurrence"] == "yearly" else 1

                try:
                    due = date.fromisoformat(str(row["due_date"])[:10])
                    next_due = add_months(due, months)
                except (ValueError, OverflowError):
                    return jsonify(
                        ok=False,
                        error="תאריך החשבון אינו תקין",
                    ), 400

                cursor = conn.execute(
                    """
                    INSERT INTO bills (
                        user_id, supplier, amount, category, due_date,
                        is_paid, is_recurring, recurrence, source
                    )
                    VALUES (?, ?, ?, ?, ?, 0, 1, ?, ?)
                    """,
                    (
                        row["user_id"],
                        row["supplier"],
                        row["amount"],
                        row["category"],
                        next_due.isoformat(),
                        row["recurrence"],
                        row["source"],
                    ),
                )
                next_bill_id = cursor.lastrowid

            conn.execute(
                """
                UPDATE bills
                SET is_paid=1
                WHERE bill_id=? AND user_id=?
                """,
                (bill_id, session["user_id"]),
            )

        return jsonify(ok=True, next_bill_id=next_bill_id)

    finally:
        conn.close()

@app.route("/api/bills/<int:bill_id>", methods=["DELETE"])
def api_bill_delete(bill_id):
    if not need_login():
        return jsonify(ok=False, error="לא מחובר"), 401
    db.query(
        "DELETE FROM bills WHERE bill_id=%s AND user_id=%s",
        (bill_id, session["user_id"]),
    )
    return jsonify(ok=True)


@app.route("/api/bills/by-month", methods=["GET"])
def api_bills_by_month():
    # drill-down: list bills for a specific year+month
    if not need_login():
        return jsonify(ok=False, error="לא מחובר"), 401
    try:
        year = int(request.args.get("year"))
        month = int(request.args.get("month"))
    except (TypeError, ValueError):
        return jsonify(ok=False, error="שנה או חודש לא תקינים"), 400
    rows = db.query(
        "SELECT bill_id, supplier, amount, category, due_date, is_paid "
        "FROM bills WHERE user_id=%s ORDER BY due_date ASC",
        (session["user_id"],), fetch=True,
    )
    filtered = []
    for r in rows:
        d_val = r["due_date"]
        if isinstance(d_val, str):
            d_val = datetime.strptime(d_val[:10], "%Y-%m-%d").date()
        if d_val.year == year and d_val.month == month:
            r["due_date"] = str(r["due_date"])
            r["amount"] = float(r["amount"])
            filtered.append(r)
    return jsonify(ok=True, bills=filtered)


@app.route("/api/suggest-category", methods=["GET"])
def api_suggest_category():
    # let the frontend ask for a category guess as the user types the supplier
    if not need_login():
        return jsonify(ok=False, error="לא מחובר"), 401
    supplier = request.args.get("supplier", "")
    cat = categorize.guess_category(supplier)
    return jsonify(ok=True, category=cat)


# ------------------ OCR + upload ------------------

@app.route("/api/bills/scan", methods=["POST"])
def api_bill_scan():
    if not need_login():
        return jsonify(ok=False, error="לא מחובר"), 401
    if "image" not in request.files:
        return jsonify(ok=False, error="לא צורפה תמונה"), 400

    f = request.files["image"]
    if not f.filename:
        return jsonify(ok=False, error="שם קובץ ריק"), 400

    safe = secure_filename(f.filename)
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    save_name = f"{session['user_id']}{stamp}{safe}"
    full_path = os.path.join(UPLOAD_FULL, save_name)
    f.save(full_path)

    parsed = ocr.scan_bill(full_path)
    parsed_ok = bool(parsed["amount"] or parsed["due_date"] or parsed["supplier"])
    # write a row to the ocr log so admins/audit can review
    db.query(
        "INSERT INTO ocr_log (user_id, image_path, parsed_ok, note) "
        "VALUES (%s, %s, %s, %s)",
        (session["user_id"], save_name, 1 if parsed_ok else 0,
         "ok" if ocr.OCR_OK else "tesseract not installed"),
    )
    # also try to guess a category from the supplier we read
    guessed = categorize.guess_category(parsed["supplier"]) if parsed["supplier"] else None
    return jsonify(
        ok=True,
        image=save_name,
        amount=parsed["amount"],
        due_date=parsed["due_date"],
        supplier=parsed["supplier"],
        category=guessed,
        ocr_available=ocr.OCR_OK,
        ocr_error=parsed.get("error"),
    )


# ------------------ OCR audit ------------------

@app.route("/api/ocr-log", methods=["GET"])
def api_ocr_log():
    if not need_login():
        return jsonify(ok=False, error="לא מחובר"), 401
    rows = db.query(
        "SELECT log_id, image_path, parsed_ok, note, created_at "
        "FROM ocr_log WHERE user_id=%s ORDER BY created_at DESC LIMIT 100",
        (session["user_id"],), fetch=True,
    )
    for r in rows:
        r["created_at"] = str(r["created_at"])
        r["parsed_ok"] = bool(r["parsed_ok"])
    # also pull bills that have an image attached
    bills = db.query(
        "SELECT bill_id, supplier, amount, category, due_date, image_path, source "
        "FROM bills WHERE user_id=%s AND (source='ocr' OR image_path IS NOT NULL) "
        "ORDER BY created_at DESC",
        (session["user_id"],), fetch=True,
    )
    for b in bills:
        b["due_date"] = str(b["due_date"])
        b["amount"] = float(b["amount"])
    return jsonify(ok=True, log=rows, bills=bills)


# ------------------ categories ------------------

@app.route("/api/categories", methods=["GET"])
def api_categories():
    rows = db.query(
        "SELECT category_name FROM categories ORDER BY category_name",
        fetch=True,
    )
    return jsonify(ok=True, categories=[r["category_name"] for r in rows])


# ------------------ reports ------------------

@app.route("/api/reports/summary", methods=["GET"])
def api_reports_summary():
    if not need_login():
        return jsonify(ok=False, error="לא מחובר"), 401
    year = request.args.get("year", default=date.today().year, type=int)

    rows = db.query(
        "SELECT category, amount, due_date FROM bills WHERE user_id=%s",
        (session["user_id"],), fetch=True,
    )

    by_month = defaultdict(float)
    by_cat = defaultdict(float)
    for r in rows:
        d_val = r["due_date"]
        if isinstance(d_val, str):
            d_val = datetime.strptime(d_val[:10], "%Y-%m-%d").date()
        if d_val.year == year:
            m = d_val.month
            by_month[m] += float(r["amount"])
            by_cat[r["category"] or "Other"] += float(r["amount"])

    months = [round(by_month.get(i, 0.0), 2) for i in range(1, 13)]
    cats = {k: round(v, 2) for k, v in by_cat.items()}
    return jsonify(ok=True, year=year, months=months, categories=cats)


@app.route("/api/reports/compare", methods=["GET"])
def api_reports_compare():
    # year-over-year comparison per month
    if not need_login():
        return jsonify(ok=False, error="לא מחובר"), 401
    year1 = request.args.get("year1", default=date.today().year, type=int)
    year2 = request.args.get("year2", default=date.today().year - 1, type=int)

    def monthly(y):
        rows = db.query(
            "SELECT due_date, amount FROM bills WHERE user_id=%s",
            (session["user_id"],), fetch=True,
        )
        out = [0.0] * 12
        for r in rows:
            d_val = r["due_date"]
            if isinstance(d_val, str):
                d_val = datetime.strptime(d_val[:10], "%Y-%m-%d").date()
            if d_val.year == y:
                out[d_val.month - 1] += float(r["amount"])
        return [round(x, 2) for x in out]

    return jsonify(ok=True, year1=year1, year2=year2,
                   data1=monthly(year1), data2=monthly(year2))


@app.route("/api/reports/csv", methods=["GET"])
def api_reports_csv():
    # CSV export of all bills
    if not need_login():
        return redirect(url_for("root"))
    import csv
    from io import StringIO, BytesIO
    rows = db.query(
        "SELECT supplier, amount, category, due_date, is_paid "
        "FROM bills WHERE user_id=%s ORDER BY due_date ASC",
        (session["user_id"],), fetch=True,
    )
    out = StringIO()
    out.write("\ufeff")  # BOM so Excel reads Hebrew right
    w = csv.writer(out)
    w.writerow(["ספק", "סכום", "קטגוריה", "תאריך פירעון", "שולם"])
    for r in rows:
        w.writerow([
            r["supplier"], f"{float(r['amount']):.2f}",
            r["category"] or "", str(r["due_date"]),
            "כן" if r["is_paid"] else "לא",
        ])
    data = out.getvalue().encode("utf-8")
    return send_file(
        BytesIO(data),
        as_attachment=True,
        download_name="billease_bills.csv",
        mimetype="text/csv; charset=utf-8",
    )


@app.route("/api/budgets", methods=["GET"])
def api_budgets_list():
    if not need_login():
        return jsonify(ok=False, error="לא מחובר"), 401
    rows = db.query(
        "SELECT category, monthly_limit FROM budgets WHERE user_id=%s",
        (session["user_id"],), fetch=True,
    )
    for r in rows:
        r["monthly_limit"] = float(r["monthly_limit"])
    return jsonify(ok=True, budgets=rows)


@app.route("/api/budgets", methods=["POST"])
def api_budgets_save():
    # upsert a single category budget
    if not need_login():
        return jsonify(ok=False, error="לא מחובר"), 401
    data = request.get_json() or {}
    category = (data.get("category") or "").strip()
    try:
        limit = float(data.get("monthly_limit"))
    except (TypeError, ValueError):
        return jsonify(ok=False, error="סכום לא תקין"), 400
    if not category:
        return jsonify(ok=False, error="חסרה קטגוריה"), 400
    db.query(
        "INSERT INTO budgets (user_id, category, monthly_limit) "
        "VALUES (%s, %s, %s) "
        "ON DUPLICATE KEY UPDATE monthly_limit=VALUES(monthly_limit)",
        (session["user_id"], category, limit),
    )
    return jsonify(ok=True)


@app.route("/api/budgets/<category>", methods=["DELETE"])
def api_budgets_delete(category):
    if not need_login():
        return jsonify(ok=False, error="לא מחובר"), 401
    db.query(
        "DELETE FROM budgets WHERE user_id=%s AND category=%s",
        (session["user_id"], category),
    )
    return jsonify(ok=True)


@app.route("/api/reports/pdf", methods=["GET"])
def api_reports_pdf():
    if not need_login():
        return redirect(url_for("root"))
    user = current_user()
    rows = db.query(
        "SELECT supplier, amount, category, due_date, is_paid "
        "FROM bills WHERE user_id=%s ORDER BY due_date ASC",
        (session["user_id"],), fetch=True,
    )
    totals = defaultdict(float)
    for r in rows:
        totals[r["category"] or "Other"] += float(r["amount"])
    pdf_bytes = pdfgen.build_report_pdf(user["full_name"], rows, dict(totals))
    return send_file(
        pdf_bytes,
        as_attachment=True,
        download_name="billease_report.pdf",
        mimetype="application/pdf",
    )


# ------------------ reminders (manual trigger) ------------------

@app.route("/api/reminders/run", methods=["POST"])
def api_reminders_run():
    # checks unpaid bills due in N days and emails reminders
    target = date.today() + timedelta(days=config.REMINDER_DAYS)
    rows = db.query(
        "SELECT b.bill_id, b.supplier, b.amount, b.due_date, u.email, u.full_name "
        "FROM bills b JOIN users u ON b.user_id = u.user_id "
        "WHERE b.is_paid=0 AND b.due_date=%s",
        (target.isoformat(),), fetch=True,
    )
    sent = 0
    for r in rows:
        body = (f"שלום {r['full_name']},\n\n"
                f"תזכורת: החשבון מ-{r['supplier']} "
                f"בסך {r['amount']} ש\"ח לתשלום עד {r['due_date']}.")
        if mailer.send_email(r["email"], "תזכורת תשלום מ-BillEase", body):
            sent += 1
    return jsonify(ok=True, sent=sent, total=len(rows))


# ------------------ admin (אפיון 11.2) ------------------

def _need_admin():
    if not need_login():
        return jsonify(ok=False, error="לא מחובר"), 401
    if not is_admin():
        return jsonify(ok=False, error="אין הרשאת מנהل"), 403
    return None


@app.route("/api/admin/stats", methods=["GET"])
def api_admin_stats():
    err = _need_admin()
    if err:
        return err
    users_count = db.query("SELECT COUNT(*) AS c FROM users", fetch=True, one=True)["c"]
    bills_count = db.query("SELECT COUNT(*) AS c FROM bills", fetch=True, one=True)["c"]
    paid_count = db.query("SELECT COUNT(*) AS c FROM bills WHERE is_paid=1",
                          fetch=True, one=True)["c"]
    ocr_count = db.query("SELECT COUNT(*) AS c FROM ocr_log", fetch=True, one=True)["c"]
    ocr_fails = db.query("SELECT COUNT(*) AS c FROM ocr_log WHERE parsed_ok=0",
                         fetch=True, one=True)["c"]
    
    today_str = date.today().isoformat()
    all_users = db.query("SELECT created_at FROM users", fetch=True) or []
    today_signup = sum(1 for u in all_users if str(u.get("created_at", ""))[:10] == today_str)

    all_bills = db.query("SELECT created_at FROM bills", fetch=True) or []
    today_bills = sum(1 for b in all_bills if str(b.get("created_at", ""))[:10] == today_str)

    # by category total
    by_cat = db.query(
        "SELECT category, COUNT(*) AS cnt, SUM(amount) AS total "
        "FROM bills GROUP BY category ORDER BY total DESC",
        fetch=True,
    )
    for r in by_cat:
        r["total"] = float(r["total"] or 0)
    return jsonify(
        ok=True,
        users=users_count,
        bills=bills_count,
        paid=paid_count,
        ocr_scans=ocr_count,
        ocr_fails=ocr_fails,
        signups_today=today_signup,
        bills_today=today_bills,
        by_category=by_cat,
    )


@app.route("/api/admin/users", methods=["GET"])
def api_admin_users():
    err = _need_admin()
    if err:
        return err
    rows = db.query(
        "SELECT u.user_id, u.full_name, u.email, u.phone, u.is_admin, u.created_at, "
        "(SELECT COUNT(*) FROM bills b WHERE b.user_id=u.user_id) AS bill_count "
        "FROM users u ORDER BY u.created_at DESC",
        fetch=True,
    )
    for r in rows:
        r["created_at"] = str(r["created_at"])
        r["is_admin"] = bool(r["is_admin"])
    return jsonify(ok=True, users=rows)


@app.route("/api/admin/ocr-log", methods=["GET"])
def api_admin_ocr_log():
    err = _need_admin()
    if err:
        return err
    rows = db.query(
        "SELECT log_id, user_id, image_path, parsed_ok, note, created_at "
        "FROM ocr_log ORDER BY created_at DESC LIMIT 200",
        fetch=True,
    )
    for r in rows:
        r["created_at"] = str(r["created_at"])
        r["parsed_ok"] = bool(r["parsed_ok"])
    return jsonify(ok=True, log=rows)

@app.errorhandler(500)
def internal_error(e):
    return f"<h3>حدث خطأ داخلي:</h3><pre>{str(e)}</pre>", 500

# start the background reminder thread (won't double-start)
scheduler.start()


if __name__ == "__main__":
    # run dev server
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
