import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import config
import db
import bootstrap

app = Flask(__name__)
app.config.from_object(config)

try:
    bootstrap.init_db()
except Exception as e:
    print(f"[Init DB Error]: {e}")

@app.route('/')
def index():
    try:
    
        return render_template('login.html')
    except Exception as e:
        return f"حدث خطأ في تحميل الصفحة: {str(e)}"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)