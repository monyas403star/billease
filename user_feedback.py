"""Private user feedback, one editable response per account; admin-only review."""
import secrets
from flask import request, session, render_template, redirect, url_for, abort
import db


def setup(app, need_login, current_user, is_admin):
    db.query('''CREATE TABLE IF NOT EXISTS user_feedback (
        user_id TEXT PRIMARY KEY, rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
        helpful TEXT NOT NULL, had_issue INTEGER NOT NULL CHECK(had_issue IN (0,1)),
        issue TEXT NOT NULL, suggestion TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)''')

    @app.route('/feedback', methods=['GET', 'POST'])
    def feedback_page():
        if not need_login():
            return redirect(url_for('root'))
        uid = session['user_id']
        token = session.get('feedback_csrf')
        if not token:
            token = secrets.token_urlsafe(32)
            session['feedback_csrf'] = token
        existing = db.query('SELECT rating,helpful,had_issue,issue,suggestion FROM user_feedback WHERE user_id=?',
                            (uid,), fetch=True, one=True)
        values = existing or dict(rating='', helpful='', had_issue='', issue='', suggestion='')
        error = None
        if request.method == 'POST':
            supplied = request.form.get('csrf', '')
            if not secrets.compare_digest(token.encode('utf-8'), supplied.encode('utf-8')):
                abort(403)
            values = {k: request.form.get(k, '').strip() for k in ('rating','helpful','had_issue','issue','suggestion')}
            if (values['rating'] not in ('1','2','3','4','5') or values['had_issue'] not in ('0','1')
                    or not 1 <= len(values['helpful']) <= 1000
                    or len(values['issue']) > 2000 or len(values['suggestion']) > 2000
                    or (values['had_issue'] == '1' and not values['issue'])):
                error = 'Please select a rating, describe the useful feature, and describe any problem you reported.'
            else:
                db.query('''INSERT INTO user_feedback(user_id,rating,helpful,had_issue,issue,suggestion)
                    VALUES(?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET
                    rating=excluded.rating,helpful=excluded.helpful,had_issue=excluded.had_issue,
                    issue=excluded.issue,suggestion=excluded.suggestion,updated_at=CURRENT_TIMESTAMP''',
                    (uid,int(values['rating']),values['helpful'],int(values['had_issue']),
                     values['issue'] if values['had_issue']=='1' else '',values['suggestion']))
                session['feedback_saved'] = True
                return redirect(url_for('feedback_page'), code=303)
        saved = session.pop('feedback_saved', False)
        return render_template('feedback.html', user=current_user(), values=values,
                               csrf=token, error=error, saved=saved), (400 if error else 200)

    @app.get('/admin/feedback')
    def admin_feedback_page():
        if not need_login():
            return redirect(url_for('root'))
        if not is_admin():
            abort(403)
        try:
            page=max(1,int(request.args.get('page','1')))
        except ValueError:
            page=1
        stats=db.query('SELECT COUNT(*) AS total, AVG(rating) AS average, COALESCE(SUM(had_issue),0) AS issues FROM user_feedback', fetch=True,one=True)
        pages=max(1,(stats['total']+19)//20)
        page=min(page,pages)
        rows=db.query('''SELECT f.rating,f.helpful,f.had_issue,f.issue,f.suggestion,f.updated_at,
            u.full_name FROM user_feedback f LEFT JOIN users u ON u.user_id=f.user_id
            ORDER BY f.updated_at DESC,f.user_id LIMIT 20 OFFSET ?''',((page-1)*20,),fetch=True)
        return render_template('admin_feedback.html',user=current_user(),rows=rows,stats=stats,page=page,pages=pages)
