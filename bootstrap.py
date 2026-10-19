import os
import sqlite3

DB_FILE = "database.db"

def init_db():
    print("[bootstrap] initializing SQLite database...")
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    # إنشاء الجداول الأساسية لـ SQLite
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        full_name TEXT,
        email TEXT,
        phone TEXT,
        password_hash TEXT,
        is_admin INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS bills (
        bill_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        supplier TEXT,
        amount REAL,
        category TEXT,
        due_date TEXT,
        is_paid INTEGER DEFAULT 0,
        is_recurring INTEGER DEFAULT 0,
        recurrence TEXT,
        image_path TEXT,
        source TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS ocr_log (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        image_path TEXT,
        parsed_ok INTEGER,
        note TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS categories (
        category_name TEXT PRIMARY KEY
    );

    CREATE TABLE IF NOT EXISTS budgets (
        user_id TEXT,
        category TEXT,
        monthly_limit REAL,
        PRIMARY KEY (user_id, category)
    );
    """)
    conn.commit()

    # إدخال بعض الفئات الافتراضية إذا كانت فارغة
    default_cats = ['חשמל', 'מים', 'אינטרנט', 'טלפון', 'ביטוח', 'שכר דירה', 'ארנונה', 'אחר']
    for cat in default_cats:
        cur.execute("INSERT OR IGNORE INTO categories (category_name) VALUES (?)", (cat,))
    conn.commit()

    # إدخال بيانات تجريبية إذا كان الجدول فارغاً
    cur.execute("SELECT COUNT(*) FROM bills WHERE user_id='123456789'")
    existing = cur.fetchone()[0]
    if existing == 0:
        demo = [
            ('123456789', 'חברת חשמל', 450.50, 'חשמל', '2026-06-01', 0, 1, 'monthly', None, 'manual'),
            ('123456789', 'מי העיר', 120.00, 'מים', '2026-05-25', 0, 1, 'monthly', None, 'manual'),
            ('123456789', 'בזק בינלאומי', 100.00, 'אינטרנט', '2026-05-15', 1, 1, 'monthly', None, 'manual'),
            ('123456789', 'סלקום', 89.00, 'טלפון', '2026-06-10', 0, 1, 'monthly', None, 'manual'),
            ('123456789', 'הראל', 210.00, 'ביטוח', '2026-06-20', 0, 0, None, None, 'manual'),
        ]
        cur.executemany(
            "INSERT INTO bills (user_id, supplier, amount, category, due_date, is_paid, is_recurring, recurrence, image_path, source) VALUES (?,?,?,?,?,?,?,?,?,?)",
            demo,
        )
        conn.commit()
        print(f"[bootstrap] seeded {len(demo)} demo bills")

    cur.close()
    conn.close()
    print("[bootstrap] SQLite database ready successfully!")
