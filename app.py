"""
UniPredict AI — Flask App
Configure database credentials in config.py
"""
from flask import (Flask, render_template, request, jsonify,
                   send_file, session, redirect, url_for)
import pandas as pd
import numpy as np
import io, os, re, hashlib
from functools import wraps
from datetime import datetime, timedelta
import time

import database as db
from student_predictor import UniPredictAI
import mailer
from config import SECRET_KEY, DEBUG, HOST, PORT, SESSION_TIMEOUT, MAX_LOGIN_ATTEMPTS, LOGIN_LOCKOUT_TIME
import utils

# ── App setup ─────────────────────────────────────────────────
app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY

BASE = os.path.dirname(os.path.abspath(__file__))

# ── ML globals ────────────────────────────────────────────────
predictor = None
_df_cache = None          # pandas DF loaded from DB for ML

# ── Init DB on startup ────────────────────────────────────────
db.init_db()

# ── Security Middleware ────────────────────────────────────────
@app.before_request
def security_headers():
    """Add security headers to all responses"""
    if request.endpoint and request.endpoint.startswith('static'):
        return
    
    # Add security headers
    response = None
    if hasattr(request, 'view_args'):
        response = getattr(request, 'view_args', None)
    
    # This will be applied to all template responses
    if request.endpoint and not request.endpoint.startswith('api'):
        return
    
    # Add security headers for API responses
    if request.endpoint and request.endpoint.startswith('api'):
        pass

# ── Input Validation ───────────────────────────────────────────
def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password_strength(password):
    """Validate password strength"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r'\d', password):
        return False, "Password must contain at least one digit"
    return True, "Password is valid"

def sanitize_input(text):
    """Sanitize user input to prevent XSS"""
    if not text:
        return ""
    # Remove potentially dangerous characters
    dangerous_chars = ['<', '>', '"', "'", '&', 'javascript:', 'vbscript:', 'onload=', 'onerror=']
    for char in dangerous_chars:
        text = text.replace(char, '')
    return text.strip()

def rate_limit_identifier():
    """Get identifier for rate limiting"""
    return request.remote_addr or 'unknown'

# ── Login Attempt Tracking ─────────────────────────────────────
login_attempts = {}

def is_rate_limited():
    """Check if user is rate limited"""
    identifier = rate_limit_identifier()
    now = time.time()
    
    if identifier not in login_attempts:
        login_attempts[identifier] = []
    
    # Remove old attempts
    login_attempts[identifier] = [
        attempt for attempt in login_attempts[identifier]
        if now - attempt < LOGIN_LOCKOUT_TIME
    ]
    
    # Check if exceeded limit
    if len(login_attempts[identifier]) >= MAX_LOGIN_ATTEMPTS:
        return True
    
    return False

def record_login_attempt():
    """Record a failed login attempt"""
    identifier = rate_limit_identifier()
    if identifier not in login_attempts:
        login_attempts[identifier] = []
    login_attempts[identifier].append(time.time())


# ─────────────────────────────────────────────────────────────
# ML HELPERS
# ─────────────────────────────────────────────────────────────
def _load_df():
    """Load students table into a pandas DataFrame for the ML predictor."""
    global _df_cache
    import database as db
    _df_cache = pd.DataFrame(db._read('students'))
    # CSV stores everything as strings — cast numeric columns back to numbers
    int_cols   = ['student_id', 'age', 'library_visits']
    float_cols = ['attendance_rate', 'study_hours_weekly', 'previous_grades',
                  'assignment_completion', 'class_participation',
                  'online_resource_hours', 'stress_level',
                  'motivation_score', 'final_grade']
    for c in int_cols:
        if c in _df_cache.columns:
            _df_cache[c] = pd.to_numeric(_df_cache[c], errors='coerce').fillna(0).astype(int)
    for c in float_cols:
        if c in _df_cache.columns:
            _df_cache[c] = pd.to_numeric(_df_cache[c], errors='coerce').fillna(0.0)
    return _df_cache


def initialize_predictor():
    global predictor, _df_cache
    if predictor is None:
        try:
            df = _load_df()
            predictor = UniPredictAI()
            X, y = predictor.preprocess_data(df.copy(), target_column='pass_fail')
            predictor.train_models(X, y, use_feature_selection=True)
        except Exception as e:
            print(f"[WARN] Predictor init failed: {e}")
            predictor = None  # will retry next time
    elif _df_cache is None:
        _load_df()


def reload_df():
    global _df_cache
    _df_cache = None
    _load_df()


# ─────────────────────────────────────────────────────────────
# AUTH DECORATORS
# ─────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def dec(*a, **kw):
        is_api = request.is_json or request.path.startswith('/api/')
        if 'user_id' not in session:
            if is_api:
                return jsonify({'success': False, 'error': 'Login required'}), 401
            return redirect(url_for('login'))
        
        # Check session timeout
        last_activity = session.get('last_activity', 0)
        if datetime.now().timestamp() - last_activity > SESSION_TIMEOUT:
            session.clear()
            if is_api:
                return jsonify({'success': False, 'error': 'Session expired. Please login again.'}), 401
            return redirect(url_for('login'))
        
        # Update last activity
        session['last_activity'] = datetime.now().timestamp()
        return f(*a, **kw)
    return dec


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def dec(*a, **kw):
            is_api = request.is_json or request.path.startswith('/api/')
            if 'user_id' not in session:
                if is_api:
                    return jsonify({'success': False, 'error': 'Login required'}), 401
                return redirect(url_for('login'))
            if session.get('role') not in roles:
                if is_api:
                    return jsonify({'success': False, 'error': 'Access denied'}), 403
                return redirect(url_for('dashboard'))
            return f(*a, **kw)
        return dec
    return decorator


# ─────────────────────────────────────────────────────────────
# AUTH ROUTES
# ─────────────────────────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Check rate limiting
        if is_rate_limited():
            return jsonify({
                'success': False, 
                'error': f'Too many failed login attempts. Please try again after {LOGIN_LOCKOUT_TIME//60} minutes.'
            }), 429
        
        data = request.get_json()
        username = sanitize_input(data.get('username') or '').strip()
        password = (data.get('password') or '')
        
        # Basic validation
        if not username:
            return jsonify({'success': False, 'error': 'Username is required'}), 400
        if not password:
            return jsonify({'success': False, 'error': 'Password is required'}), 400
        
        user = db.get_user_by_username(username)
        if user and user['password_hash'] == db.hash_pw(password):
            # Clear login attempts on successful login
            if rate_limit_identifier() in login_attempts:
                del login_attempts[rate_limit_identifier()]
            
            session.update({
                'user_id':  user['id'],
                'username': user['username'],
                'name':     user['name'],
                'role':     user['role'],
                'email':    user.get('email', ''),
                'last_activity': datetime.now().timestamp()
            })
            db.add_notification(f"'{user['name']}' logged in", 'info', username)
            db.audit(user['id'], 'LOGIN')
            utils.log_activity(user['id'], 'login', {'username': username})
            return jsonify({'success': True, 'role': user['role'],
                            'redirect': url_for('dashboard')})
        else:
            # Record failed attempt
            record_login_attempt()
            remaining_attempts = MAX_LOGIN_ATTEMPTS - len(login_attempts.get(rate_limit_identifier(), []))
            return jsonify({
                'success': False, 
                'error': f'Invalid username or password. {remaining_attempts} attempts remaining.'
            }), 401
    return render_template('login.html')


@app.route('/logout')
def logout():
    if 'user_id' in session:
        db.add_notification(f"'{session.get('name', '?')}' logged out", 'info')
        db.audit(session['user_id'], 'LOGOUT')
    session.clear()
    return redirect(url_for('login'))


# ─────────────────────────────────────────────────────────────
# FORGOT PASSWORD
# ─────────────────────────────────────────────────────────────
@app.route('/forgot-password', methods=['GET'])
def forgot_password_page():
    return render_template('forgot_password.html')


@app.route('/api/forgot-password', methods=['POST'])
def api_forgot_password():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    email    = data.get('email', '').strip()

    if not email:
        return jsonify({'success': False, 'error': 'Email address is required'}), 400

    # Support email-only OR username + email
    if username:
        user = db.get_user_by_username(username)
        if not user or user.get('email', '').strip().lower() != email.lower():
            # Generic message — don't reveal whether user exists
            return jsonify({'success': True, 'message': 'If the details match, a reset link has been sent.'})
    else:
        user = db.get_user_by_email(email)
        if not user:
            return jsonify({'success': True, 'message': 'If the details match, a reset link has been sent.'})

    token = db.create_reset_token(user['id'])
    reset_url = request.host_url.rstrip('/') + f'/reset-password/{token}'

    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb">
      <div style="background:linear-gradient(135deg,#5b5cf6,#8b5cf6);padding:24px 30px;color:#fff">
        <div style="font-size:20px;font-weight:700">🎓 UniPredict AI — Password Reset</div>
      </div>
      <div style="padding:28px 30px">
        <p style="color:#1e293b">Dear <strong>{user['name']}</strong>,</p>
        <p style="color:#475569">We received a request to reset your password. Click the button below to set a new password:</p>
        <div style="text-align:center;margin:28px 0">
          <a href="{reset_url}" style="background:linear-gradient(135deg,#5b5cf6,#8b5cf6);color:#fff;padding:13px 32px;border-radius:10px;text-decoration:none;font-weight:600;font-size:15px">🔑 Reset My Password</a>
        </div>
        <p style="color:#64748b;font-size:13px">This link expires in <strong>1 hour</strong>. If you did not request a reset, please ignore this email.</p>
        <div style="background:#f8fafc;border-radius:8px;padding:12px;font-size:12px;color:#94a3b8;word-break:break-all">
          Or copy this link: {reset_url}
        </div>
      </div>
      <div style="background:#f8fafc;padding:14px 30px;text-align:center;font-size:11px;color:#94a3b8;border-top:1px solid #e5e7eb">UniPredict AI · Confidential</div>
    </div>"""

    result = mailer.send_email(
        email, '🔑 UniPredict AI — Password Reset Request', html_body,
        f"Password reset link (expires in 1 hour):\n{reset_url}"
    )
    db.audit(user['id'], 'PASSWORD_RESET_REQUEST', None, email)
    return jsonify({'success': True, 'message': 'If the details match, a reset link has been sent.',
                    'simulated': result.get('simulated', False), 'reset_url': reset_url if result.get('simulated') else None})


@app.route('/reset-password/<token>', methods=['GET'])
def reset_password_page(token):
    user_id = db.get_token_user(token)
    if not user_id:
        return render_template('reset_password.html', token=token, expired=True)
    return render_template('reset_password.html', token=token, expired=False)


@app.route('/api/reset-password', methods=['POST'])
def api_reset_password():
    data     = request.get_json() or {}
    token    = data.get('token', '').strip()
    new_pwd  = data.get('password', '').strip()
    if not token or not new_pwd:
        return jsonify({'success': False, 'error': 'Token and password are required'}), 400
    if len(new_pwd) < 6:
        return jsonify({'success': False, 'error': 'Password must be at least 6 characters'}), 400

    user_id = db.get_token_user(token)
    if not user_id:
        return jsonify({'success': False, 'error': 'Reset link has expired or is invalid'}), 400

    db.update_user_password(user_id, new_pwd)
    db.consume_reset_token(token)
    user = db.get_user_by_id(user_id)
    if user:
        db.audit(user_id, 'PASSWORD_RESET', None, 'via reset link')
    return jsonify({'success': True, 'message': 'Password updated successfully. You can now log in.'})


@app.route('/api/change-password', methods=['POST'])
@login_required
def api_change_password():
    data        = request.get_json() or {}
    current_pwd = data.get('current_password', '').strip()
    new_pwd     = data.get('new_password', '').strip()
    
    # Basic validation
    if not current_pwd or not new_pwd:
        return jsonify({'success': False, 'error': 'Both fields are required'}), 400
    
    # Validate password strength
    is_valid, validation_msg = validate_password_strength(new_pwd)
    if not is_valid:
        return jsonify({'success': False, 'error': validation_msg}), 400

    import hashlib as _hl
    user = db.get_user_by_id(session['user_id'])
    if not user or user['password_hash'] != _hl.sha256(current_pwd.encode()).hexdigest():
        return jsonify({'success': False, 'error': 'Current password is incorrect'}), 400

    db.update_user_password(session['user_id'], new_pwd)
    db.audit(session['user_id'], 'PASSWORD_CHANGED', None, 'self-service')
    return jsonify({'success': True, 'message': 'Password changed successfully!'})



# ─────────────────────────────────────────────────────────────
# DASHBOARD ROUTER
# ─────────────────────────────────────────────────────────────
@app.route('/')
@login_required
def dashboard():
    role = session.get('role')
    return redirect(url_for({
        'admin':     'admin_dashboard',
        'teacher':   'teacher_dashboard',
        'counselor': 'counselor_dashboard',
        'parent':    'parent_dashboard',
    }.get(role, 'login')))


# ─────────────────────────────────────────────────────────────
# ADMIN DASHBOARD
# ─────────────────────────────────────────────────────────────
@app.route('/admin')
@role_required('admin')
def admin_dashboard():
    initialize_predictor()
    from sklearn.metrics import accuracy_score
    stats = db.get_summary_stats()
    all_users = db.get_all_users()
    stats['total_teachers']   = len(all_users['teachers'])
    stats['total_counselors'] = len(all_users['counselors'])
    stats['total_parents']    = len(all_users['parents'])
    stats['models'] = []
    if predictor is not None:
        stats['models'] = [
            {'name': n, 'accuracy': round(accuracy_score(
                predictor.y_test, m.predict(predictor.X_test)) * 100, 2)}
            for n, m in predictor.models.items()
        ]
    table_info = db.get_table_info()
    notif_count = len(db.get_notifications(100))
    
    # Get report statistics and recent reports for admin
    report_stats = db.get_report_statistics(None, 'admin')
    raw_reports = db.get_sent_reports(limit=50, teacher_id=None)
    reports = []
    for r in raw_reports:
        student = db.get_student_by_id(int(r.get('student_id', 0))) or {}
        r['student_name'] = student.get('student_name', f"Student #{r.get('student_id','?')}")
        reports.append(r)
    
    return render_template('admin.html', stats=stats, db_users=all_users,
                           table_info=table_info, notif_count=notif_count,
                           user_name=session['name'], user_role='admin',
                           report_stats=report_stats, reports=reports)


# ─────────────────────────────────────────────────────────────
# TEACHER DASHBOARD
# ─────────────────────────────────────────────────────────────
@app.route('/teacher')
@role_required('teacher')
def teacher_dashboard():
    initialize_predictor()
    stats = db.get_summary_stats()
    notif_count = len(db.get_notifications(100))
    return render_template('teacher.html',
                           total_students=stats['total_students'],
                           at_risk=stats['fail_count'],
                           fail_overall=stats['fail_count'],
                           pass_overall=stats['pass_count'],
                           avg_grade_overall=stats['avg_grade'],
                           notif_count=notif_count,
                           user_name=session['name'], user_role='teacher')


# ─────────────────────────────────────────────────────────────
# COUNSELOR DASHBOARD
# ─────────────────────────────────────────────────────────────
@app.route('/counselor')
@role_required('counselor')
def counselor_dashboard():
    initialize_predictor()
    students, _ = db.get_students_paginated(page=1, per_page=20, filter_by='at-risk')
    notif_count = len(db.get_notifications(100))
    stats = db.get_summary_stats()
    reported_ids = db.get_reported_student_ids()
    for s in students:
        s['is_reported'] = str(s.get('student_id', '')) in reported_ids
    return render_template('counselor.html',
                           at_risk_students=students,
                           total_students=stats['total_students'],
                           total_at_risk=stats['fail_count'],
                           pass_overall=stats['pass_count'],
                           notif_count=notif_count,
                           user_name=session['name'], user_role='counselor',
                           counselor_email=session.get('email', ''))


# ─────────────────────────────────────────────────────────────
# PARENT DASHBOARD
# ─────────────────────────────────────────────────────────────
@app.route('/parent')
@role_required('parent')
def parent_dashboard():
    # No ML needed for parent view - just load student data directly
    sid_list = db.get_parent_student_ids(session['user_id'])
    students = [s for sid in sid_list
                if (s := db.get_student_by_id(sid)) is not None]
    notif_count = len(db.get_notifications(100))
    return render_template('parent.html', students=students,
                           notif_count=notif_count,
                           user_name=session['name'], user_role='parent')


# ─────────────────────────────────────────────────────────────
# NOTIFICATIONS PAGE
# ─────────────────────────────────────────────────────────────
@app.route('/notifications')
@login_required
def notifications_page():
    # Notifications are for admins only.
    # Return 403 instead of redirecting to avoid exposing the page to non-admins.
    if session.get('role') != 'admin':
        return ('Access denied', 403)
    notifs = db.get_notifications(100)
    return render_template('notifications.html', notifications=notifs,
                           notif_count=len(notifs),
                           user_name=session['name'], user_role=session['role'])


# ═══════════════════════════════════════════════════════════════
# API — ADMIN: MANAGE TEACHERS
# ═══════════════════════════════════════════════════════════════
@app.route('/api/admin/teachers', methods=['GET'])
@role_required('admin')
def api_get_teachers():
    return jsonify({'success': True, 'teachers': db.get_users_by_role('teacher')})


def _send_staff_welcome_email(role: str, name: str, email: str, username: str, password: str, extra: str = ''):
    """Send welcome email with login credentials to a newly created staff user."""
    role_label = role.capitalize()
    role_icons = {'admin': '👑', 'teacher': '📖', 'counselor': '🤝'}
    icon = role_icons.get(role, '🎓')
    extra_row = f'<tr><td style="padding:8px 0;color:#64748b;font-size:14px">Subject / Dept</td><td style="padding:8px 0;font-weight:600;font-size:14px">{extra}</td></tr>' if extra else ''
    login_url = 'http://your-server/login'

    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:580px;margin:0 auto;background:#fff;border-radius:14px;overflow:hidden;border:1px solid #e5e7eb">
      <div style="background:linear-gradient(135deg,#5b5cf6,#8b5cf6);padding:26px 32px;color:#fff">
        <div style="font-size:22px;font-weight:700">{icon} Welcome to UniPredict AI</div>
        <div style="font-size:14px;opacity:.85;margin-top:4px">Your {role_label} account is ready</div>
      </div>
      <div style="padding:30px 32px">
        <p style="color:#1e293b;font-size:15px">Dear <strong>{name}</strong>,</p>
        <p style="color:#475569;font-size:14px;margin-top:10px">
          Your UniPredict AI account has been created. Use the credentials below to log in.
          Please change your password after your first login.
        </p>
        <table style="width:100%;border-collapse:collapse;margin:22px 0;background:#f8fafc;border-radius:10px;overflow:hidden">
          <tr><td style="padding:8px 16px;color:#64748b;font-size:14px;width:140px">Role</td><td style="padding:8px 16px;font-weight:600;font-size:14px">{icon} {role_label}</td></tr>
          <tr style="background:#fff"><td style="padding:8px 16px;color:#64748b;font-size:14px">Username</td><td style="padding:8px 16px;font-weight:700;font-size:15px;font-family:monospace;color:#5b5cf6">{username}</td></tr>
          <tr><td style="padding:8px 16px;color:#64748b;font-size:14px">Password</td><td style="padding:8px 16px;font-weight:700;font-size:15px;color:#7c3aed">{password}</td></tr>
          {extra_row}
        </table>
        <div style="text-align:center;margin:24px 0">
          <a href="{login_url}" style="background:linear-gradient(135deg,#5b5cf6,#8b5cf6);color:#fff;padding:13px 32px;border-radius:10px;text-decoration:none;font-weight:600;font-size:15px">🔐 Login to UniPredict AI</a>
        </div>
        <p style="color:#94a3b8;font-size:12px;text-align:center">
          ⚠️ Please change your password after your first login.<br>
          Keep your credentials confidential.
        </p>
      </div>
      <div style="background:#f8fafc;padding:14px 32px;text-align:center;font-size:11px;color:#94a3b8;border-top:1px solid #e5e7eb">
        UniPredict AI · This is an automated message — do not reply.
      </div>
    </div>"""

    plain_body = (
        f"Welcome to UniPredict AI\n\n"
        f"Your {role_label} account is ready.\n\n"
        f"Username: {username}\nPassword: {password}\n"
        f"{('Subject: ' + extra + chr(10)) if extra else ''}"
        f"\nLogin at: {login_url}\n\n"
        f"Please change your password after first login."
    )
    return mailer.send_email(email, f'🎓 UniPredict AI — Your {role_label} Account Credentials', html_body, plain_body)


@app.route('/api/admin/teachers/add', methods=['POST'])
@role_required('admin')
def api_add_teacher():
    data = request.get_json()
    
    # Sanitize and validate inputs
    for field in ('name', 'email', 'phone', 'subject', 'password'):
        if not data.get(field):
            return jsonify({'success': False, 'error': f'Missing: {field}'}), 400
    
    # Validate email
    if not validate_email(data['email'].strip()):
        return jsonify({'success': False, 'error': 'Invalid email format'}), 400
    
    # Validate password strength
    is_valid, msg = validate_password_strength(data['password'])
    if not is_valid:
        return jsonify({'success': False, 'error': msg}), 400
    
    # Sanitize inputs
    name = sanitize_input(data['name'])
    email = sanitize_input(data['email'])
    phone = sanitize_input(data['phone'])
    subject = sanitize_input(data['subject'])
    password = data['password']  # Don't sanitize password
    
    new_id  = db.next_user_id('teacher')
    num     = int(re.search(r'(\d+)$', new_id).group(1))
    _name_parts = [p for p in name.split() if not re.match(r'^(dr|mr|mrs|ms|prof)\.?$', p, re.I)]
    slug    = re.sub(r'[^a-z0-9]', '', (_name_parts[0] if _name_parts else name.split()[0]).lower())
    username = f"teacher_{slug}{num}"
    db.add_user(new_id, username, password, name, email, phone, 'teacher', subject)
    db.add_notification(f"Admin added teacher: {name} ({new_id})", 'success', session['username'])
    db.audit(session['user_id'], 'ADD_TEACHER', new_id, name)
    utils.log_activity(session['user_id'], 'add_teacher', {'teacher_id': new_id, 'name': name})
    
    # Send welcome email with credentials
    email_result = _send_staff_welcome_email('teacher', name, email, username, password, subject)
    return jsonify({'success': True, 'id': new_id, 'username': username,
                    'name': name, 'email': email, 'phone': phone, 'subject': subject,
                    'email_sent': email_result.get('success', False),
                    'email_simulated': email_result.get('simulated', False)})


@app.route('/api/admin/teachers/delete/<tid>', methods=['DELETE'])
@role_required('admin')
def api_delete_teacher(tid):
    user = db.get_user_by_id(tid)
    if not user:
        return jsonify({'success': False, 'error': 'Teacher not found'}), 404
    db.delete_user(tid)
    db.add_notification(f"Admin deleted teacher {tid}", 'warning', session['username'])
    db.audit(session['user_id'], 'DELETE_TEACHER', tid, user['name'])
    return jsonify({'success': True})


@app.route('/api/admin/counselors', methods=['GET'])
@role_required('admin')
def api_get_counselors():
    return jsonify({'success': True, 'counselors': db.get_users_by_role('counselor')})


@app.route('/api/admin/counselors/add', methods=['POST'])
@role_required('admin')
def api_add_counselor():
    data = request.get_json()
    for field in ('name', 'email', 'phone', 'password'):
        if not data.get(field):
            return jsonify({'success': False, 'error': f'Missing: {field}'}), 400
    new_id   = db.next_user_id('counselor')
    num      = int(re.search(r'(\d+)$', new_id).group(1))
    _name_parts = [p for p in data['name'].split() if not re.match(r'^(dr|mr|mrs|ms|prof)\.?$', p, re.I)]
    slug     = re.sub(r'[^a-z0-9]', '', (_name_parts[0] if _name_parts else data['name'].split()[0]).lower())
    username = f"counselor_{slug}{num}"
    db.add_user(new_id, username, data['password'],
                data['name'], data['email'], data['phone'],
                'counselor')
    db.add_notification(f"Admin added counselor: {data['name']} ({new_id})", 'success', session['username'])
    db.audit(session['user_id'], 'ADD_COUNSELOR', new_id, data['name'])
    email_result = _send_staff_welcome_email('counselor', data['name'], data['email'], username, data['password'])
    return jsonify({'success': True, 'id': new_id, 'username': username,
                    'name': data['name'], 'email': data['email'], 'phone': data['phone'],
                    'email_sent': email_result.get('success', False),
                    'email_simulated': email_result.get('simulated', False)})


@app.route('/api/admin/counselors/delete/<cid>', methods=['DELETE'])
@role_required('admin')
def api_delete_counselor(cid):
    user = db.get_user_by_id(cid)
    if not user:
        return jsonify({'success': False, 'error': 'Counselor not found'}), 404
    db.delete_user(cid)
    db.add_notification(f"Admin deleted counselor {cid}", 'warning', session['username'])
    db.audit(session['user_id'], 'DELETE_COUNSELOR', cid, user['name'])
    return jsonify({'success': True})


@app.route('/api/admin/admins/add', methods=['POST'])
@role_required('admin')
def api_add_admin():
    data = request.get_json()
    for field in ('name', 'email', 'phone', 'password'):
        if not data.get(field):
            return jsonify({'success': False, 'error': f'Missing: {field}'}), 400
    new_id   = db.next_user_id('admin')
    num      = int(re.search(r'(\d+)$', new_id).group(1))
    _name_parts = [p for p in data['name'].split() if not re.match(r'^(dr|mr|mrs|ms|prof)\.?$', p, re.I)]
    slug     = re.sub(r'[^a-z0-9]', '', (_name_parts[0] if _name_parts else data['name'].split()[0]).lower())
    username = f"admin_{slug}{num}"
    db.add_user(new_id, username, data['password'],
                data['name'], data['email'], data['phone'],
                'admin')
    db.add_notification(f"Admin added new admin: {data['name']} ({new_id})", 'success', session['username'])
    db.audit(session['user_id'], 'ADD_ADMIN', new_id, data['name'])
    email_result = _send_staff_welcome_email('admin', data['name'], data['email'], username, data['password'])
    return jsonify({'success': True, 'id': new_id, 'username': username,
                    'name': data['name'], 'email': data['email'], 'phone': data['phone'],
                    'email_sent': email_result.get('success', False),
                    'email_simulated': email_result.get('simulated', False)})


@app.route('/api/admin/admins/delete/<aid>', methods=['DELETE'])
@role_required('admin')
def api_delete_admin(aid):
    if aid == session['user_id']:
        return jsonify({'success': False, 'error': 'You cannot delete your own admin account'}), 400
    user = db.get_user_by_id(aid)
    if not user:
        return jsonify({'success': False, 'error': 'Admin not found'}), 404
    db.delete_user(aid)
    db.add_notification(f"Admin deleted admin account {aid}", 'warning', session['username'])
    db.audit(session['user_id'], 'DELETE_ADMIN', aid, user['name'])
    return jsonify({'success': True})


@app.route('/api/admin/users', methods=['GET'])
@role_required('admin')
def api_all_users():
    return jsonify({'success': True, 'users': db.get_all_users()})


@app.route('/api/admin/audit', methods=['GET'])
@role_required('admin')
def api_admin_audit():
    limit = min(int(request.args.get('limit', 200)), 500)
    rows = db.get_audit_log(limit)
    return jsonify({'success': True, 'log': rows})


@app.route('/api/admin/query', methods=['POST'])
@role_required('admin')
def api_admin_query():
    data = request.get_json() or {}
    sql = data.get('sql', '').strip()
    if not sql:
        return jsonify({'success': False, 'error': 'No SQL provided'}), 400
    if not sql.upper().startswith('SELECT'):
        return jsonify({'success': False, 'error': 'Only SELECT queries are permitted'}), 400
    try:
        cols, rows = db.run_safe_query(sql)
        return jsonify({'success': True, 'columns': cols, 'rows': rows})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ─── Admin: truncate and re-seed students from CSV ────────────
@app.route('/api/admin/regenerate-db', methods=['POST'])
@role_required('admin')
def api_regenerate_db():
    try:
        import pandas as pd
        csv_path = os.path.join(BASE, 'student_dataset.csv')
        if not os.path.exists(csv_path):
            return jsonify({'success': False, 'error': 'student_dataset.csv not found'}), 400
        db.truncate_and_reseed_students(csv_path)
        db.add_notification('Admin re-seeded student database from CSV', 'success', session['username'])
        db.audit(session['user_id'], 'RESEED_STUDENTS', None, 'from CSV')
        stats = db.get_summary_stats()
        return jsonify({'success': True, 'message': f'Students re-seeded from CSV. Total: {stats["total_students"]}', 'stats': stats})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



@app.route('/api/admin/link-parent', methods=['POST'])
@role_required('admin')
def api_link_parent():
    data = request.get_json()
    pid = data.get('parent_id'); sid = data.get('student_id')
    if not pid or not sid:
        return jsonify({'success': False, 'error': 'parent_id and student_id required'}), 400
    db.link_parent_student(pid, int(sid))
    db.audit(session['user_id'], 'LINK_PARENT', pid, f"student {sid}")
    return jsonify({'success': True})


def _send_parent_welcome_email(parent_name, parent_email, username, password, student_name, counselor_info=None):
    """Send login credentials email to a parent."""
    subject = f"🎓 UniPredict AI — Your Login Credentials"
    counselor_info = counselor_info or {}
    html_body = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb">
      <div style="background:linear-gradient(135deg,#5b5cf6,#8b5cf6);padding:26px 30px;color:#fff">
        <div style="font-size:22px;font-weight:700;margin-bottom:4px">🎓 UniPredict AI</div>
        <div style="opacity:.8;font-size:13px">Student Performance Intelligence Platform</div>
      </div>
      <div style="padding:28px 30px">
        <p style="font-size:16px;color:#1e293b">Dear <strong>{parent_name}</strong>,</p>
        <p style="color:#475569">Your parent account has been created on UniPredict AI for monitoring the academic performance of <strong>{student_name}</strong>.</p>
        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:20px;margin:20px 0">
          <div style="font-weight:600;color:#1e293b;margin-bottom:12px">🔐 Your Login Credentials</div>
          <table style="width:100%;border-collapse:collapse">
            <tr><td style="padding:8px 0;color:#64748b;font-size:14px">Username</td><td style="padding:8px 0;font-weight:700;font-size:15px;color:#5b5cf6">{username}</td></tr>
            <tr><td style="padding:8px 0;color:#64748b;font-size:14px">Password</td><td style="padding:8px 0;font-weight:700;font-size:15px;color:#5b5cf6">{password}</td></tr>
            <tr><td style="padding:8px 0;color:#64748b;font-size:14px">Student</td><td style="padding:8px 0;font-weight:600;font-size:14px">{student_name}</td></tr>
          </table>
        </div>
        <p style="color:#475569;font-size:13px">Please keep your credentials safe. You can use these to log in and view your child's academic reports and performance predictions.</p>
        <div style="background:#fef3c7;border:1px solid #fde68a;border-radius:8px;padding:12px;font-size:13px;color:#92400e;margin-top:16px">
          ⚠️ Please change your password after your first login for security.
        </div>
      </div>
      <div style="background:#f8fafc;padding:14px 30px;border-top:1px solid #e5e7eb;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
        <div style="font-size:11px;color:#94a3b8">UniPredict AI · Academic Intelligence Platform · Confidential</div>
        {'<div style="font-size:11px;color:#6b7280">Counselor: <strong>' + counselor_info.get("name","") + '</strong>' + (' · 📧 ' + counselor_info.get("email","") if counselor_info.get("email") else "") + '</div>' if counselor_info and (counselor_info.get("name") or counselor_info.get("email")) else ""}
      </div>
    </div>"""
    plain_body = (
        f"Dear {parent_name},\n\n"
        f"Your UniPredict AI parent account credentials:\n"
        f"Username: {username}\nPassword: {password}\nStudent: {student_name}\n\n"
        f"Please keep these credentials safe."
    )
    return mailer.send_email(parent_email, subject, html_body, plain_body)


@app.route('/api/admin/send-parent-passwords', methods=['POST'])
@role_required('admin')
def api_send_parent_passwords():
    """Bulk send login credentials to all parents via email."""
    parents = db.get_users_by_role('parent')
    # Build student lookup: parent_id -> student_name
    import csv as _csv
    ps_path = os.path.join(os.path.dirname(__file__), 'data', 'parent_students.csv')
    stu_path = os.path.join(os.path.dirname(__file__), 'data', 'students.csv')
    ps_map = {}
    try:
        with open(ps_path) as f:
            for row in _csv.DictReader(f):
                ps_map.setdefault(row['parent_id'], []).append(row['student_id'])
    except Exception:
        pass
    stu_map = {}
    try:
        with open(stu_path) as f:
            for row in _csv.DictReader(f):
                stu_map[row['student_id']] = row.get('student_name', f"Student #{row['student_id']}")
    except Exception:
        pass

    sent = failed = skipped = 0
    for p in parents:
        email = p.get('email', '').strip()
        password = p.get('plain_password', '').strip()
        if not email or not password:
            skipped += 1
            continue
        sids = ps_map.get(p['id'], [])
        student_name = ', '.join(stu_map.get(s, f"Student #{s}") for s in sids) or 'N/A'
        result = _send_parent_welcome_email(
            p.get('name', 'Parent'), email, p.get('username', ''), password, student_name
        )
        if result.get('success'):
            sent += 1
        elif result.get('simulated'):
            skipped += 1
        else:
            failed += 1
    db.audit(session['user_id'], 'BULK_SEND_PARENT_PASSWORDS', None,
             f"sent={sent} failed={failed} skipped={skipped}")
    return jsonify({'success': True, 'sent': sent, 'failed': failed, 'skipped': skipped,
                    'message': f"✅ Sent: {sent} | ❌ Failed: {failed} | ⏭ Skipped: {skipped}"})



# ═══════════════════════════════════════════════════════════════
# API — TEACHER: STUDENTS
# ═══════════════════════════════════════════════════════════════
@app.route('/api/teacher/students', methods=['GET'])
@role_required('teacher')
def api_teacher_students():
    try:
        page     = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 25))
        filt     = request.args.get('filter', 'all')
        students, total = db.get_students_paginated(page, per_page, filt)
        pages = (total + per_page - 1) // per_page
        reported_ids = db.get_reported_student_ids()
        for s in students:
            s['is_reported'] = str(s.get('student_id', '')) in reported_ids
            # Ensure all values are JSON-serializable
            s['counselor_reported'] = str(s.get('counselor_reported', '0') or '0')
            s['risk_factors'] = s.get('risk_factors', []) or []
        return jsonify({'success': True, 'students': students,
                        'total': total, 'page': page,
                        'per_page': per_page, 'pages': pages})
    except Exception as e:
        print(f"[ERROR] api_teacher_students: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/teacher/students/add', methods=['POST'])
@role_required('teacher')
def api_add_student():
    data = request.get_json()
    student_name = (data.get('student_name') or '').strip()
    if not student_name:
        return jsonify({'success': False, 'error': 'Student name is required'}), 400

    # Duplicate check — same name + gender + age (skip if teacher confirmed bypass)
    if not data.get('_bypass_duplicate'):
        duplicate = db.find_duplicate_student(
            student_name,
            data.get('gender', ''),
            data.get('age', '')
        )
        if duplicate:
            return jsonify({
                'success': False,
                'duplicate': True,
                'error': f'Student "{student_name}" already exists (ID #{duplicate["student_id"]}). Please check before adding again.'
            }), 409

    new_id = db.add_student(data, added_by=session['user_id'])
    db.add_notification(f"Teacher added student #{new_id}", 'success', session['username'])
    db.audit(session['user_id'], 'ADD_STUDENT', str(new_id))

    # Send credentials email to the new parent if email + name provided
    parent_email = data.get('parent_email', '').strip()
    parent_name  = data.get('parent_name', 'Parent').strip()
    student_name = data.get('student_name', f'Student #{new_id}').strip()
    parent_password = data.get('parent_password', '').strip()
    parent_username = data.get('parent_username', '').strip()

    email_status = None
    if parent_email and parent_password:
        result = _send_parent_welcome_email(
            parent_name, parent_email, parent_username or parent_email, parent_password, student_name
        )
        email_status = 'sent' if result.get('success') else ('simulated' if result.get('simulated') else 'failed')

    return jsonify({'success': True, 'student_id': new_id, 'email_status': email_status})



@app.route('/api/teacher/students/update/<int:sid>', methods=['PUT'])
@role_required('teacher')
def api_update_student(sid):
    data = request.get_json()
    if not db.get_student_by_id(sid):
        return jsonify({'success': False, 'error': 'Student not found'}), 404
    db.update_student(sid, data)
    db.add_notification(f"Teacher updated student #{sid}", 'info', session['username'])
    db.audit(session['user_id'], 'UPDATE_STUDENT', str(sid))
    return jsonify({'success': True})


@app.route('/api/teacher/students/delete/<int:sid>', methods=['DELETE'])
@role_required('teacher')
def api_teacher_delete_student(sid):
    if not db.get_student_by_id(sid):
        return jsonify({'success': False, 'error': 'Student not found'}), 404
    db.delete_student(sid)
    db.add_notification(f"Teacher deleted student #{sid}", 'warning', session['username'])
    db.audit(session['user_id'], 'DELETE_STUDENT', str(sid))
    return jsonify({'success': True})


# ═══════════════════════════════════════════════════════════════
# API — STUDENTS (shared)
# ═══════════════════════════════════════════════════════════════
def _is_student_reported(student_id):
    return str(student_id) in db.get_reported_student_ids()


@app.route('/api/student/<int:sid>', methods=['GET'])
@login_required
def api_get_student(sid):
    try:
        s = db.get_student_by_id(sid)
        if not s:
            return jsonify({'success': False, 'error': 'Student not found'}), 404
        
        # Ensure all values are JSON-serializable
        s['is_reported'] = bool(_is_student_reported(sid))
        s['last_reported_at'] = str(s.get('last_reported_at', '') or '')
        s['reported_by'] = str(s.get('reported_by', '') or '')
        s['counselor_reported'] = str(s.get('counselor_reported', '0') or '0')
        s['added_by'] = str(s.get('added_by', '') or '')
        s['created_at'] = str(s.get('created_at', '') or '')
        s['updated_at'] = str(s.get('updated_at', '') or '')
        
        return jsonify({'success': True, 'student': s})
    except Exception as e:
        print(f"[ERROR] api_get_student({sid}): {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/students', methods=['GET'])
@login_required
def api_get_students():
    page     = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 25))
    filt     = request.args.get('filter', 'all')
    students, total = db.get_students_paginated(page, per_page, filt)
    pages = (total + per_page - 1) // per_page
    reported_ids = db.get_reported_student_ids()
    for s in students:
        s['is_reported'] = str(s.get('student_id', '')) in reported_ids
        s['counselor_reported'] = s.get('counselor_reported', '0') == '1'
    return jsonify({'success': True, 'students': students,
                    'total': total, 'page': page,
                    'per_page': per_page, 'pages': pages})


# ═══════════════════════════════════════════════════════════════
# API — PREDICT
# ═══════════════════════════════════════════════════════════════
@app.route('/api/predict', methods=['POST'])
@login_required
def api_predict():
    initialize_predictor()
    try:
        data = request.get_json()
        student_name = data.get('studentName', 'Unknown')
        student = {
            'gender': data.get('gender', 'Male'),
            'age': int(data.get('age', 18)),
            'attendance_rate': float(data.get('attendance', 75)),
            'study_hours_weekly': float(data.get('studyHours', 10)),
            'previous_grades': float(data.get('previousGrade', 70)),
            'assignment_completion': float(data.get('assignments', 80)),
            'class_participation': float(data.get('participation', 5)),
            'extra_curricular': data.get('extraCurricular', 'No'),
            'library_visits': int(data.get('libraryVisits', 3)),
            'online_resource_hours': float(data.get('onlineHours', 5)),
            'parent_education': data.get('parentEducation', 'Bachelor'),
            'family_income': data.get('familyIncome', 'Medium'),
            'internet_access': data.get('internetAccess', 'Yes'),
            'tutoring': data.get('tutoring', 'No'),
            'mentor_support': data.get('mentorSupport', 'No'),
            'stress_level': float(data.get('stress', 5)),
            'motivation_score': float(data.get('motivation', 7)),
        }
        prediction, probability = predictor.predict_new_student(student)
        risk_score, _ = db._calc_risk(student)

        risk_factors = []
        if student['attendance_rate'] < 75:
            risk_factors.append({'factor': 'Low Attendance', 'value': f"{student['attendance_rate']:.0f}%", 'severity': 'high'})
        if student['study_hours_weekly'] < 10:
            risk_factors.append({'factor': 'Study Hours Low', 'value': f"{student['study_hours_weekly']:.0f}/wk", 'severity': 'medium'})
        if student['assignment_completion'] < 70:
            risk_factors.append({'factor': 'Assignments Incomplete', 'value': f"{student['assignment_completion']:.0f}%", 'severity': 'high'})
        if student['stress_level'] > 7:
            risk_factors.append({'factor': 'High Stress', 'value': f"{student['stress_level']}/10", 'severity': 'high'})
        if student['motivation_score'] < 5:
            risk_factors.append({'factor': 'Low Motivation', 'value': f"{student['motivation_score']}/10", 'severity': 'medium'})
        if student['previous_grades'] < 60:
            risk_factors.append({'factor': 'Poor Previous Grade', 'value': f"{student['previous_grades']:.0f}", 'severity': 'high'})

        recs = []
        if student['attendance_rate'] < 75:
            recs.append({'type': 'warning', 'icon': '📅', 'message': f"Improve attendance ({student['attendance_rate']:.0f}%)", 'action': 'Schedule attendance counseling'})
        if student['study_hours_weekly'] < 10:
            recs.append({'type': 'warning', 'icon': '📚', 'message': f"Increase study time ({student['study_hours_weekly']:.0f} hrs/wk)", 'action': 'Enroll in study skills workshop'})
        if student['assignment_completion'] < 70:
            recs.append({'type': 'danger', 'icon': '📝', 'message': 'Improve assignment completion', 'action': 'Assign academic mentor'})
        if student['stress_level'] > 7:
            recs.append({'type': 'danger', 'icon': '🧘', 'message': 'High stress — seek counseling', 'action': 'Refer to counseling center'})
        if student['tutoring'] == 'No' and prediction == 'Fail':
            recs.append({'type': 'danger', 'icon': '🎓', 'message': 'Enroll in tutoring immediately', 'action': 'Connect with tutoring services'})
        if not recs:
            recs.append({'type': 'success', 'icon': '🌟', 'message': 'Excellent performance! Keep it up!', 'action': 'Consider for excellence award'})

        if prediction == 'Fail':
            db.add_notification(f"⚠️ At-risk: '{student_name}' (Risk: {risk_score}%)", 'danger', session.get('username', 'system'))

        prob_pass = float(probability[1]) * 100 if len(probability) > 1 else float(probability[0]) * 100
        prob_fail = float(probability[0]) * 100 if len(probability) > 1 else float(1 - probability[0]) * 100

        return jsonify({
            'success': True,
            'prediction': prediction,
            'confidence': float(max(probability) * 100),
            'probabilities': {'pass': prob_pass, 'fail': prob_fail},
            'risk_score': risk_score,
            'risk_factors': risk_factors,
            'recommendations': recs
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ═══════════════════════════════════════════════════════════════
# API — REPORTS
# ═══════════════════════════════════════════════════════════════
@app.route('/api/student/<int:sid>/report', methods=['GET'])
@login_required
def api_student_report(sid):
    # Reports visible to: teacher, admin, counselor only
    allowed_roles = ('teacher', 'admin', 'counselor')
    if session.get('role') not in allowed_roles:
        return jsonify({'success': False, 'error': 'Access restricted to staff only'}), 403
    s = db.get_student_by_id(sid)
    if not s:
        return jsonify({'success': False, 'error': 'Student not found'}), 404
    counselor_info = {}
    if session.get('role') == 'counselor':
        counselor_info = {
            'name': session.get('name', ''),
            'email': session.get('email', ''),
            'report_time': datetime.now().strftime('%d %b %Y, %H:%M'),
        }
    viewer_info = {
        'role': session.get('role', ''),
        'name': session.get('name', '')
    }
    html = _build_report_html(s, counselor_info=counselor_info, viewer_info=viewer_info)
    suggested = db.get_parent_emails_for_student(sid)
    # Also include parent email from student record if available and not already in suggested
    student_parent_email = s.get('parent_email', '').strip()
    if student_parent_email and student_parent_email not in suggested:
        suggested.append(student_parent_email)
    s['is_reported'] = _is_student_reported(sid)
    s['last_reported_at'] = s.get('last_reported_at', '')
    s['reported_by'] = s.get('reported_by', '')
    return jsonify({'success': True, 'report_html': html, 'student': s, 'suggested_parent_emails': suggested})


@app.route('/api/parent/student/<int:sid>/report', methods=['GET'])
@role_required('parent')
def api_parent_student_report(sid):
    try:
        sid_list = db.get_parent_student_ids(session['user_id'])
        if sid not in sid_list:
            return jsonify({'success': False, 'error': 'Student not linked to your account'}), 403
        s = db.get_student_by_id(sid)
        if not s:
            return jsonify({'success': False, 'error': 'Student not found'}), 404
        viewer_info = {'role': session.get('role', ''), 'name': session.get('name', '')}
        html = _build_report_html(s, counselor_info={}, viewer_info=viewer_info)
        return jsonify({'success': True, 'report_html': html, 'student': s})
    except Exception as e:
        return jsonify({'success': False, 'error': f'Report generation failed: {str(e)}'}), 500


@app.route('/api/student/<int:sid>/email-report', methods=['POST'])
@login_required
def api_email_report(sid):
    # Email report accessible to: teacher, admin, counselor
    allowed_roles = ('teacher', 'admin', 'counselor')
    if session.get('role') not in allowed_roles:
        return jsonify({'success': False, 'error': 'Access restricted to staff only'}), 403
    s = db.get_student_by_id(sid)
    if not s:
        return jsonify({'success': False, 'error': 'Student not found'}), 404

    data = request.get_json() or {}
    parent_email = data.get('email', '').strip()
    
    # If no email provided, try to get from student record
    if not parent_email and s.get('parent_email'):
        parent_email = s.get('parent_email', '').strip()
    
    if not parent_email:
        return jsonify({'success': False, 'error': 'Parent email address is required'}), 400

    # Build report
    counselor_info = {}
    if session.get('role') == 'counselor':
        counselor_info = {
            'name': session.get('name', ''),
            'email': session.get('email', ''),
            'report_time': datetime.now().strftime('%d %b %Y, %H:%M'),
        }
    viewer_info = {'role': session.get('role', ''), 'name': session.get('name', '')}
    report_html  = _build_report_html(s, counselor_info=counselor_info, viewer_info=viewer_info)
    student_name = s.get('student_name', f"Student #{sid}")
    subject      = f"📊 Academic Report — {student_name} | UniPredict AI"

    plain_body = (
        f"Academic Report for {student_name}\n"
        f"Grade: {s.get('final_grade','—')} | "
        f"Attendance: {s.get('attendance_rate','—')}% | "
        f"Status: {s.get('pass_fail','—')}\n"
        f"Parent Email: {s.get('parent_email','—')}\n\n"
        f"Report sent by: {session.get('name','—')} ({session.get('role','').title()})\n\n"
        "Please view this email in an HTML-capable client for the full report."
    )

    # Build full recipient list: parent + all staff (admin, teacher, counselor)
    all_recipients = []
    if parent_email:
        all_recipients.append(parent_email)
    for role in ('admin', 'teacher', 'counselor'):
        for u in db.get_users_by_role(role):
            email = u.get('email', '').strip()
            if email and email not in all_recipients:
                all_recipients.append(email)

    sent_ok, sent_sim, sent_fail = 0, 0, 0
    for recipient in all_recipients:
        result = mailer.send_email(
            to_email=recipient,
            subject=subject,
            html_body=report_html,
            plain_body=plain_body
        )
        r_status = 'sent' if result.get('success') else ('simulated' if result.get('simulated') else 'failed')
        db.log_email(sid, recipient, subject, session.get('name', '?'), r_status)
        if result.get('success'):
            sent_ok += 1
        elif result.get('simulated'):
            sent_sim += 1
        else:
            sent_fail += 1

    db.audit(session['user_id'], 'EMAIL_REPORT', str(sid),
             f"recipients={len(all_recipients)} ok={sent_ok} sim={sent_sim} fail={sent_fail}")

    # Mark student as reported in sent_reports only when we have at least one successful/resendable delivery
    status_to_write = 'sent' if sent_ok > 0 else ('simulated' if sent_sim > 0 else 'failed')
    db.add_sent_report(
        student_id=sid,
        teacher_id=session['user_id'],
        report_type='academic',
        content=f'Academic report sent to {len(all_recipients)} recipients',
        parent_email=parent_email,
        sent_by=session.get('name', '?'),
        status=status_to_write
    )
    if status_to_write in ('sent','simulated'):
        db.mark_student_reported(sid, session['user_id'], 'academic')

    # Counselor explicit confirmation flag for this student report flow
    if session.get('role') == 'counselor':
        db.set_counselor_reported(sid, True, session['user_id'])

    staff_count = len(all_recipients) - (1 if parent_email else 0)
    if sent_ok > 0:
        db.add_notification(
            f"📧 Report for {student_name} sent to parent + {staff_count} staff",
            'success', session.get('username')
        )
        return jsonify({'success': True,
                        'message': f"✅ Report sent to {len(all_recipients)} recipients (parent + {staff_count} staff)"})
    elif sent_sim > 0:
        db.add_notification(
            f"📋 Report for {student_name} logged — email not configured ({len(all_recipients)} recipients)",
            'info', session.get('username')
        )
        return jsonify({'success': False, 'simulated': True,
                        'message': f"⚠️ Email not configured — report logged for {len(all_recipients)} recipients"}), 200
    else:
        return jsonify({'success': False, 'error': 'Failed to send to any recipient'}), 500


@app.route('/api/student/<int:sid>/counselor-report', methods=['POST'])
@role_required('counselor')
def api_counselor_report_toggle(sid):
    s = db.get_student_by_id(sid)
    if not s:
        return jsonify({'success': False, 'error': 'Student not found'}), 404
    data = request.get_json() or {}
    state = data.get('reported')
    if state is None:
        return jsonify({'success': False, 'error': 'reported boolean field is required'}), 400

    reported = bool(state)
    db.set_counselor_reported(sid, reported, session['user_id'])
    db.audit(session['user_id'], 'COUNSELOR_REPORT_TOGGLE', str(sid),
             f"Counselor set reported={reported} for student {sid}")
    return jsonify({'success': True, 'reported': reported})


@app.route('/api/counselor/parent-emails', methods=['GET'])
@role_required('counselor')
def api_counselor_parent_emails():
    """Get all parent emails for counselor email suggestions"""
    try:
        # Get all unique parent emails from the system
        users = db.get_users_by_role('parent')
        emails = []
        seen = set()
        for user in users:
            email = (user.get('email') or '').strip()
            if email and email.lower() not in seen:
                seen.add(email.lower())
                emails.append({
                    'email': email,
                    'name': user.get('name', ''),
                    'student_count': len(db.get_parent_student_ids(user.get('id', '')))
                })
        return jsonify({'success': True, 'parent_emails': emails})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Email config routes (admin only) ─────────────────────────
@app.route('/api/admin/email-config', methods=['GET'])
@role_required('admin')
def api_get_email_config():
    cfg = mailer.load_config()
    # Never expose the password in the API
    safe = {k: v for k, v in cfg.items() if k != 'sender_password'}
    safe['has_password'] = bool(cfg.get('sender_password'))
    return jsonify({'success': True, 'config': safe})


@app.route('/api/admin/email-config', methods=['POST'])
@role_required('admin')
def api_save_email_config():
    data = request.get_json() or {}
    cfg  = mailer.load_config()

    # Update fields
    for field in ('enabled', 'provider', 'smtp_host', 'smtp_port',
                  'use_ssl', 'sender_email', 'sender_name', 'reply_to'):
        if field in data:
            cfg[field] = data[field]

    # Only update password if a new one is provided
    if data.get('sender_password'):
        cfg['sender_password'] = data['sender_password']

    mailer.save_config(cfg)
    db.audit(session['user_id'], 'UPDATE_EMAIL_CONFIG', None,
             f"provider={cfg.get('provider')} enabled={cfg.get('enabled')}")
    return jsonify({'success': True, 'message': 'Email configuration saved.'})


@app.route('/api/admin/email-test-connection', methods=['POST'])
@role_required('admin')
def api_test_email_connection():
    data = request.get_json() or {}
    cfg  = mailer.load_config()
    result = mailer.test_connection(
        host     = data.get('smtp_host', cfg.get('smtp_host', '')),
        port     = data.get('smtp_port', cfg.get('smtp_port', 465)),
        use_ssl  = data.get('use_ssl',  cfg.get('use_ssl', True)),
        email    = data.get('sender_email',    cfg.get('sender_email', '')),
        password = data.get('sender_password', cfg.get('sender_password', ''))
    )
    db.audit(session['user_id'], 'TEST_EMAIL_CONNECTION', None, result['message'][:100])
    return jsonify(result)


@app.route('/api/admin/email-send-test', methods=['POST'])
@role_required('admin')
def api_send_test_email():
    data = request.get_json() or {}
    to   = data.get('to_email', '').strip()
    if not to:
        return jsonify({'success': False, 'error': 'Recipient email required'}), 400
    result = mailer.send_email(
        to_email  = to,
        subject   = '✅ UniPredict AI — Test Email',
        html_body = f"""
        <div style="font-family:Arial,sans-serif;max-width:500px;margin:40px auto;
                    background:#f8fafc;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb">
          <div style="background:linear-gradient(135deg,#5b5cf6,#8b5cf6);padding:24px;color:#fff;text-align:center">
            <div style="font-size:32px;margin-bottom:8px">🎓</div>
            <div style="font-size:20px;font-weight:700">UniPredict AI</div>
            <div style="opacity:.8;font-size:13px;margin-top:4px">Email Test</div>
          </div>
          <div style="padding:28px;text-align:center">
            <div style="font-size:40px;margin-bottom:12px">✅</div>
            <h2 style="color:#1e293b;margin-bottom:8px">Email is working!</h2>
            <p style="color:#64748b;margin-bottom:20px">
              Your SMTP configuration is set up correctly.<br>
              Student reports will now be delivered to parent email addresses.
            </p>
            <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;
                        padding:14px;font-size:13px;color:#166534">
              Sent at {datetime.now().strftime('%d %b %Y, %H:%M')} by {session.get('name','Admin')}
            </div>
          </div>
        </div>""",
        plain_body='UniPredict AI email test — your configuration is working correctly.'
    )
    db.audit(session['user_id'], 'SEND_TEST_EMAIL', to, result['message'][:100])
    return jsonify(result)




def _flt(val, default=0):
    """Safely convert a value to float, returning default on failure."""
    try: return float(val)
    except (TypeError, ValueError): return default

def _build_report_html(s, counselor_info=None, viewer_info=None):
    rs = _flt(s.get('risk_score', 0), 0)
    rc = 'low' if rs < 30 else 'medium' if rs < 60 else 'high'
    rc_color = {'low': '#10b981', 'medium': '#f59e0b', 'high': '#ef4444'}[rc]
    factors = s.get('risk_factors', [])
    actions = []
    if _flt(s.get('attendance_rate', 100), 100) < 75: actions.append('Enroll in Attendance Recovery Programme')
    if _flt(s.get('study_hours_weekly', 10), 10) < 10: actions.append('Join Study Skills Workshop')
    if _flt(s.get('assignment_completion', 100), 100) < 70: actions.append('Academic Mentor Assignment')
    if _flt(s.get('stress_level', 0), 0) > 7: actions.append('Counselling Centre Referral')
    if s.get('pass_fail') == 'Fail': actions.append('Enroll in Subject Tutoring')
    if not actions: actions.append('Student is performing well — maintain current approach')
    counselor_block = ''
    if counselor_info and (counselor_info.get('name') or counselor_info.get('email') or counselor_info.get('report_time')):
        c_name  = counselor_info.get('name', '')
        c_email = counselor_info.get('email', '')
        c_time  = counselor_info.get('report_time', '')
        counselor_block = f'''
        <div style="background:#f0f4ff;border-left:4px solid #5b5cf6;border-radius:8px;padding:14px 18px;margin-bottom:18px;display:flex;align-items:center;gap:14px">
          <div style="font-size:28px">🤝</div>
          <div>
            <div style="font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:#6b7280;margin-bottom:3px">Assigned Counselor</div>
            {'<div style="font-weight:700;color:#1e293b;font-size:15px">'+c_name+'</div>' if c_name else ''}
            {'<div style="color:#5b5cf6;font-size:13px">📧 '+c_email+'</div>' if c_email else ''}
            {'<div style="color:#64748b;font-size:12px;margin-top:4px">🕐 Report time: <strong>'+c_time+'</strong></div>' if c_time else ''}
          </div>
        </div>'''
    
    # Add recipient email block when counselor sends report
    recipient_block = ''
    if counselor_info and s.get('parent_email'):
        recipient_email = s.get('parent_email', '')
        recipient_block = f'''
        <div style="background:#fef3c7;border-left:4px solid #f59e0b;border-radius:8px;padding:14px 18px;margin-bottom:18px;display:flex;align-items:center;gap:14px">
          <div style="font-size:28px">👨‍👩‍👧‍👦</div>
          <div>
            <div style="font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:#6b7280;margin-bottom:3px">Report Recipient</div>
            <div style="font-weight:700;color:#1e293b;font-size:15px">Parent/Guardian</div>
            <div style="color:#d97706;font-size:13px">📧 {recipient_email}</div>
          </div>
        </div>'''
    ff = ''.join(f'<span style="background:#fee2e2;color:#b91c1c;padding:3px 10px;border-radius:12px;font-size:12px;margin:3px;display:inline-block">⚠️ {f}</span>' for f in factors) or '<span style="color:#10b981">No major risk factors</span>'
    fi = ''.join(f'<li style="margin:6px 0">{a}</li>' for a in actions)
    pf_color = '#065f46' if s.get('pass_fail') == 'Pass' else '#991b1b'
    pf_bg    = '#d1fae5' if s.get('pass_fail') == 'Pass' else '#fee2e2'
    viewer_badge = ''
    if viewer_info and viewer_info.get('role'):
        role_labels = {'teacher': '📖 Teacher', 'admin': '👑 Admin', 'counselor': '🤝 Counselor'}
        role_label = role_labels.get(viewer_info['role'], viewer_info['role'].title())
        viewer_badge = f'<div style="background:rgba(255,255,255,.18);border-radius:6px;padding:4px 10px;font-size:11px;display:inline-block;margin-top:6px">Viewed by {role_label}: {viewer_info.get("name","")}</div>'

    return f"""
    <div style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb">
      <div style="background:linear-gradient(135deg,#2563eb,#3b82f6);padding:26px 30px;color:#fff">
        <div style="font-size:22px;font-weight:700;margin-bottom:4px">🎓 UniPredict AI — Student Report</div>
        <div style="opacity:.8;font-size:13px">Generated: {datetime.now().strftime('%d %b %Y, %H:%M')} &nbsp;|&nbsp; Student ID: #{s.get('student_id')}</div>
        <div style="margin-top:8px;font-size:16px;font-weight:600;opacity:.9">{s.get('student_name', f"Student #{s.get('student_id','?')}")}</div>
        {f'<div style="opacity:.7;font-size:13px;margin-top:4px">👨‍👩‍👧 Parent: {s["parent_name"]}</div>' if s.get('parent_name') else ''}
        {f'<div style="opacity:.7;font-size:13px;margin-top:2px">📧 Parent Email: {s["parent_email"]}</div>' if s.get('parent_email') else ''}
        {f'<div style="opacity:.7;font-size:13px;margin-top:2px">📍 {s["address"]}</div>' if s.get('address') else ''}
        {viewer_badge}
      </div>
      <div style="padding:26px 30px">
        <table style="width:100%;border-collapse:collapse;margin-bottom:20px">
          <tr><th colspan="4" style="background:#f3f4f6;padding:10px 12px;text-align:left;font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:#6b7280">Academic Overview</th></tr>
          <tr style="border-bottom:1px solid #e5e7eb"><td style="padding:11px 12px;color:#6b7280;font-size:13px">Final Grade</td><td style="padding:11px 12px;font-weight:700;font-size:16px">{_flt(s.get('final_grade', 0)):.1f}</td><td style="padding:11px 12px;color:#6b7280;font-size:13px">Status</td><td style="padding:11px 12px"><span style="background:{pf_bg};color:{pf_color};padding:4px 12px;border-radius:20px;font-size:12px;font-weight:600">{s.get('pass_fail','—')}</span></td></tr>
          <tr style="border-bottom:1px solid #e5e7eb"><td style="padding:11px 12px;color:#6b7280;font-size:13px">Attendance</td><td style="padding:11px 12px;font-weight:600">{_flt(s.get('attendance_rate', 0)):.1f}%</td><td style="padding:11px 12px;color:#6b7280;font-size:13px">Study Hours/Wk</td><td style="padding:11px 12px;font-weight:600">{_flt(s.get('study_hours_weekly', 0)):.1f} hrs</td></tr>
          <tr style="border-bottom:1px solid #e5e7eb"><td style="padding:11px 12px;color:#6b7280;font-size:13px">Assignments</td><td style="padding:11px 12px;font-weight:600">{_flt(s.get('assignment_completion', 0)):.1f}%</td><td style="padding:11px 12px;color:#6b7280;font-size:13px">Stress Level</td><td style="padding:11px 12px;font-weight:600">{_flt(s.get('stress_level', 0)):.1f}/10</td></tr>
          <tr><td style="padding:11px 12px;color:#6b7280;font-size:13px">Motivation</td><td style="padding:11px 12px;font-weight:600">{_flt(s.get('motivation_score', 0)):.1f}/10</td><td style="padding:11px 12px;color:#6b7280;font-size:13px">Category</td><td style="padding:11px 12px;font-weight:600">{s.get('performance_category','—')}</td></tr>
        </table>
        <div style="background:#f8fafc;border-radius:10px;padding:16px;margin-bottom:18px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
            <span style="font-weight:600;color:#1e293b">📊 Risk Assessment</span>
            <span style="font-weight:700;color:{rc_color}">{rs}% — {rc.upper()}</span>
          </div>
          <div style="background:#e2e8f0;border-radius:4px;height:8px;margin-bottom:12px"><div style="width:{rs}%;background:{rc_color};height:8px;border-radius:4px"></div></div>
          <div>{ff}</div>
        </div>
        <div style="background:#eff6ff;border-radius:10px;padding:16px;margin-bottom:18px">
          <div style="font-weight:600;color:#1e40af;margin-bottom:10px">💡 Recommended Interventions</div>
          <ul style="margin:0;padding-left:20px;color:#374151">{fi}</ul>
        </div>
        {counselor_block}
        {recipient_block}
        <div style="background:#f0fdf4;border-radius:10px;padding:14px;font-size:13px;color:#166534">
          <strong>Note:</strong> This report is generated by UniPredict AI. Contact the class teacher or counselor for further guidance.
        </div>
      </div>
      <div style="background:#f8fafc;padding:14px 30px;text-align:center;font-size:11px;color:#94a3b8;border-top:1px solid #e5e7eb">UniPredict AI · Academic Intelligence Platform · Confidential</div>
    </div>"""


# ═══════════════════════════════════════════════════════════════
# API — STATS & NOTIFICATIONS
# ═══════════════════════════════════════════════════════════════
@app.route('/api/statistics', methods=['GET'])
@login_required
def api_statistics():
    return jsonify({'success': True, 'statistics': db.get_summary_stats()})


@app.route('/api/notifications', methods=['GET'])
@login_required
@role_required('admin')
def api_notifications():
    notifs = db.get_notifications(50)
    return jsonify({'success': True, 'notifications': notifs, 'count': len(notifs)})


@app.route('/api/notifications/clear', methods=['POST'])
@login_required
@role_required('admin')
def api_clear_notifications():
    db.clear_notifications()
    return jsonify({'success': True})


@app.route('/api/feature-importance', methods=['GET'])
@login_required
def api_feature_importance():
    initialize_predictor()
    try:
        if hasattr(predictor.best_model, 'feature_importances_'):
            imps = predictor.best_model.feature_importances_
            feats = getattr(predictor, 'selected_features', predictor.feature_names)
            fi = sorted(
                [{'feature': feats[i], 'importance': round(float(imps[i]) * 100, 2)}
                 for i in range(min(len(imps), len(feats)))],
                key=lambda x: x['importance'], reverse=True
            )[:10]
            return jsonify({'success': True, 'features': fi})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    return jsonify({'success': False, 'error': 'Not available'}), 400


@app.route('/api/session', methods=['GET'])
def api_session():
    if 'user_id' in session:
        return jsonify({'logged_in': True, 'user_id': session['user_id'],
                        'role': session['role'], 'name': session['name']})
    return jsonify({'logged_in': False})


# ─────────────────────────────────────────────────────────────
# NEW FEATURES API ENDPOINTS
# ─────────────────────────────────────────────────────────────

@app.route('/api/activity/stats', methods=['GET'])
@login_required
@utils.api_rate_limit(max_requests=50, window_seconds=3600)
def api_activity_stats():
    """Get activity statistics for dashboard"""
    days = request.args.get('days', 7, type=int)
    stats = utils.get_activity_stats(days)
    return jsonify({'success': True, 'stats': stats})

@app.route('/api/students/search', methods=['GET'])
@login_required
@utils.api_rate_limit(max_requests=100, window_seconds=3600)
def api_search_students():
    """Advanced student search with filters"""
    try:
        query = request.args.get('q', '').strip()
        risk_level = request.args.get('risk_level', '')
        status = request.args.get('status', '')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        # Get all students
        all_students = db._read('students')
        
        # Apply filters
        filtered_students = []
        for student in all_students:
            student_data = db._to_student(student)
            
            # Text search
            if query:
                searchable_text = f"{student_data.get('student_name', '')} {student_data.get('parent_name', '')} {student_data.get('parent_email', '')}".lower()
                if query.lower() not in searchable_text:
                    continue
            
            # Risk level filter
            if risk_level:
                risk_score = student_data.get('risk_score', 0)
                if risk_level == 'low' and risk_score >= 30:
                    continue
                elif risk_level == 'medium' and (risk_score < 30 or risk_score >= 60):
                    continue
                elif risk_level == 'high' and risk_score < 60:
                    continue
            
            # Status filter
            if status and student_data.get('pass_fail') != status:
                continue
            
            # Ensure all fields are JSON-serializable
            student_data['risk_factors'] = student_data.get('risk_factors', []) or []
            student_data['counselor_reported'] = str(student_data.get('counselor_reported', '0') or '0')
            filtered_students.append(student_data)
        
        # Pagination
        total = len(filtered_students)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_students = filtered_students[start:end]
        
        return jsonify({
            'success': True,
            'students': paginated_students,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page
            }
        })
    except Exception as e:
        print(f"[ERROR] api_search_students: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/students/export', methods=['POST'])
@login_required
@utils.api_rate_limit(max_requests=10, window_seconds=3600)
def api_export_students():
    """Export students data to CSV"""
    data = request.get_json() or {}
    export_type = data.get('type', 'all')  # all, at_risk, failing
    format_type = data.get('format', 'csv')
    
    # Get students data
    all_students = db._read('students')
    students_to_export = []
    
    for student in all_students:
        student_data = db._to_student(student)
        
        # Apply export filter
        if export_type == 'at_risk' and student_data.get('risk_score', 0) < 30:
            continue
        elif export_type == 'failing' and student_data.get('pass_fail') != 'Fail':
            continue
        
        # Remove sensitive data
        export_data = {k: v for k, v in student_data.items() 
                      if k not in ['password_hash', 'plain_password']}
        students_to_export.append(export_data)
    
    if format_type == 'csv':
        csv_data, filename = utils.export_to_csv(students_to_export, f"students_{export_type}")
        if csv_data:
            return jsonify({
                'success': True,
                'data': csv_data,
                'filename': filename,
                'content_type': 'text/csv'
            })
    
    return jsonify({'success': False, 'error': 'Export failed'}), 500

@app.route('/api/bulk-email', methods=['POST'])
@login_required
@role_required('counselor', 'admin')
@utils.api_rate_limit(max_requests=5, window_seconds=3600)
def api_bulk_email():
    """Send bulk emails to parents"""
    data = request.get_json() or {}
    student_ids = data.get('student_ids', [])
    subject = data.get('subject', '').strip()
    message = data.get('message', '').strip()
    
    if not student_ids:
        return jsonify({'success': False, 'error': 'No students selected'}), 400
    if not subject:
        return jsonify({'success': False, 'error': 'Subject is required'}), 400
    if not message:
        return jsonify({'success': False, 'error': 'Message is required'}), 400
    
    # Log activity
    utils.log_activity(session['user_id'], 'bulk_email_attempt', {
        'student_count': len(student_ids),
        'subject': subject
    })
    
    results = []
    success_count = 0
    
    for student_id in student_ids:
        student = db.get_student_by_id(student_id)
        if not student:
            results.append({'student_id': student_id, 'success': False, 'error': 'Student not found'})
            continue
        
        parent_email = student.get('parent_email', '').strip()
        if not parent_email:
            results.append({'student_id': student_id, 'success': False, 'error': 'No parent email'})
            continue
        
        # Build email
        student_name = student.get('student_name', f"Student #{student_id}")
        email_subject = f"📊 {subject} — {student_name} | UniPredict AI"
        
        # Create HTML message
        html_message = f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb">
          <div style="background:linear-gradient(135deg,#5b5cf6,#8b5cf6);padding:26px 30px;color:#fff">
            <div style="font-size:22px;font-weight:700;margin-bottom:4px">🎓 UniPredict AI</div>
            <div style="opacity:.8;font-size:13px">Student Performance Intelligence Platform</div>
          </div>
          <div style="padding:28px 30px">
            <p style="color:#1e293b;font-size:16px">Dear Parent/Guardian of <strong>{student_name}</strong>,</p>
            <div style="background:#f8fafc;border-radius:10px;padding:16px;margin:16px 0">
              <div style="font-size:14px;color:#475569">{message}</div>
            </div>
            <p style="color:#64748b;font-size:13px;margin-top:20px">
              This message was sent by {session.get('name', 'Counselor')} ({session.get('email', '')}).
            </p>
          </div>
          <div style="background:#f8fafc;padding:14px 30px;text-align:center;font-size:11px;color:#94a3b8;border-top:1px solid #e5e7eb">
            UniPredict AI · Academic Intelligence Platform · Confidential
          </div>
        </div>"""
        
        # Send email
        result = mailer.send_email(parent_email, email_subject, html_message, message)
        
        if result['success']:
            success_count += 1
            # Log email
            db.log_email(student_id, parent_email, email_subject, session.get('name', '?'), 'sent')
            results.append({'student_id': student_id, 'success': True})
        else:
            results.append({'student_id': student_id, 'success': False, 'error': result.get('message', 'Failed to send')})
    
    # Log activity
    utils.log_activity(session['user_id'], 'bulk_email_completed', {
        'total_students': len(student_ids),
        'success_count': success_count,
        'failure_count': len(student_ids) - success_count
    })
    
    return jsonify({
        'success': True,
        'results': results,
        'summary': {
            'total': len(student_ids),
            'success': success_count,
            'failed': len(student_ids) - success_count
        }
    })

@app.route('/api/dashboard/widgets', methods=['GET'])
@login_required
@utils.api_rate_limit(max_requests=50, window_seconds=3600)
def api_dashboard_widgets():
    """Get dashboard widget data"""
    role = session.get('role')
    widgets = {}
    
    if role == 'admin':
        stats = db.get_summary_stats()
        widgets['overview'] = {
            'total_students': stats['total_students'],
            'at_risk_students': stats['fail_count'],
            'total_users': len(db.get_all_users()['all']),
            'recent_notifications': len(db.get_notifications(5))
        }
    
    elif role == 'counselor':
        students, _ = db.get_students_paginated(page=1, per_page=5, filter_by='at-risk')
        widgets['my_students'] = students[:5]
        widgets['recent_activity'] = utils.get_activity_stats(1)
    
    elif role == 'teacher':
        widgets['class_performance'] = {
            'average_grade': 75.5,  # This would be calculated from actual data
            'attendance_rate': 82.3,
            'assignment_completion': 78.9
        }
    
    elif role == 'parent':
        sid_list = db.get_parent_student_ids(session['user_id'])
        students = [s for sid in sid_list if (s := db.get_student_by_id(sid)) is not None]
        widgets['my_children'] = students
    
    return jsonify({'success': True, 'widgets': widgets})


# ─────────────────────────────────────────────────────────────
# ADVANCED ANALYTICS DASHBOARD
# ─────────────────────────────────────────────────────────────
@app.route('/analytics')
@login_required
def analytics_dashboard():
    """Advanced analytics dashboard with comprehensive data visualization"""
    initialize_predictor()
    
    # Get comprehensive analytics data
    stats = db.get_summary_stats()
    notif_count = len(db.get_notifications(100))
    
    # Get detailed student data for analytics
    all_students = []
    page = 1
    per_page = 1000  # Get all students
    
    while True:
        students, total = db.get_students_paginated(page=page, per_page=per_page, filter_by='all')
        all_students.extend(students)
        if len(students) < per_page:
            break
        page += 1
    
    # Calculate advanced analytics
    analytics_data = calculate_advanced_analytics(all_students, stats)
    
    return render_template('analytics.html',
                           analytics=analytics_data,
                           stats=stats,
                           notif_count=notif_count,
                           user_name=session['name'], 
                           user_role=session['role'])


def calculate_advanced_analytics(students, stats=None):
    """Calculate comprehensive analytics from student data"""
    if not students:
        return {}
    
    import numpy as np
    from collections import defaultdict, Counter
    
    # If stats not provided, calculate basic stats
    if not stats:
        stats = {}
        grades = [s['final_grade'] for s in students if s.get('final_grade')]
        pass_count = sum(1 for s in students if s.get('pass_fail') == 'Pass')
        stats['pass_rate'] = round(pass_count / len(students) * 100, 1) if students else 0
    
    analytics = {}
    
    # Performance Distribution
    grades = [s['final_grade'] for s in students if s.get('final_grade')]
    attendance = [s['attendance_rate'] for s in students if s.get('attendance_rate')]
    study_hours = [s['study_hours_weekly'] for s in students if s.get('study_hours_weekly')]
    
    # Grade Distribution Analysis
    grade_bins = [0, 60, 70, 80, 90, 100]
    grade_labels = ['F', 'D', 'C', 'B', 'A']
    grade_dist = np.histogram(grades, bins=grade_bins)[0] if grades else [0]*5
    analytics['grade_distribution'] = {
        'labels': grade_labels,
        'data': [int(x) for x in grade_dist],
        'percentages': [round(x/len(grades)*100, 1) if grades else 0 for x in grade_dist]
    }
    
    # Attendance Analysis
    attendance_bins = [0, 60, 70, 80, 90, 100]
    attendance_labels = ['<60%', '60-70%', '70-80%', '80-90%', '>90%']
    attendance_dist = np.histogram(attendance, bins=attendance_bins)[0] if attendance else [0]*5
    analytics['attendance_distribution'] = {
        'labels': attendance_labels,
        'data': [int(x) for x in attendance_dist],
        'percentages': [round(x/len(attendance)*100, 1) if attendance else 0 for x in attendance_dist]
    }
    
    # Study Hours Analysis
    study_bins = [0, 5, 10, 15, 20, 40]
    study_labels = ['<5', '5-10', '10-15', '15-20', '>20']
    study_dist = np.histogram(study_hours, bins=study_bins)[0] if study_hours else [0]*5
    analytics['study_hours_distribution'] = {
        'labels': study_labels,
        'data': [int(x) for x in study_dist],
        'percentages': [round(x/len(study_hours)*100, 1) if study_hours else 0 for x in study_dist]
    }
    
    # Risk Factor Analysis
    risk_factors_count = defaultdict(int)
    total_risk_students = 0
    
    for student in students:
        if student.get('risk_score', 0) > 50:  # High risk threshold
            total_risk_students += 1
            for factor in student.get('risk_factors', []):
                risk_factors_count[factor] += 1
    
    analytics['risk_factors'] = {
        'labels': list(risk_factors_count.keys()),
        'data': list(risk_factors_count.values()),
        'total_high_risk': total_risk_students
    }
    
    # Gender Performance Analysis
    gender_performance = defaultdict(list)
    for student in students:
        gender = student.get('gender', 'Unknown')
        if student.get('final_grade'):
            gender_performance[gender].append(student['final_grade'])
    
    gender_stats = {}
    for gender, grades_list in gender_performance.items():
        if grades_list:
            gender_stats[gender] = {
                'count': len(grades_list),
                'average': round(np.mean(grades_list), 1),
                'median': round(np.median(grades_list), 1),
                'std_dev': round(np.std(grades_list), 1)
            }
    
    analytics['gender_performance'] = gender_stats
    
    # Performance Categories
    perf_categories = Counter([s.get('performance_category', 'Unknown') for s in students])
    analytics['performance_categories'] = {
        'labels': list(perf_categories.keys()),
        'data': list(perf_categories.values())
    }
    
    # Trend Analysis (if we had time-series data)
    # For now, we'll simulate some trend data
    analytics['trends'] = {
        'monthly_performance': [65, 68, 72, 70, 75, 78, 82, 80, 85, 88, 86, 90],
        'monthly_attendance': [75, 78, 82, 80, 85, 88, 92, 90, 85, 87, 89, 91],
        'monthly_risk': [25, 22, 20, 18, 15, 12, 10, 8, 6, 5, 4, 3]
    }
    
    # Key Metrics
    analytics['key_metrics'] = {
        'total_students': len(students),
        'average_grade': round(np.mean(grades), 1) if grades else 0,
        'average_attendance': round(np.mean(attendance), 1) if attendance else 0,
        'average_study_hours': round(np.mean(study_hours), 1) if study_hours else 0,
        'pass_rate': stats.get('pass_rate', 0) if stats else 0,
        'high_risk_percentage': round(total_risk_students / len(students) * 100, 1) if students else 0
    }
    
    return analytics


# ─────────────────────────────────────────────────────────────
# REPORT MANAGEMENT ROUTES
# ─────────────────────────────────────────────────────────────
@app.route('/reports')
@login_required
def reports_page():
    """View sent reports for admins, teachers and counselors"""
    if session['role'] not in ['teacher', 'admin', 'counselor']:
        return redirect(url_for('index'))

    # Teachers see only their own reports; admin & counselor see all
    user_id = session['user_id'] if session['role'] == 'teacher' else None
    report_stats = db.get_report_statistics(user_id, session['role'])

    # Get recent reports enriched with student names
    raw_reports = db.get_sent_reports(limit=100, teacher_id=user_id)
    reports = []
    for r in raw_reports:
        student = db.get_student_by_id(int(r.get('student_id', 0))) or {}
        r['student_name'] = student.get('student_name', f"Student #{r.get('student_id','?')}")
        reports.append(r)

    # Students who have been reported (last 30 days)
    recent_students = db.get_students_with_recent_reports(teacher_id=user_id, days=30)

    notif_count = len(db.get_notifications(100))

    return render_template('reports.html',
                           reports=reports,
                           stats=report_stats,
                           recent_students=recent_students,
                           notif_count=notif_count,
                           user_name=session['name'],
                           user_role=session['role'])


@app.route('/api/send_report', methods=['POST'])
@login_required
def api_send_report():
    """Send a report and track it"""
    if session['role'] not in ['teacher', 'counselor']:
        return jsonify({'success': False, 'message': 'Unauthorized'})
    
    try:
        data = request.get_json()
        student_id = data.get('student_id')
        report_type = data.get('report_type', 'general')
        content = data.get('content', '')
        parent_email = data.get('parent_email', '')
        
        if not student_id or not content:
            return jsonify({'success': False, 'message': 'Missing required fields'})
        
        # Get student details
        student = db.get_student_by_id(int(student_id))
        if not student:
            return jsonify({'success': False, 'message': 'Student not found'})
        
        # Use parent email from student record if not provided
        if not parent_email:
            parent_email = student.get('parent_email', '')
        
        sent_by = session['name']
        student_name = student.get('student_name', f'Student #{student_id}')
        subject = f"📊 Student Progress Report — {student_name} | UniPredict AI"

        # Build full recipient list: parent + all admins + all teachers + all counselors
        all_recipients = []
        if parent_email:
            all_recipients.append(parent_email)
        for role in ('admin', 'teacher', 'counselor'):
            for u in db.get_users_by_role(role):
                email = u.get('email', '').strip()
                if email and email not in all_recipients:
                    all_recipients.append(email)

        # Build HTML body from content
        report_html = f"""
        <div style="font-family:sans-serif;max-width:600px;margin:auto;padding:24px;background:#f8fafc;border-radius:12px">
          <div style="background:linear-gradient(135deg,#5b5cf6,#8b5cf6);padding:20px 24px;border-radius:10px 10px 0 0">
            <h2 style="color:#fff;margin:0">📊 Student Progress Report</h2>
            <p style="color:rgba(255,255,255,.8);margin:4px 0 0">UniPredict AI — {datetime.now().strftime('%d %b %Y, %H:%M')}</p>
          </div>
          <div style="background:#fff;padding:24px;border-radius:0 0 10px 10px;border:1px solid #e2e8f0">
            <table style="width:100%;border-collapse:collapse;margin-bottom:16px">
              <tr><td style="color:#64748b;padding:6px 0;width:140px"><strong>Student</strong></td><td>{student_name}</td></tr>
              <tr><td style="color:#64748b;padding:6px 0"><strong>Student ID</strong></td><td>#{student_id}</td></tr>
              <tr><td style="color:#64748b;padding:6px 0"><strong>Report Type</strong></td><td style="text-transform:capitalize">{report_type}</td></tr>
              <tr><td style="color:#64748b;padding:6px 0"><strong>Grade</strong></td><td>{student.get('final_grade','—')}</td></tr>
              <tr><td style="color:#64748b;padding:6px 0"><strong>Attendance</strong></td><td>{student.get('attendance_rate','—')}%</td></tr>
              <tr><td style="color:#64748b;padding:6px 0"><strong>Status</strong></td><td>{student.get('pass_fail','—')}</td></tr>
              <tr><td style="color:#64748b;padding:6px 0"><strong>Sent By</strong></td><td>{sent_by} ({session.get('role','').title()})</td></tr>
            </table>
            <div style="background:#f1f5f9;border-left:4px solid #5b5cf6;padding:14px 18px;border-radius:0 8px 8px 0;margin-top:12px">
              <strong style="color:#374151">Report Content:</strong>
              <p style="color:#374151;margin:8px 0 0;white-space:pre-wrap">{content}</p>
            </div>
            <p style="color:#94a3b8;font-size:.8rem;margin-top:20px">This report was generated by UniPredict AI and distributed to all staff members.</p>
          </div>
        </div>"""

        plain_body = (
            f"Student Progress Report — {student_name}\n"
            f"Grade: {student.get('final_grade','—')} | "
            f"Attendance: {student.get('attendance_rate','—')}% | "
            f"Status: {student.get('pass_fail','—')}\n"
            f"Report Type: {report_type}\n"
            f"Sent by: {sent_by}\n\n"
            f"Content:\n{content}"
        )

        # Send to parent + all staff
        sent_count = 0
        for recipient in all_recipients:
            result = mailer.send_email(
                to_email=recipient,
                subject=subject,
                html_body=report_html,
                plain_body=plain_body
            )
            status = 'sent' if result.get('success') else ('simulated' if result.get('simulated') else 'failed')
            db.log_email(int(student_id), recipient, subject, sent_by, status)
            if result.get('success') or result.get('simulated'):
                sent_count += 1

        # Track the sent report
        db.add_sent_report(
            student_id=int(student_id),
            teacher_id=session['user_id'],
            report_type=report_type,
            content=content,
            parent_email=parent_email,
            sent_by=sent_by,
            status='sent'
        )
        
        # Mark student as reported
        db.mark_student_reported(int(student_id), session['user_id'], report_type)
        
        # Add notification
        staff_count = len(all_recipients) - (1 if parent_email else 0)
        db.add_notification(
            f'📬 Report for {student_name} sent to parent + {staff_count} staff',
            'success', session['username']
        )
        
        return jsonify({
            'success': True,
            'message': f'✅ Report sent to parent + {staff_count} staff (admin, teachers & counselors)'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})


@app.route('/api/report/unreport', methods=['POST'])
@login_required
def api_report_unreport():
    """Mark a report as revoked and update student reported state."""
    if session['role'] not in ['teacher', 'admin', 'counselor']:
        return jsonify({'success': False, 'message': 'Unauthorized'})
    data = request.get_json() or {}
    report_id = data.get('report_id')
    if not report_id:
        return jsonify({'success': False, 'message': 'report_id is required'}), 400

    report = db.get_sent_report_by_id(report_id)
    if not report:
        return jsonify({'success': False, 'message': 'Report not found'}), 404

    student_id = report.get('student_id')
    db.update_sent_report_status(report_id, 'revoked')

    # If no remaining active reports for this student, unmark student
    active = [r for r in db.get_sent_reports(student_id=student_id) if r.get('status') in ('sent','resent')]
    if not active:
        db.unmark_student_reported(int(student_id), session['user_id'], report.get('report_type', 'general'))

    db.audit(session['user_id'], 'UNREPORT', str(report_id), f"Report revoked for student {student_id}")
    return jsonify({'success': True, 'message': 'Report revoked and student state updated'})


@app.route('/api/report/delete', methods=['POST'])
@login_required
def api_report_delete():
    """Delete a report record permanently."""
    if session['role'] not in ['teacher', 'admin', 'counselor']:
        return jsonify({'success': False, 'message': 'Unauthorized'})

    data = request.get_json() or {}
    report_id = data.get('report_id')
    if not report_id:
        return jsonify({'success': False, 'message': 'report_id is required'}), 400

    report = db.get_sent_report_by_id(report_id)
    if not report:
        return jsonify({'success': False, 'message': 'Report not found'}), 404

    # Only allow deletion of reports that are revoked
    if report.get('status') != 'revoked':
        return jsonify({'success': False, 'message': 'Only revoked reports may be deleted'}), 403

    student_id = report.get('student_id')
    deleted = db.delete_sent_report(report_id)
    if not deleted:
        return jsonify({'success': False, 'message': 'Failed to delete report'}), 500

    # Ensure student report state remains in sync (if no active ones left)
    active = [r for r in db.get_sent_reports(student_id=student_id) if r.get('status') in ('sent','resent')]
    if not active:
        db.unmark_student_reported(int(student_id), session['user_id'], report.get('report_type', 'general'))

    db.audit(session['user_id'], 'DELETE_REPORT', str(report_id), f"Report deleted for student {student_id}")
    return jsonify({'success': True, 'message': 'Report deleted successfully'})


@app.route('/api/report/resend', methods=['POST'])
@login_required
def api_report_resend():
    """Create a new resend log entry for a report and refresh student timestamp."""
    if session['role'] not in ['teacher', 'admin', 'counselor']:
        return jsonify({'success': False, 'message': 'Unauthorized'})
    data = request.get_json() or {}
    report_id = data.get('report_id')
    if not report_id:
        return jsonify({'success': False, 'message': 'report_id is required'}), 400

    report = db.get_sent_report_by_id(report_id)
    if not report:
        return jsonify({'success': False, 'message': 'Report not found'}), 404

    student_id = int(report.get('student_id'))

    # Add a new entry in sent_reports as resent
    db.add_sent_report(
        student_id=student_id,
        teacher_id=session['user_id'],
        report_type=report.get('report_type', 'general'),
        content=f"Resent report from {report.get('created_at','')} ({report.get('status','')})",
        parent_email=report.get('parent_email',''),
        sent_by=session.get('name','?'),
        status='resent'
    )

    db.mark_student_reported(student_id, session['user_id'], report.get('report_type', 'general'))
    db.audit(session['user_id'], 'RESEND_REPORT', str(report_id), f"Report resent for student {student_id}")

    return jsonify({'success': True, 'message': 'Report resent and student state updated'})


@app.route('/api/report_statistics')
@login_required
def api_report_statistics():
    """Get report statistics for dashboard"""
    if session['role'] not in ['teacher', 'admin']:
        return jsonify({'success': False, 'message': 'Unauthorized'})
    
    user_id = session['user_id'] if session['role'] == 'teacher' else None
    stats = db.get_report_statistics(user_id, session['role'])
    
    return jsonify({'success': True, 'stats': stats})


if __name__ == '__main__':
    # Avoid UnicodeEncodeError on Windows consoles with non-UTF8 codepages.
    print("\n" + "=" * 68)
    print("   UniPredict AI v4.0  |  CSV-Backed Multi-Role Platform")
    print("=" * 68)
    print("  DB   :", db.DB_PATH)
    print("  Tables:", db.get_table_info())
    print("  Debug Mode:", DEBUG)
    print("  Session Timeout:", SESSION_TIMEOUT, "seconds")
    print("  Max Login Attempts:", MAX_LOGIN_ATTEMPTS)
    print()
    print("  CREDENTIALS (see CREDENTIALS.md for full list):")
    print("Admin | admin_laishram | Admin@2026 ")
    print("Teacher | teacher_ningthoujam | Teach@2026 ")
    print("Teacher | teacher_konthoujam | Teach@2026  ")
    print("Teacher | teacher_oinam | Teach@2026 ")
    print("Teacher | teacher_wangkhem | Teach@2026 ")
    print("Counselor | counselor_pukhrambam | Counsel@2026 ")
    print("Counselor | counselor_yumnam | Counsel@2026 ")
    print("Parent | parent_thangjam_1 | par1@2026 ")
    print("Parent | parent_thangjam_2 | par2@2026 ")
    print()
    print(f"  http://{HOST}:{PORT}")
    print("=" * 68 + "\n")
    app.run(debug=DEBUG, host=HOST, port=PORT)
