from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from flask_wtf.csrf import validate_csrf, ValidationError
from functools import wraps
from db import query, execute
import bcrypt, time
from collections import defaultdict
import threading

employee_bp = Blueprint('employee', __name__, url_prefix='/employee')

_login_attempts = defaultdict(list)
_lock = threading.Lock()

# Role hierarchy
ROLE_LEVEL = {
    'Consultant':     1,
    'Stylist':        1,
    'Senior Stylist': 2,
    'Manager':        3,
}

def _role_level():
    return ROLE_LEVEL.get(session.get('emp_role', ''), 1)

def _rate_limited(ip, window=300, limit=10):
    now = time.time()
    with _lock:
        attempts = [t for t in _login_attempts[ip] if now - t < window]
        _login_attempts[ip] = attempts
        if len(attempts) >= limit:
            return True
        _login_attempts[ip].append(now)
    return False


def emp_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'emp_id' not in session:
            return redirect(url_for('employee.login'))
        return f(*args, **kwargs)
    return decorated


def manager_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'emp_id' not in session:
            return redirect(url_for('employee.login'))
        if _role_level() < 3:
            flash('Manager access required.', 'danger')
            return redirect(url_for('employee.dashboard'))
        return f(*args, **kwargs)
    return decorated


# ── Login ─────────────────────────────────────────────────────────────────────

@employee_bp.route('/login', methods=['GET'])
def login():
    if 'emp_id' in session:
        return redirect(url_for('employee.dashboard'))
    return render_template('employee/login.html')


@employee_bp.route('/login', methods=['POST'])
def login_post():
    ip = request.remote_addr
    if _rate_limited(ip):
        flash('Too many attempts. Please wait 5 minutes.', 'danger')
        return render_template('employee/login.html')
    identifier = request.form.get('identifier', '').strip().lower()
    password   = request.form.get('password', '')
    if not identifier or not password:
        flash('Please enter both fields.', 'danger')
        return render_template('employee/login.html')
    emp = query(
        "SELECT * FROM employees WHERE (username=%s OR email=%s) AND is_active=1",
        (identifier, identifier), one=True
    )
    if emp and bcrypt.checkpw(password.encode(), emp['password_hash'].encode()):
        session.clear()
        session.permanent = True
        session['emp_id']   = emp['id']
        session['emp_name'] = emp['full_name']
        session['emp_role'] = emp['role']
        return redirect(url_for('employee.dashboard'))
    flash('Invalid credentials or account inactive.', 'danger')
    return render_template('employee/login.html')


@employee_bp.route('/logout')
def logout():
    session.pop('emp_id', None)
    session.pop('emp_name', None)
    session.pop('emp_role', None)
    return redirect(url_for('employee.login'))


# ── Dashboard ─────────────────────────────────────────────────────────────────

@employee_bp.route('/dashboard')
@emp_required
def dashboard():
    eid   = session['emp_id']
    level = _role_level()
    emp   = query("SELECT * FROM employees WHERE id=%s", (eid,), one=True)

    # Level 1 (Consultant/Stylist): only assigned enquiries
    # Level 2+ (Senior Stylist / Manager): all enquiries
    if level >= 2:
        enquiries = query(
            "SELECT e.*, u.full_name as customer_name, u.phone as customer_phone, "
            "emp2.full_name as assigned_to "
            "FROM enquiries e JOIN users u ON e.user_id=u.id "
            "LEFT JOIN employees emp2 ON e.assigned_employee_id=emp2.id "
            "ORDER BY e.updated_at DESC"
        )
    else:
        enquiries = query(
            "SELECT e.*, u.full_name as customer_name, u.phone as customer_phone, "
            "NULL as assigned_to "
            "FROM enquiries e JOIN users u ON e.user_id=u.id "
            "WHERE e.assigned_employee_id=%s ORDER BY e.updated_at DESC",
            (eid,)
        )

    total     = len(enquiries)
    pending   = sum(1 for e in enquiries if e['status'] == 'Pending')
    contacted = sum(1 for e in enquiries if e['status'] == 'Contacted')
    confirmed = sum(1 for e in enquiries if e['status'] == 'Confirmed')

    # Manager: also get employee list for reassign
    all_employees = []
    if level >= 3:
        all_employees = query(
            "SELECT id, full_name, role FROM employees WHERE is_active=1 ORDER BY full_name"
        )

    return render_template('employee/dashboard.html',
                           enquiries=enquiries, emp=emp, level=level,
                           total=total, pending=pending,
                           contacted=contacted, confirmed=confirmed,
                           all_employees=all_employees)


# ── Update enquiry (Consultant/Stylist — only assigned) ───────────────────────

@employee_bp.route('/enquiry/update/<int:enq_id>', methods=['POST'])
@emp_required
def update_enquiry(enq_id):
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('Invalid CSRF token.', 'danger')
        return redirect(url_for('employee.dashboard'))

    level = _role_level()

    # Level 1: can only update their own assigned enquiries
    if level < 2:
        enq = query(
            "SELECT * FROM enquiries WHERE enquiry_id=%s AND assigned_employee_id=%s",
            (enq_id, session['emp_id']), one=True
        )
        if not enq:
            flash('Enquiry not found or not assigned to you.', 'danger')
            return redirect(url_for('employee.dashboard'))
        allowed_statuses = ('Pending', 'Contacted', 'Confirmed')
    else:
        # Level 2+: can update any enquiry
        enq = query("SELECT * FROM enquiries WHERE enquiry_id=%s", (enq_id,), one=True)
        if not enq:
            flash('Enquiry not found.', 'danger')
            return redirect(url_for('employee.dashboard'))
        # Manager can also set Closed
        allowed_statuses = ('Pending', 'Contacted', 'Confirmed', 'Closed') if level >= 3 else ('Pending', 'Contacted', 'Confirmed')

    new_status = request.form.get('status', '').strip()
    emp_notes  = request.form.get('employee_notes', '').strip()[:1000]

    if new_status not in allowed_statuses:
        flash('Invalid status for your role.', 'danger')
        return redirect(url_for('employee.dashboard'))

    # Manager can also reassign
    if level >= 3:
        assign_id = request.form.get('assigned_employee_id', '').strip()
        emp_id_val = int(assign_id) if assign_id and assign_id.isdigit() else None
        execute(
            "UPDATE enquiries SET status=%s, employee_notes=%s, assigned_employee_id=%s WHERE enquiry_id=%s",
            (new_status, emp_notes, emp_id_val, enq_id)
        )
    else:
        execute(
            "UPDATE enquiries SET status=%s, employee_notes=%s WHERE enquiry_id=%s",
            (new_status, emp_notes, enq_id)
        )

    flash(f'Enquiry #{enq_id} updated to {new_status}.', 'success')
    return redirect(url_for('employee.dashboard'))
