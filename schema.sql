-- BillEase database schema

CREATE DATABASE IF NOT EXISTS billease CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE billease;

-- users table
CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR(50) PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL,
    phone VARCHAR(20),
    password_hash VARCHAR(255) NOT NULL,
    is_admin BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) DEFAULT CHARSET=utf8mb4;

-- expense categories
CREATE TABLE IF NOT EXISTS categories (
    category_id INT AUTO_INCREMENT PRIMARY KEY,
    category_name VARCHAR(100) NOT NULL UNIQUE,
    description VARCHAR(255)
) DEFAULT CHARSET=utf8mb4;

-- bills table
CREATE TABLE IF NOT EXISTS bills (
    bill_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    supplier VARCHAR(100),
    amount DECIMAL(10, 2) NOT NULL,
    category VARCHAR(50),
    due_date DATE NOT NULL,
    is_paid BOOLEAN DEFAULT 0,
    is_recurring BOOLEAN DEFAULT 0,
    recurrence VARCHAR(20) DEFAULT NULL,  -- 'monthly' or 'yearly'
    image_path VARCHAR(255) DEFAULT NULL,
    source VARCHAR(20) DEFAULT 'manual',  -- 'manual' or 'ocr'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) DEFAULT CHARSET=utf8mb4;

-- per-user budget per category
CREATE TABLE IF NOT EXISTS budgets (
    budget_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    category VARCHAR(50) NOT NULL,
    monthly_limit DECIMAL(10, 2) NOT NULL,
    UNIQUE KEY uniq_user_cat (user_id, category),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) DEFAULT CHARSET=utf8mb4;

-- log of OCR scans / errors (for admin)
CREATE TABLE IF NOT EXISTS ocr_log (
    log_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    image_path VARCHAR(255),
    parsed_ok BOOLEAN DEFAULT 0,
    note VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) DEFAULT CHARSET=utf8mb4;

-- default Hebrew categories
INSERT IGNORE INTO categories (category_name, description) VALUES
('חשמל', 'חשבונות חשמל'),
('מים', 'חשבונות מים'),
('אינטרנט', 'ספק אינטרנט'),
('טלפון', 'סלולר או טלפון'),
('שכירות', 'שכר דירה או משכנתא'),
('מזון', 'קניות ומזון'),
('ביטוח', 'תשלומי ביטוח'),
('מנויים', 'מנויים חודשיים'),
('ארנונה', 'מיסים עירוניים'),
('אחר', 'הוצאות נוספות');

-- demo user (id: 123456789, password: 1234) - also admin so you can see the panel
INSERT IGNORE INTO users (user_id, full_name, email, phone, password_hash, is_admin)
VALUES ('123456789', 'ישראל ישראלי', 'israel@test.com', '050-1234567',
        '03ac674216f3e15c761ee1a5e255f067953623c8b388b4459e13f978d7c846f4', 1);

-- demo bills are seeded by bootstrap.py only if the bills table is empty,
-- because bill_id is auto-increment and would duplicate on re-run.
