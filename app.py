# BillEase - Flask backend
import os
import hmac
import secrets
import re
import sqlite3
from urllib.parse import urlsplit
from datetime import datetime, date
from collections import defaultdict

from flask import (
    Flask, request, jsonify, session, render_template,
    send_file, redirect, url_for, send_from_directory
)
from werkzeug.exceptions import BadRequest
from PIL import Image, ImageOps, UnidentifiedImageError
import billease_security as security

import config
import bootstrap
import db
import ocr
import mailer
import pdfgen
import categorize
import i18n
import email_templates
import payment_plans
import scheduler

# auto-create DB + tables + demo data on first start (idempotent)
bootstrap.DB_FILE = db.database_path()
bootstrap.init_db()
i18n.init_schema()
payment_plans.init_schema()
scheduler.init_schema()
security.init_schema()


# build the app, pointing to ../templates and ../static
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = HERE

app = Flask(
    __name__,
    template_folder=os.path.join(ROOT, "templates"),
    static_folder=os.path.join(ROOT, "static"),
)
app.secret_key = security.session_secret()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("RENDER", "").lower() == "true"
        or os.environ.get("SESSION_COOKIE_SECURE") == "1",
    MAX_CONTENT_LENGTH=12 * 1024 * 1024,
)
i18n.setup(app)

# keep Hebrew as-is in JSON responses
app.config["JSON_AS_ASCII"] = False
app.json.ensure_ascii = False

# folder for uploaded images
UPLOAD_FULL = os.environ.get("BILLEASE_UPLOAD_DIR") or os.path.join(HERE, config.UPLOAD_DIR)
os.makedirs(UPLOAD_FULL, exist_ok=True)

@app.before_request
def check_write_origin():
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("Origin")
        if origin:
            parsed = urlsplit(origin)
            if parsed.netloc != request.host or parsed.scheme not in ("http", "https"):
                return jsonify(ok=False, error="הבקשה אינה מאושרת"), 403
            if app.config["SESSION_COOKIE_SECURE"] and parsed.scheme != "https":
                return jsonify(ok=False, error="נדרש חיבור מאובטח"), 403


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "same-origin"
    if request.path.startswith(("/api/", "/uploads/")):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.errorhandler(400)
def invalid_request(error):
    message = getattr(error, "description", "")
    if not any("א" <= c <= "ת" for c in message):
        message = "הבקשה אינה תקינה"
    return jsonify(ok=False, error=message), 400


@app.errorhandler(413)
def upload_too_large(error):
    return jsonify(ok=False, error="גודל הבקשה המרבי הוא 12 MB"), 413


# ------------------ helpers ------------------

def hash_pw(pw):
    return security.hash_password(pw)


def need_login():
    user_id = session.get("user_id")
    if not isinstance(user_id, str) or not user_id:
        return False
    row = db.query("SELECT user_id FROM users WHERE user_id=?", (user_id,), fetch=True, one=True)
    if not row or session.get("auth_version") != security.version(user_id):
        session.clear()
        return False
    return True


def gen_otp():
    return f"{secrets.randbelow(1000000):06d}"


def image_owned(fname):
    if not isinstance(fname, str) or not fname or fname != os.path.basename(fname) or "\\" in fname:
        return False
    row = db.query("SELECT 1 AS found FROM bills WHERE user_id=? AND image_path=? "
                   "UNION ALL SELECT 1 AS found FROM ocr_log WHERE user_id=? AND image_path=? LIMIT 1",
                   (session["user_id"], fname, session["user_id"], fname), fetch=True, one=True)
    return bool(row)


def current_user():
    if not need_login():
        return None
    row = db.query(
        "SELECT user_id, full_name, email, phone, is_admin, preferred_language FROM users WHERE user_id=%s",
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
    if not need_login():
        return jsonify(ok=False, error="לא מחובר"), 401
    if os.path.splitext(fname)[1].lower() not in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}:
        return jsonify(ok=False, error="הקובץ לא נמצא"), 404
    if not image_owned(fname) and not is_admin():
        return jsonify(ok=False, error="הקובץ לא נמצא"), 404
    return send_from_directory(UPLOAD_FULL, fname)


# ------------------ auth api ------------------

@app.route("/api/register", methods=["POST"])
def api_register():
    data = security.json_object(request)
    preferred_language = i18n.parse_language(data.get("preferred_language", i18n.language()))
    i18n.use_language(preferred_language)
    user_id = security.text(data, "user_id", 64, required=True)
    name = security.text(data, "full_name", 100, required=True)
    email = security.email(security.text(data, "email", 254, required=True))
    phone = security.text(data, "phone", 30)
    pw = security.password(data, "password", new=True)
    if not security.rate_allowed("register", request.remote_addr or "unknown", 20, 3600):
        return jsonify(ok=False, error="יותר מדי ניסיונות. נסו שוב מאוחר יותר"), 429
    try:
        db.query("INSERT INTO users (user_id,full_name,email,phone,password_hash,preferred_language) VALUES (?,?,?,?,?,?)",
                 (user_id, name, email, phone, hash_pw(pw), preferred_language))
    except sqlite3.IntegrityError:
        return jsonify(ok=False, error="מספר הזהות כבר רשום במערכת"), 400
    try:
        mailer.send_email(email, *email_templates.welcome(preferred_language, name))
    except Exception:
        app.logger.warning("Welcome email failed; account was created")
    session.clear()
    session.update(user_id=user_id, full_name=name, auth_version=security.version(user_id))
    i18n.use_language(preferred_language)
    return jsonify(ok=True, language=preferred_language, redirect=url_for("dashboard_page"))


@app.route("/api/login", methods=["POST"])
def api_login():
    data = security.json_object(request)
    selected_language = i18n.parse_language(data["preferred_language"]) if "preferred_language" in data else None
    if selected_language:
        i18n.use_language(selected_language)
    user_id = security.text(data, "user_id", 64, required=True)
    pw = security.password(data, "password")
    if not security.rate_allowed("login", user_id, 20):
        return jsonify(ok=False, error="יותר מדי ניסיונות. נסו שוב בעוד 15 דקות"), 429
    row = db.query("SELECT user_id,full_name,password_hash,preferred_language FROM users WHERE user_id=?",
                   (user_id,), fetch=True, one=True)
    if not row or not security.password_matches(row["password_hash"], pw):
        return jsonify(ok=False, error="פרטי ההתחברות אינם נכונים"), 401
    if security.legacy_hash(row["password_hash"]):
        db.query("UPDATE users SET password_hash=? WHERE user_id=? AND password_hash=?",
                 (hash_pw(pw), user_id, row["password_hash"]))
    session.clear()
    session.update(user_id=user_id, full_name=row["full_name"], auth_version=security.version(user_id))
    scheduler.wake()
    locale = selected_language or row["preferred_language"]
    if selected_language:
        db.query("UPDATE users SET preferred_language=? WHERE user_id=?", (locale, user_id))
    i18n.use_language(locale)
    return jsonify(ok=True, name=row["full_name"], language=locale)


@app.route("/api/recover/request", methods=["POST"])
def api_recover_request():
    data = security.json_object(request)
    user_id = security.text(data, "user_id", 64, required=True)
    if not security.rate_allowed("recover", user_id, 3):
        return jsonify(ok=False, error="יותר מדי בקשות לקוד. נסו שוב בעוד 15 דקות"), 429
    generic = "אם החשבון קיים, הקוד הועבר לשליחה. בדקו גם בתיקיית הספאם."
    row = db.query("SELECT user_id,email,preferred_language FROM users WHERE user_id=?", (user_id,), fetch=True, one=True)
    if not row:
        return jsonify(ok=True, msg=generic)
    code = gen_otp()
    digest = security.save_reset(user_id, code, app.secret_key)
    try:
        sent = mailer.send_email(row["email"], *email_templates.recovery(row["preferred_language"], code))
    except Exception:
        sent = False
    if not sent:
        db.query("DELETE FROM password_reset_codes WHERE user_id=? AND code_hash=?", (user_id, digest))
        return jsonify(ok=False, error="שליחת הקוד נכשלה. נסו שוב מאוחר יותר"), 502
    return jsonify(ok=True, msg=generic)


@app.route("/api/recover/reset", methods=["POST"])
def api_recover_reset():
    data = security.json_object(request)
    user_id = security.text(data, "user_id", 64, required=True)
    code = security.text(data, "otp", 6, required=True)
    new_pw = security.password(data, "new_password", new=True)
    if not re.fullmatch(r"[0-9]{6}", code):
        return jsonify(ok=False, error="נדרש קוד בן שש ספרות"), 400
    if not security.rate_allowed("reset", user_id, 10):
        return jsonify(ok=False, error="יותר מדי ניסיונות. נסו שוב בעוד 15 דקות"), 429
    if not security.apply_reset(user_id, code, hash_pw(new_pw), app.secret_key):
        return jsonify(ok=False, error="הקוד שגוי, פג תוקף או נחסם. בקשו קוד חדש"), 400
    session.clear()
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
    data = security.json_object(request)
    name = security.text(data, "full_name", 100, required=True)
    email = security.email(security.text(data, "email", 254, required=True))
    phone = security.text(data, "phone", 30)
    new_pw = security.password(data, "password", new=True, optional=True)
    user_id = session["user_id"]
    previous = current_user()
    preferred_language = i18n.parse_language(data.get("preferred_language", previous["preferred_language"]))
    conn = db.get_conn()
    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            if new_pw:
                conn.execute("UPDATE users SET full_name=?,email=?,phone=?,password_hash=? WHERE user_id=?",
                             (name, email, phone, hash_pw(new_pw), user_id))
            else:
                conn.execute("UPDATE users SET full_name=?,email=?,phone=? WHERE user_id=?", (name,email,phone,user_id))
            conn.execute("UPDATE users SET preferred_language=? WHERE user_id=?", (preferred_language, user_id))
            # Updating recovery email or password invalidates other sessions/codes.
            if new_pw or previous["email"] != email:
                security.bump_version(conn, user_id)
                conn.execute("DELETE FROM password_reset_codes WHERE user_id=?", (user_id,))
    finally:
        conn.close()
    session["auth_version"] = security.version(user_id)
    session["full_name"] = name
    i18n.use_language(preferred_language)
    return jsonify(ok=True, language=preferred_language)


# ------------------ bills api ------------------

@app.route("/api/bills", methods=["GET"])
def api_bills_list():
    if not need_login():
        return jsonify(ok=False, error="לא מחובר"), 401
    rows = db.query(
        "SELECT bill_id, supplier, amount, category, due_date, is_paid, "
        "is_recurring, recurrence, image_path, source, payment_plan_id, installment_number, installment_count "
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
    data = security.json_object(request)
    supplier = security.text(data, "supplier", 150, required=True)
    payment_mode = data.get("payment_mode", "single")
    if payment_mode not in ("single", "recurring", "installments"):
        raise BadRequest("סוג התשלום אינו תקין")
    amount = security.money(data.get("amount")) if payment_mode != "installments" else None
    category = security.text(data, "category", 80)
    due_date = security.due_date(security.text(data, "due_date", 10, required=True)) if payment_mode != "installments" else None
    recurring = data.get("is_recurring", payment_mode == "recurring")
    if not isinstance(recurring, (bool, int)) or recurring not in (False, True, 0, 1):
        raise BadRequest("ערך החזרתיות אינו תקין")
    is_recurring = int(bool(recurring))
    recurrence = (security.text(data, "recurrence", 10) or "monthly") if is_recurring else None
    if recurrence is not None and recurrence not in ("monthly", "yearly"):
        raise BadRequest("תקופת החזרתיות אינה תקינה")
    image_path = security.text(data, "image_path", 255) or None
    if image_path and not image_owned(image_path):
        raise BadRequest("התמונה אינה שייכת לחשבון שלך")
    source = "ocr" if image_path else "manual"

    # if user didn't pick a category, try to guess from supplier
    if not category or category == "אחר":
        guessed = categorize.guess_category(supplier)
        if guessed:
            category = guessed
    if not category:
        category = "אחר"

    if payment_mode == "installments":
        return jsonify(**payment_plans.create(session["user_id"], supplier, category, image_path, source, data))

    bill_id = db.query(
        "INSERT INTO bills (user_id, supplier, amount, category, due_date, "
        "is_paid, is_recurring, recurrence, image_path, source, recurrence_day) "
        "VALUES (%s, %s, %s, %s, %s, 0, %s, %s, %s, %s, %s)",
        (session["user_id"], supplier, amount, category, due_date,
         is_recurring, recurrence, image_path, source, date.fromisoformat(due_date).day if is_recurring else None),
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

            if row["is_recurring"] and not row["payment_plan_id"]:
                months = 12 if row["recurrence"] == "yearly" else 1

                try:
                    due = date.fromisoformat(str(row["due_date"])[:10])
                    next_due = add_months(due, months)
                    from calendar import monthrange
                    anchor_day = row["recurrence_day"] or due.day
                    next_due = next_due.replace(day=min(anchor_day, monthrange(next_due.year, next_due.month)[1]))
                except (ValueError, OverflowError):
                    return jsonify(
                        ok=False,
                        error="תאריך החשבון אינו תקין",
                    ), 400

                cursor = conn.execute(
                    """
                    INSERT INTO bills (
                        user_id, supplier, amount, category, due_date,
                        is_paid, is_recurring, recurrence, source, recurrence_day
                    )
                    VALUES (?, ?, ?, ?, ?, 0, 1, ?, ?, ?)
                    """,
                    (
                        row["user_id"],
                        row["supplier"],
                        row["amount"],
                        row["category"],
                        next_due.isoformat(),
                        row["recurrence"],
                        row["source"],
                        anchor_day,
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

            event_id = scheduler.queue_payment(conn, bill_id, session["user_id"])

        # Payment is committed before contacting the email provider.
        email_accepted = False
        try:
            if event_id is not None:
                result = scheduler.deliver_pending(event_id=event_id, max_seconds=20)
                email_accepted = result["sent"] > 0
        except Exception:
            app.logger.exception("[notifications] payment saved; email remains queued")
        scheduler.wake()
        return jsonify(ok=True, next_bill_id=next_bill_id,
                       email_accepted=email_accepted)

    finally:
        conn.close()

@app.route("/api/bills/<int:bill_id>", methods=["DELETE"])
def api_bill_delete(bill_id):
    if not need_login():
        return jsonify(ok=False, error="לא מחובר"), 401
    conn = db.get_conn()
    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            owned = conn.execute("SELECT bill_id FROM bills WHERE bill_id=? AND user_id=?",
                                 (bill_id, session["user_id"])).fetchone()
            if owned is None:
                return jsonify(ok=False, error="החשבון לא נמצא"), 404
            event_id = scheduler.queue_deletion(conn, bill_id, session["user_id"])
            conn.execute("DELETE FROM bills WHERE bill_id=? AND user_id=?", (bill_id, session["user_id"]))
        email_accepted = False
        try:
            if event_id is not None:
                result = scheduler.deliver_pending(event_id=event_id,max_seconds=20)
                email_accepted = result["sent"] > 0
        except Exception:
            app.logger.exception("[notifications] bill deleted; email remains queued")
        scheduler.wake()
        return jsonify(ok=True,email_accepted=email_accepted)
    finally:
        conn.close()


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
    if not 1 <= month <= 12 or not 1 <= year <= 9999:
        raise BadRequest("שנה או חודש אינם תקינים")
    rows = db.query(
        "SELECT bill_id, supplier, amount, category, due_date, is_paid, payment_plan_id, installment_number, installment_count "
        "FROM bills WHERE user_id=%s ORDER BY due_date ASC",
        (session["user_id"],), fetch=True,
    )
    filtered = []
    for r in rows:
        d_val = r["due_date"]
        if isinstance(d_val, str):
            try:
                d_val = datetime.strptime(d_val[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
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

    save_name = secrets.token_hex(20) + ".png"
    full_path = os.path.join(UPLOAD_FULL, save_name)
    try:
        with Image.open(f.stream) as original:
            if original.format not in {"PNG", "JPEG", "WEBP"} or original.width * original.height > 20000000:
                raise ValueError("Unsupported image")
            original.load()
            normalized = ImageOps.exif_transpose(original).convert("RGB")
            normalized.save(full_path, format="PNG")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        if os.path.isfile(full_path):
            os.remove(full_path)
        return jsonify(ok=False, error="נדרשת תמונת JPG, PNG או WEBP תקינה, עד 20 מיליון פיקסלים"), 400
    try:
        parsed = ocr.scan_bill(full_path)
    except Exception:
        parsed = dict(amount=None, due_date=None, supplier=None, error="OCR failed")
    # OCR output is only a suggestion and must pass the same save-time rules.
    if parsed.get("due_date"):
        try:
            parsed["due_date"] = security.due_date(parsed["due_date"])
        except BadRequest:
            parsed["due_date"] = None
    if parsed.get("amount") is not None:
        try:
            parsed["amount"] = security.money(parsed["amount"])
        except BadRequest:
            parsed["amount"] = None
    parsed_ok = bool(parsed["amount"] or parsed["due_date"] or parsed["supplier"])
    # write a row to the ocr log so admins/audit can review
    db.query(
        "INSERT INTO ocr_log (user_id, image_path, parsed_ok, note) "
        "VALUES (%s, %s, %s, %s)",
        (session["user_id"], save_name, 1 if parsed_ok else 0,
         "openai: error" if parsed.get("error") else "openai: extracted; review required"),
    )
    # also try to guess a category from the supplier we read
    guessed = parsed.get("category")
    if guessed:
        allowed = db.query("SELECT category_name FROM categories", fetch=True)
        if guessed not in {row["category_name"] for row in allowed}:
            guessed = None
    return jsonify(
        ok=True,
        image=save_name,
        amount=parsed["amount"],
        due_date=parsed["due_date"],
        supplier=parsed["supplier"],
        category=guessed,
        ocr_available=ocr.OCR_OK,
        ocr_error=parsed.get("error"),
        ocr_notice=parsed.get("notice"),
        document_type=parsed.get("document_type", "unknown"),
        payment_plan=parsed.get("payment_plan"),
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
            try:
                d_val = datetime.strptime(d_val[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
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
                try:
                    d_val = datetime.strptime(d_val[:10], "%Y-%m-%d").date()
                except ValueError:
                    continue
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
    w.writerow([i18n.translate(label) for label in ["ספק", "סכום", "קטגוריה", "תאריך פירעון", "שולם"]])
    for r in rows:
        w.writerow([
            r["supplier"], f"{float(r['amount']):.2f}",
            i18n.translate(r["category"] or ""), str(r["due_date"]),
            i18n.translate("כן" if r["is_paid"] else "לא"),
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
    data = security.json_object(request)
    category = security.text(data, "category", 80, required=True)
    limit = security.money(data.get("monthly_limit"), allow_zero=True)
    db.query(
        "INSERT INTO budgets (user_id, category, monthly_limit) "
        "VALUES (%s, %s, %s) "
        "ON CONFLICT(user_id, category) DO UPDATE SET monthly_limit=excluded.monthly_limit",
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
    expected = os.environ.get("REMINDER_JOB_TOKEN", "").strip()
    supplied = request.headers.get("Authorization", "")
    token_ok = bool(expected) and hmac.compare_digest(
        supplied.encode("utf-8"), ("Bearer " + expected).encode("utf-8"))
    if not token_ok:
        err = _need_admin()
        if err:
            return err
    result = scheduler.run_notifications()
    return jsonify(ok=True, **result)


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
    app.logger.error("Internal server error", exc_info=True)
    return jsonify(ok=False, error="אירעה שגיאה פנימית. נסו שוב מאוחר יותר"), 500

# start the background reminder thread (won't double-start)
scheduler.start()


if __name__ == "__main__":
    # run dev server
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)