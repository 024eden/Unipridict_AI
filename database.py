"""
UniPredict AI — CSV Database Layer
Replaces MySQL/PyMySQL with flat CSV files stored in the `data/` folder.
All public function signatures are identical to the original MySQL version.
"""
import csv, hashlib, os, re, threading
from datetime import datetime, timedelta
from contextlib import contextmanager

# ─────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_DIR  = os.path.join(BASE_DIR, 'data')
DB_PATH   = DATA_DIR          # compatibility shim — points to the data/ folder
os.makedirs(DATA_DIR, exist_ok=True)

_TABLES = {
    'users':          ['id','username','password_hash','name','email','phone','role','subject','created_at','is_active','plain_password'],
    # NOTE: parent fields are stored with the student record for report emailing.
    'students':       ['student_id','student_name','parent_name','parent_email','address',
                       'gender','age','attendance_rate','study_hours_weekly',
                       'previous_grades','assignment_completion','class_participation','extra_curricular',
                       'library_visits','online_resource_hours','parent_education','family_income',
                       'internet_access','tutoring','mentor_support','stress_level','motivation_score',
                       'final_grade','performance_category','pass_fail','last_reported_at','reported_by','counselor_reported','added_by','created_at','updated_at'],
    'parent_students':['parent_id','student_id'],
    'notifications':  ['id','message','level','username','created_at'],
    'email_logs':     ['id','student_id','to_email','subject','sent_by','status','created_at'],
    'sent_reports':   ['id','student_id','teacher_id','report_type','content','parent_email','sent_by','status','created_at'],
    'audit_log':      ['id','user_id','action','target','detail','created_at'],
}

_LOCKS = {t: threading.Lock() for t in _TABLES}


def _path(table: str) -> str:
    return os.path.join(DATA_DIR, f"{table}.csv")


# ─────────────────────────────────────────────────────────────
# LOW-LEVEL CSV HELPERS
# ─────────────────────────────────────────────────────────────
def _read(table: str) -> list[dict]:
    p = _path(table)
    if not os.path.exists(p):
        return []
    with open(p, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def _write(table: str, rows: list[dict]):
    p = _path(table)
    cols = _TABLES[table]
    with open(p, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def _next_int_id(table: str, id_col: str = 'id') -> int:
    rows = _read(table)
    ids = [int(r[id_col]) for r in rows if r.get(id_col, '').lstrip('-').isdigit()]
    return max(ids) + 1 if ids else 1


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# ─────────────────────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────────────────────
def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


# ─────────────────────────────────────────────────────────────
# SEED DATA  (mirrors original SEED_USERS / PARENT_LINKS)
# ─────────────────────────────────────────────────────────────
SEED_USERS = [
    dict(id='ADM001', username='admin_laishram',       password='Admin@2026',      name='Dr. Laishram Ibohal Singh',      email='laishram.ibohal@university.edu',   phone='+91-9856001001', role='admin'),
    dict(id='ADM002', username='admin_thounaojam',     password='Admin@2026',      name='Dr. Thounaojam Sunil Singh',     email='thounaojam.sunil@university.edu',  phone='+91-9856001002', role='admin'),
    dict(id='TCH001', username='teacher_ningthoujam',  password='Teach@2026',      name='Mr. Ningthoujam Ranjit Singh',   email='ningthoujam.ranjit@university.edu',phone='+91-9856002001', role='teacher',   subject='Mathematics'),
    dict(id='TCH002', username='teacher_konthoujam',   password='Teach@2026',      name='Ms. Konthoujam Sunita Devi',     email='konthoujam.sunita@university.edu', phone='+91-9856002002', role='teacher',   subject='Science'),
    dict(id='TCH003', username='teacher_oinam',        password='Teach@2026',      name='Mr. Oinam Biren Singh',          email='oinam.biren@university.edu',       phone='+91-9856002003', role='teacher',   subject='English'),
    dict(id='TCH004', username='teacher_wangkhem',     password='Teach@2026',      name='Ms. Wangkhem Sanatombi Devi',    email='wangkhem.sanatombi@university.edu',phone='+91-9856002004', role='teacher',   subject='History'),
    dict(id='CSL001', username='counselor_pukhrambam', password='Counsel@2026',    name='Ms. Pukhrambam Ibemhal Devi',    email='pukhrambam.ibemhal@university.edu',phone='+91-9856003001', role='counselor'),
    dict(id='CSL002', username='counselor_yumnam',     password='Counsel@2026',    name='Mr. Yumnam Sanajaoba Singh',     email='yumnam.sanajaoba@university.edu',  phone='+91-9856003002', role='counselor'),
    dict(id='PAR001', username='parent_thangjam_1',    password='par1@2026',       name='Mr. Thangjam Ibohal',            email='thangjam.ibohal@gmail.com',        phone='+91-9856004001', role='parent'),
    dict(id='PAR002', username='parent_thangjam_2',    password='par2@2026',       name='Mrs. Thangjam Sanalembi',        email='thangjam.sanalembi@gmail.com',     phone='+91-9856004002', role='parent'),
]

PARENT_LINKS = [('PAR001', 1), ('PAR001', 2), ('PAR002', 3), ('PAR002', 4)]


# ─────────────────────────────────────────────────────────────
# INIT
# ─────────────────────────────────────────────────────────────
def init_db():
    """Create CSV files and seed initial data if empty."""
    # Ensure all CSV files exist
    for table, cols in _TABLES.items():
        p = _path(table)
        if not os.path.exists(p):
            with open(p, 'w', newline='', encoding='utf-8') as f:
                csv.DictWriter(f, fieldnames=cols).writeheader()
        else:
            _ensure_table_schema(table)

    # Seed users
    with _LOCKS['users']:
        users = _read('users')
        if not users:
            now = _now()
            rows = []
            for u in SEED_USERS:
                rows.append({
                    'id': u['id'], 'username': u['username'],
                    'password_hash': hash_pw(u['password']),
                    'name': u['name'], 'email': u['email'],
                    'phone': u.get('phone', ''), 'role': u['role'],
                    'subject': u.get('subject', ''),
                    'created_at': now, 'is_active': '1',
                })
            _write('users', rows)
            add_notification('Database initialised with seed users', 'success', 'system')

    # Seed parent links
    with _LOCKS['parent_students']:
        ps = _read('parent_students')
        if not ps:
            _write('parent_students', [{'parent_id': pid, 'student_id': sid} for pid, sid in PARENT_LINKS])

    # Seed students from CSV
    _seed_students_from_csv()
    print("[DB] CSV backend ready.")


def _ensure_table_schema(table: str):
    """
    Ensure existing CSV header matches current schema (adds missing columns).
    Keeps existing rows and fills new columns with ''.
    """
    p = _path(table)
    if not os.path.exists(p):
        return
    expected = _TABLES[table]
    try:
        with open(p, newline='', encoding='utf-8') as f:
            r = csv.reader(f)
            header = next(r, None) or []
    except Exception:
        header = []
    if not header:
        # Empty or unreadable file — rewrite header
        with open(p, 'w', newline='', encoding='utf-8') as f:
            csv.DictWriter(f, fieldnames=expected).writeheader()
        return
    if header == expected:
        return

    # Read existing rows with current header, then rewrite with expected header.
    rows = _read(table)
    fixed = []
    for row in rows:
        out = {k: row.get(k, '') for k in expected}
        fixed.append(out)
    _write(table, fixed)


def _seed_students_from_csv():
    import pandas as pd
    csv_path = os.path.join(BASE_DIR, 'student_dataset.csv')
    if not os.path.exists(csv_path):
        return
    with _LOCKS['students']:
        if _read('students'):
            return
        df = pd.read_csv(csv_path)
        if 'student_name' not in df.columns:
            df['student_name'] = 'Unknown Student'
        now = _now()
        cols = ['student_name','gender','age','attendance_rate','study_hours_weekly','previous_grades',
                'assignment_completion','class_participation','extra_curricular','library_visits',
                'online_resource_hours','parent_education','family_income','internet_access',
                'tutoring','mentor_support','stress_level','motivation_score','final_grade',
                'performance_category','pass_fail']
        rows = []
        for i, (_, row) in enumerate(df.iterrows(), 1):
            r = {'student_id': str(i), 'added_by': '', 'created_at': now, 'updated_at': now}
            # Optional parent fields (not present in the dataset) — keep blank by default.
            r['parent_name'] = ''
            r['parent_email'] = ''
            r['address'] = ''
            for c in cols:
                r[c] = str(row.get(c, ''))
            rows.append(r)
        _write('students', rows)
    print(f"[DB] Seeded {len(rows)} students from CSV")


# ─────────────────────────────────────────────────────────────
# USER OPERATIONS
# ─────────────────────────────────────────────────────────────
def get_user_by_username(username: str):
    for r in _read('users'):
        if r['username'] == username and r.get('is_active', '1') == '1':
            return r
    return None


def get_user_by_id(uid: str):
    for r in _read('users'):
        if r['id'] == uid:
            return r
    return None


def get_users_by_role(role: str):
    return [r for r in _read('users') if r['role'] == role]


def get_all_users():
    result = {'admins': [], 'teachers': [], 'counselors': [], 'parents': []}
    for r in _read('users'):
        key = r['role'] + 's'
        if key in result:
            result[key].append(r)
    return result


def add_user(user_id, username, password, name, email, phone, role, subject=None):
    with _LOCKS['users']:
        rows = _read('users')
        row = {
            'id': user_id, 'username': username,
            'password_hash': hash_pw(password),
            'name': name, 'email': email, 'phone': phone or '',
            'role': role, 'subject': subject or '',
            'created_at': _now(), 'is_active': '1',
            'plain_password': password if role == 'parent' else '',
        }
        rows.append(row)
        _write('users', rows)


def delete_user(user_id: str):
    with _LOCKS['users']:
        rows = _read('users')
        for r in rows:
            if r['id'] == user_id:
                r['is_active'] = '0'
        _write('users', rows)


def get_parent_student_ids(parent_id: str):
    return [int(r['student_id']) for r in _read('parent_students') if str(r['parent_id']) == str(parent_id)]


def get_all_parents_with_passwords():
    """Return list of parent users that have email and plain_password set."""
    return [
        r for r in _read('users')
        if r.get('role') == 'parent'
        and r.get('email', '').strip()
        and r.get('plain_password', '').strip()
        and r.get('is_active', '1') == '1'
    ]


def link_parent_student(parent_id: str, student_id: int):
    with _LOCKS['parent_students']:
        rows = _read('parent_students')
        if not any(r['parent_id'] == parent_id and str(r['student_id']) == str(student_id) for r in rows):
            rows.append({'parent_id': parent_id, 'student_id': str(student_id)})
            _write('parent_students', rows)


def next_user_id(role: str) -> str:
    prefix = {'admin': 'ADM', 'teacher': 'TCH', 'counselor': 'CSL', 'parent': 'PAR'}[role]
    nums = []
    for r in _read('users'):
        if r['role'] == role:
            m = re.search(r'(\d+)$', r['id'])
            if m:
                nums.append(int(m.group(1)))
    n = max(nums) + 1 if nums else 1
    return f"{prefix}{n:03d}"


# ─────────────────────────────────────────────────────────────
# STUDENT OPERATIONS
# ─────────────────────────────────────────────────────────────
def _calc_risk(row: dict):
    score = 0
    factors = []
    def flt(k, default): 
        try: return float(row.get(k) or default)
        except: return default
    if flt('attendance_rate', 100) < 75:       score += 30; factors.append('Low Attendance')
    if flt('study_hours_weekly', 10) < 10:     score += 20; factors.append('Low Study Hours')
    if flt('assignment_completion', 100) < 70: score += 25; factors.append('Incomplete Assignments')
    if flt('stress_level', 0) > 7:             score += 20; factors.append('High Stress')
    if flt('motivation_score', 10) < 5:        score += 15; factors.append('Low Motivation')
    if flt('previous_grades', 100) < 60:       score += 25; factors.append('Poor Academic History')
    return min(score, 100), factors


def _to_student(r: dict) -> dict:
    """Cast numeric string fields back to numbers and add risk info."""
    int_fields   = {'student_id','age','library_visits'}
    float_fields = {'attendance_rate','study_hours_weekly','previous_grades','assignment_completion',
                    'class_participation','online_resource_hours','stress_level','motivation_score','final_grade'}
    out = dict(r)
    for k in int_fields:
        try: out[k] = int(r[k])
        except: pass
    for k in float_fields:
        try: out[k] = float(r[k])
        except: pass
    # Ensure student_name is never empty — fall back to Student #ID
    if not out.get('student_name') or str(out.get('student_name','')).strip().lower() in ('', 'unknown student', 'unknown'):
        out['student_name'] = f"Student #{out.get('student_id', '?')}"
    # Pass through parent_name, parent_email and address safely
    out['parent_name'] = out.get('parent_name', '') or ''
    out['parent_email'] = out.get('parent_email', '') or ''
    out['address'] = out.get('address', '') or ''
    out['risk_score'], out['risk_factors'] = _calc_risk(out)
    return out


def get_student_by_id(sid: int):
    for r in _read('students'):
        if str(r['student_id']) == str(sid):
            return _to_student(r)
    return None


def get_students_paginated(page=1, per_page=25, filter_by='all'):
    rows = _read('students')
    if filter_by == 'at-risk':
        rows = [r for r in rows if r.get('pass_fail') == 'Fail']
    elif filter_by == 'passing':
        rows = [r for r in rows if r.get('pass_fail') == 'Pass']
    total = len(rows)
    offset = (page - 1) * per_page
    page_rows = rows[offset:offset + per_page]
    return [_to_student(r) for r in page_rows], total


def find_duplicate_student(name: str, gender: str = None, age: str = None) -> dict:
    """Check if a student with same name (and optionally same gender+age) already exists."""
    name = name.strip().lower()
    for r in _read('students'):
        if r.get('student_name', '').strip().lower() == name:
            # Extra check: if gender and age also match, it's almost certainly a duplicate
            if gender and age:
                if r.get('gender', '').lower() == gender.lower() and str(r.get('age', '')) == str(age):
                    return r
            else:
                return r
    return None


def add_student(data: dict, added_by: str = None):
    with _LOCKS['students']:
        rows = _read('students')
        new_id = max((int(r['student_id']) for r in rows if str(r.get('student_id','')).isdigit()), default=0) + 1
        now = _now()
        cols = ['student_name','parent_name','parent_email','address','gender','age','attendance_rate','study_hours_weekly',
                'previous_grades','assignment_completion','class_participation',
                'extra_curricular','library_visits','online_resource_hours',
                'parent_education','family_income','internet_access',
                'tutoring','mentor_support','stress_level','motivation_score',
                'final_grade','performance_category','pass_fail']
        row = {'student_id': str(new_id), 'added_by': added_by or '', 'created_at': now, 'updated_at': now}
        for c in cols:
            row[c] = str(data.get(c, ''))
        rows.append(row)
        _write('students', rows)
        return new_id


def update_student(sid: int, data: dict):
    allowed = {'student_name','attendance_rate','study_hours_weekly','assignment_completion',
               'class_participation','stress_level','motivation_score','tutoring',
               'mentor_support','final_grade','performance_category','pass_fail','previous_grades'}
    with _LOCKS['students']:
        rows = _read('students')
        for r in rows:
            if str(r['student_id']) == str(sid):
                for k, v in data.items():
                    if k in allowed:
                        r[k] = str(v)
                r['updated_at'] = _now()
        _write('students', rows)


def delete_student(sid: int):
    with _LOCKS['students']:
        rows = _read('students')
        rows = [r for r in rows if str(r['student_id']) != str(sid)]
        _write('students', rows)


def get_summary_stats():
    rows = _read('students')
    total = len(rows)
    if total == 0:
        return {'total_students':0,'pass_count':0,'fail_count':0,'pass_rate':0,
                'avg_grade':0,'avg_attendance':0,'avg_study_hours':0,'performance_categories':{}}
    pass_cnt  = sum(1 for r in rows if r.get('pass_fail') == 'Pass')
    fail_cnt  = sum(1 for r in rows if r.get('pass_fail') == 'Fail')
    def avg(key):
        vals = []
        for r in rows:
            try: vals.append(float(r[key]))
            except: pass
        return sum(vals)/len(vals) if vals else 0
    cats = {}
    for r in rows:
        c = r.get('performance_category','Unknown')
        cats[c] = cats.get(c, 0) + 1
    return {
        'total_students': total,
        'pass_count': pass_cnt,
        'fail_count': fail_cnt,
        'pass_rate': round(pass_cnt / total * 100, 1),
        'avg_grade': round(avg('final_grade'), 1),
        'avg_attendance': round(avg('attendance_rate'), 1),
        'avg_study_hours': round(avg('study_hours_weekly'), 1),
        'performance_categories': cats,
    }


# ─────────────────────────────────────────────────────────────
# NOTIFICATIONS
# ─────────────────────────────────────────────────────────────
def add_notification(message: str, level: str = 'info', username: str = 'system'):
    with _LOCKS['notifications']:
        rows = _read('notifications')
        new_id = max((int(r['id']) for r in rows if str(r.get('id','')).isdigit()), default=0) + 1
        rows.append({'id': str(new_id), 'message': message, 'level': level,
                     'username': username, 'created_at': _now()})
        _write('notifications', rows)


def get_notifications(limit: int = 50):
    rows = _read('notifications')
    rows.sort(key=lambda r: int(r.get('id', 0) or 0), reverse=True)
    return rows[:limit]


def clear_notifications():
    with _LOCKS['notifications']:
        _write('notifications', [])


# ─────────────────────────────────────────────────────────────
# EMAIL LOGS
# ─────────────────────────────────────────────────────────────
def log_email(student_id: int, to_email: str, subject: str, sent_by: str, status='simulated'):
    with _LOCKS['email_logs']:
        rows = _read('email_logs')
        new_id = max((int(r['id']) for r in rows if str(r.get('id','')).isdigit()), default=0) + 1
        rows.append({'id': str(new_id), 'student_id': str(student_id), 'to_email': to_email,
                     'subject': subject, 'sent_by': sent_by, 'status': status, 'created_at': _now()})
        _write('email_logs', rows)


def get_email_logs(limit: int = 100):
    rows = _read('email_logs')
    rows.sort(key=lambda r: int(r.get('id', 0) or 0), reverse=True)
    return rows[:limit]


# ─────────────────────────────────────────────────────────────
# AUDIT LOG
# ─────────────────────────────────────────────────────────────
def audit(user_id: str, action: str, target: str = None, detail: str = None):
    with _LOCKS['audit_log']:
        rows = _read('audit_log')
        new_id = max((int(r['id']) for r in rows if str(r.get('id','')).isdigit()), default=0) + 1
        rows.append({'id': str(new_id), 'user_id': user_id or '', 'action': action,
                     'target': target or '', 'detail': detail or '', 'created_at': _now()})
        _write('audit_log', rows)


def get_audit_log(limit: int = 200):
    rows = _read('audit_log')
    rows.sort(key=lambda r: int(r.get('id', 0) or 0), reverse=True)
    return rows[:limit]


# ─────────────────────────────────────────────────────────────
# ADMIN HELPERS
# ─────────────────────────────────────────────────────────────
def get_table_info():
    tables = ['users','students','notifications','email_logs','audit_log','parent_students']
    return {t: len(_read(t)) for t in tables}


def run_safe_query(sql: str):
    """Read-only SELECT executed in-memory (SQLite)."""
    sql = sql.strip()
    if not sql.upper().startswith('SELECT'):
        raise ValueError("Only SELECT queries are allowed")
    import sqlite3

    def _quote_ident(name: str) -> str:
        # SQLite identifier quoting
        return '"' + name.replace('"', '""') + '"'

    con = sqlite3.connect(':memory:')
    try:
        cur = con.cursor()
        # Create tables (all columns as TEXT for simplicity)
        for table, cols in _TABLES.items():
            col_defs = ', '.join(f'{_quote_ident(c)} TEXT' for c in cols)
            cur.execute(f'CREATE TABLE {_quote_ident(table)} ({col_defs});')
            rows = _read(table)
            if not rows:
                continue
            ins_cols = cols
            ph = ','.join(['?'] * len(ins_cols))
            cur.executemany(
                f'INSERT INTO {_quote_ident(table)} ({",".join(_quote_ident(c) for c in ins_cols)}) VALUES ({ph});',
                [[r.get(c, '') for c in ins_cols] for r in rows]
            )
        con.commit()

        cur.execute(sql)
        fetched = cur.fetchmany(200)
        cols = [d[0] for d in (cur.description or [])]
        return cols, [list(r) for r in fetched]
    finally:
        try:
            con.close()
        except Exception:
            pass


def truncate_and_reseed_students(csv_path: str):
    """Truncate students + parent_students CSVs and re-import from CSV (admin use)."""
    import pandas as pd
    df = pd.read_csv(csv_path)
    if 'student_name' not in df.columns:
        df['student_name'] = 'Unknown Student'
    cols = ['student_name','gender','age','attendance_rate','study_hours_weekly','previous_grades',
            'assignment_completion','class_participation','extra_curricular','library_visits',
            'online_resource_hours','parent_education','family_income','internet_access',
            'tutoring','mentor_support','stress_level','motivation_score','final_grade',
            'performance_category','pass_fail']
    now = _now()
    with _LOCKS['students']:
        rows = []
        for i, (_, row) in enumerate(df.iterrows(), 1):
            r = {'student_id': str(i), 'added_by': '', 'created_at': now, 'updated_at': now}
            for c in cols:
                r[c] = str(row.get(c, ''))
            rows.append(r)
        _write('students', rows)
    with _LOCKS['parent_students']:
        _write('parent_students', [{'parent_id': pid, 'student_id': str(sid)} for pid, sid in PARENT_LINKS])
    print(f"[DB] Reseeded {len(rows)} students from {csv_path}")


# ── Password Reset Token Store (in-memory, TTL 1 hour) ─────────────────────
import secrets, time as _time
_RESET_TOKENS = {}   # token -> {'user_id': str, 'expires': float}
_TOKEN_TTL = 3600    # 1 hour

def create_reset_token(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    _RESET_TOKENS[token] = {'user_id': user_id, 'expires': _time.time() + _TOKEN_TTL}
    # Clean up expired tokens
    expired = [t for t, v in _RESET_TOKENS.items() if v['expires'] < _time.time()]
    for t in expired:
        _RESET_TOKENS.pop(t, None)
    return token

def get_token_user(token: str):
    entry = _RESET_TOKENS.get(token)
    if not entry:
        return None
    if entry['expires'] < _time.time():
        _RESET_TOKENS.pop(token, None)
        return None
    return entry['user_id']

def consume_reset_token(token: str):
    _RESET_TOKENS.pop(token, None)

def get_user_by_email(email: str):
    email = email.strip().lower()
    for r in _read('users'):
        if r.get('email', '').strip().lower() == email and r.get('is_active', '1') == '1':
            return r
    return None

def update_user_password(user_id: str, new_password: str):
    with _LOCKS['users']:
        rows = _read('users')
        for r in rows:
            if r['id'] == user_id:
                r['password_hash'] = hash_pw(new_password)
                r['plain_password'] = new_password if r.get('role') == 'parent' else ''
                break
        _write('users', rows)


def get_parent_emails_for_student(student_id: int) -> list[str]:
    """
    Return unique parent emails linked to a student via parent_students + users.
    """
    sid = str(student_id)
    parent_ids = [r.get('parent_id', '') for r in _read('parent_students') if str(r.get('student_id', '')) == sid]
    if not parent_ids:
        return []
    users = _read('users')
    emails = []
    for pid in parent_ids:
        for u in users:
            if u.get('id') == pid:
                em = (u.get('email') or '').strip()
                if em:
                    emails.append(em)
                break
    # Unique, stable order
    out = []
    seen = set()
    for e in emails:
        if e.lower() in seen:
            continue
        seen.add(e.lower())
        out.append(e)
    return out


# ─────────────────────────────────────────────────────────────
# SENT REPORTS MANAGEMENT
# ─────────────────────────────────────────────────────────────
def add_sent_report(student_id: int, teacher_id: str, report_type: str, content: str, 
                  parent_email: str, sent_by: str, status: str = 'sent'):
    """Add a record of sent report"""
    with _LOCKS['sent_reports']:
        rows = _read('sent_reports')
        new_id = max((int(r['id']) for r in rows if str(r.get('id','')).isdigit()), default=0) + 1
        rows.append({
            'id': str(new_id),
            'student_id': str(student_id),
            'teacher_id': teacher_id,
            'report_type': report_type,
            'content': content,
            'parent_email': parent_email,
            'sent_by': sent_by,
            'status': status,
            'created_at': _now()
        })
        _write('sent_reports', rows)
        return new_id


def get_sent_reports(limit: int = 100, teacher_id: str = None, student_id: int = None):
    """Get sent reports with optional filtering"""
    rows = _read('sent_reports')
    
    # Apply filters
    if teacher_id:
        rows = [r for r in rows if r.get('teacher_id') == teacher_id]
    if student_id:
        rows = [r for r in rows if str(r.get('student_id')) == str(student_id)]
    
    # Sort by created_at descending
    rows.sort(key=lambda r: r.get('created_at', ''), reverse=True)
    return rows[:limit]


def get_report_statistics(user_id: str = None, role: str = None):
    """Get statistics about sent reports"""
    rows = _read('sent_reports')
    
    # Filter by user if provided
    if user_id and role == 'teacher':
        rows = [r for r in rows if r.get('teacher_id') == user_id]
    
    total_reports = len(rows)
    reports_by_type = {}
    reports_by_status = {}
    recent_reports = 0
    
    for r in rows:
        # Count by type
        report_type = r.get('report_type', 'Unknown')
        reports_by_type[report_type] = reports_by_type.get(report_type, 0) + 1
        
        # Count by status
        status = r.get('status', 'Unknown')
        reports_by_status[status] = reports_by_status.get(status, 0) + 1
        
        # Count recent (last 7 days)
        try:
            created_date = datetime.strptime(r.get('created_at', ''), '%Y-%m-%d %H:%M:%S')
            if created_date >= datetime.now() - timedelta(days=7):
                recent_reports += 1
        except:
            pass

    sent_successful = reports_by_status.get('sent', 0) + reports_by_status.get('resent', 0)

    return {
        'total_reports': total_reports,
        'reports_by_type': reports_by_type,
        'reports_by_status': reports_by_status,
        'recent_reports': recent_reports,
        'sent_successful': sent_successful
    }


def mark_student_reported(student_id: int, teacher_id: str, report_type: str = 'general'):
    """Mark a student as reported (for tracking)"""
    student = get_student_by_id(student_id)
    if student:
        with _LOCKS['students']:
            rows = _read('students')
            for r in rows:
                if str(r.get('student_id', '')) == str(student_id):
                    r['last_reported_at'] = _now()
                    r['reported_by'] = teacher_id
                    break
            _write('students', rows)
        audit(teacher_id, f'mark_student_reported', f'student_{student_id}', 
              f'Marked student {student["student_name"]} as reported: {report_type}')


def unmark_student_reported(student_id: int, teacher_id: str, report_type: str = 'general'):
    """Unmark a student as reported when a report is revoked."""
    student = get_student_by_id(student_id)
    if student:
        with _LOCKS['students']:
            rows = _read('students')
            for r in rows:
                if str(r.get('student_id', '')) == str(student_id):
                    r['last_reported_at'] = ''
                    r['reported_by'] = ''
                    break
            _write('students', rows)
        audit(teacher_id, f'unmark_student_reported', f'student_{student_id}',
              f'Unmarked student {student["student_name"]} as reported: {report_type}')


def set_counselor_reported(student_id: int, reported: bool, user_id: str):
    """Set a counselor-specific report completion marker at student level."""
    with _LOCKS['students']:
        rows = _read('students')
        for r in rows:
            if str(r.get('student_id', '')) == str(student_id):
                r['counselor_reported'] = '1' if reported else '0'
                break
        _write('students', rows)
    audit(user_id, 'SET_COUNSELOR_REPORTED', f'student_{student_id}',
          f"Counselor reported toggled to {reported} for student {student_id}")


def update_sent_report_status(report_id: int, status: str):
    """Update the status of a sent report."""
    with _LOCKS['sent_reports']:
        rows = _read('sent_reports')
        for r in rows:
            if str(r.get('id','')) == str(report_id):
                r['status'] = status
                break
        _write('sent_reports', rows)


def get_sent_report_by_id(report_id: int):
    """Return a single sent report by id."""
    rows = _read('sent_reports')
    for r in rows:
        if str(r.get('id','')) == str(report_id):
            return r
    return None


def delete_sent_report(report_id: int) -> bool:
    """Delete a sent report record permanently."""
    with _LOCKS['sent_reports']:
        rows = _read('sent_reports')
        filtered = [r for r in rows if str(r.get('id','')) != str(report_id)]
        if len(filtered) == len(rows):
            return False
        _write('sent_reports', filtered)
        return True


def get_reported_student_ids() -> set:
    """Return a set of student_id strings that have successful or resent reports."""
    rows = _read('sent_reports')
    return {str(r.get('student_id', '')) for r in rows
            if r.get('student_id') and r.get('status') in ('sent', 'resent')}


def get_students_with_recent_reports(teacher_id: str = None, days: int = 30):
    """Get students who have received recent reports"""
    rows = _read('sent_reports')
    
    # Filter by teacher if provided
    if teacher_id:
        rows = [r for r in rows if r.get('teacher_id') == teacher_id]
    
    # Get recent reports
    cutoff_date = datetime.now() - timedelta(days=days)
    recent_student_ids = set()
    
    for r in rows:
        try:
            created_date = datetime.strptime(r.get('created_at', ''), '%Y-%m-%d %H:%M:%S')
            if created_date >= cutoff_date:
                recent_student_ids.add(r.get('student_id'))
        except:
            pass
    
    # Get student details
    students = []
    for student_id in recent_student_ids:
        student = get_student_by_id(int(student_id))
        if student:
            students.append(student)
    
    return students
