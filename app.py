import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import config
import db
import bootstrap

app = Flask(__name__)
app.config.from_object(config)

# تهيئة قاعدة البيانات عند تشغيل السيرفر
try:
    bootstrap.init_db()
except Exception as e:
    print(f"[Init DB Error]: {e}")

# 1. الصفحة الرئيسية (توجيه لصفحة تسجيل الدخول)
@app.route('/')
def index():
    try:
        return render_template('login.html')
    except Exception as e:
        return f"حدث خطأ في تحميل الصفحة: {str(e)}"

# 2. مسار صفحة تسجيل الدخول (Login)
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # هنا يتم استقبال بيانات الدخول إذا أردتِ معالجتها بـ POST
        pass
    return render_template('login.html')

# 3. مسار صفحة التسجيل (Register)
@app.route('/register', methods=['GET', 'POST'])
def register():
    return render_template('register.html')

# 4. مسار الدالة المخصصة لصفحة التسجيل (لتوافق الروابط)
@app.route('/register_page')
def register_page():
    return render_template('register.html')

# 5. مسار صفحة استعادة كلمة المرور (Recover)
@app.route('/recover', methods=['GET', 'POST'])
def recover():
    return render_template('recover.html')

# 6. مسار الدالة المخصصة لاستعادة كلمة المرور (لتوافق الروابط)
@app.route('/recover_page')
def recover_page():
    return render_template('recover.html')

# 7. مسار لوحة التحكم الرئيسية (Dashboard)
@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

# 8. معالجة خطأ 404 وتوجيهه بلطف بدلاً من شاشة الخطأ
@app.errorhandler(404)
def page_not_found(e):
    return render_template('login.html'), 404


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)