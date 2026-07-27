from flask import Blueprint, render_template, request, redirect, url_for, session, flash, Response
from flask_wtf.csrf import validate_csrf, ValidationError
from functools import wraps
import bcrypt, time, io, csv
from collections import defaultdict
import threading
from datetime import datetime, date as _date
import db

employee_bp = Blueprint('employee', __name__, url_prefix='/employee')

_login_attempts = defaultdict(list)
_lock = threading.Lock()

ROLE_LEVEL = {
    'Consultant':     1,
    'Stylist':        1,
    'Barber':         1,
    'Beautician':     1,
    'Receptionist':   1,
    'Senior Stylist': 2,
    'Manager':        3,
}

def _role_level():
    return ROLE_LEVEL.get(session.get('emp_role', ''), 1)

def _can_mark_attendance():
    """Check if the current employee has attendance access enabled."""
    emp = db.get_employee_by_id(session.get('emp_id', ''))
    if not emp:
        return False
    # Default: True if field missing (backward compat)
    return bool(emp.get('can_mark_attendance', True))

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

    emp = db.get_employee_by_identifier(identifier)
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


@employee_bp.route('/dashboard')
@emp_required
def dashboard():
    eid   = session['emp_id']
    level = _role_level()
    emp   = db.get_employee_by_id(eid)
    role  = session.get('emp_role', '')

    # Receptionist gets a dedicated dashboard
    if role == 'Receptionist':
        return redirect(url_for('employee.receptionist_dashboard'))

    if level >= 2:
        enquiries = db.get_all_enquiries()
    else:
        all_enqs  = db.get_all_enquiries()
        enquiries = [e for e in all_enqs if e.get('assigned_employee_id') == str(eid)]

    total     = len(enquiries)
    pending   = sum(1 for e in enquiries if e['status'] == 'Pending')
    contacted = sum(1 for e in enquiries if e['status'] == 'Contacted')
    confirmed = sum(1 for e in enquiries if e['status'] == 'Confirmed')

    all_employees = db.get_all_employees(active_only=True) if level >= 3 else []

    return render_template('employee/dashboard.html',
                           enquiries=enquiries, emp=emp, level=level,
                           total=total, pending=pending,
                           contacted=contacted, confirmed=confirmed,
                           all_employees=all_employees)


@employee_bp.route('/receptionist')
@emp_required
def receptionist_dashboard():
    if session.get('emp_role') != 'Receptionist':
        return redirect(url_for('employee.dashboard'))
    eid = session['emp_id']
    emp = db.get_employee_by_id(eid)
    today = _date.today().isoformat()

    all_enquiries = db.get_all_enquiries()

    # Today's appointments
    today_enqs = [e for e in all_enquiries if str(e.get('preferred_date', ''))[:10] == today]
    today_enqs = sorted(today_enqs, key=lambda x: x.get('preferred_time') or '')

    # Stats
    total     = len(all_enquiries)
    pending   = sum(1 for e in all_enquiries if e['status'] == 'Pending')
    confirmed = sum(1 for e in all_enquiries if e['status'] == 'Confirmed')
    today_count = len(today_enqs)

    # All employees for assignment
    all_employees = db.get_all_employees(active_only=True)

    # Attendance status
    today_att = db.get_attendance_today(eid)
    can_att   = _can_mark_attendance()

    return render_template('employee/receptionist.html',
        emp=emp, today=today, today_enqs=today_enqs,
        all_enquiries=all_enquiries, all_employees=all_employees,
        total=total, pending=pending, confirmed=confirmed, today_count=today_count,
        today_att=today_att, can_att=can_att)


# ── Attendance ────────────────────────────────────────────────────────────────

@employee_bp.route('/clock-in', methods=['POST'])
@emp_required
def clock_in():
    if not _can_mark_attendance():
        flash('Attendance access is disabled for your account. Contact admin.', 'danger')
        return redirect(url_for('employee.attendance'))
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('Invalid CSRF token.', 'danger')
        return redirect(url_for('employee.attendance'))
    _, err = db.clock_in(session['emp_id'])
    flash(err if err else 'Clocked in successfully!', 'danger' if err else 'success')
    return redirect(url_for('employee.attendance'))


@employee_bp.route('/clock-out', methods=['POST'])
@emp_required
def clock_out():
    if not _can_mark_attendance():
        flash('Attendance access is disabled for your account. Contact admin.', 'danger')
        return redirect(url_for('employee.attendance'))
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('Invalid CSRF token.', 'danger')
        return redirect(url_for('employee.attendance'))
    _, err = db.clock_out(session['emp_id'])
    flash(err if err else 'Clocked out successfully!', 'danger' if err else 'success')
    return redirect(url_for('employee.attendance'))


@employee_bp.route('/attendance')
@emp_required
def attendance():
    eid = session['emp_id']
    now = datetime.utcnow()
    year  = int(request.args.get('year',  now.year))
    month = int(request.args.get('month', now.month))
    today_rec = db.get_attendance_today(eid)
    monthly   = db.get_attendance_for_month(eid, year, month)
    emp       = db.get_employee_by_id(eid)
    # Build calendar grid
    import calendar
    cal = calendar.monthcalendar(year, month)
    att_map = {r['date']: r for r in monthly}
    present = sum(1 for r in monthly if r.get('status') in ('Present', 'Late'))
    absent  = sum(1 for r in monthly if r.get('status') == 'Absent')
    on_leave = sum(1 for r in monthly if r.get('status') == 'Leave')
    half_day = sum(1 for r in monthly if r.get('status') == 'Half Day')
    total_ot = round(sum(float(r.get('overtime_hours') or 0) for r in monthly), 2)
    month_name = calendar.month_name[month]
    return render_template('employee/attendance.html',
        today_rec=today_rec, monthly=monthly, emp=emp,
        year=year, month=month, month_name=month_name,
        cal=cal, att_map=att_map,
        present=present, absent=absent, on_leave=on_leave,
        half_day=half_day, total_ot=total_ot,
        level=_role_level(), today=_date.today().isoformat(),
        can_mark_attendance=_can_mark_attendance())


# ── Salary ────────────────────────────────────────────────────────────────────

@employee_bp.route('/salary')
@emp_required
def salary():
    eid = session['emp_id']
    now = datetime.utcnow()
    year  = int(request.args.get('year',  now.year))
    month = int(request.args.get('month', now.month))
    import calendar
    month_name = calendar.month_name[month]
    calc = db.calculate_salary(eid, year, month)
    saved = db.get_salary_record(eid, f'{year}-{month:02d}')
    emp = db.get_employee_by_id(eid)
    return render_template('employee/salary.html',
        calc=calc, saved=saved, emp=emp,
        year=year, month=month, month_name=month_name, level=_role_level())


# ── Leave ─────────────────────────────────────────────────────────────────────

@employee_bp.route('/leave')
@emp_required
def leave():
    eid = session['emp_id']
    requests = db.get_leave_requests_for_employee(eid)
    emp = db.get_employee_by_id(eid)
    return render_template('employee/leave.html', requests=requests, emp=emp, level=_role_level())


@employee_bp.route('/leave/apply', methods=['POST'])
@emp_required
def apply_leave():
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('Invalid CSRF token.', 'danger')
        return redirect(url_for('employee.leave'))
    from_date  = request.form.get('from_date', '').strip()
    to_date    = request.form.get('to_date', '').strip()
    reason     = request.form.get('reason', '').strip()[:500]
    leave_type = request.form.get('leave_type', 'Casual').strip()
    if not from_date or not to_date or not reason:
        flash('All fields are required.', 'danger')
        return redirect(url_for('employee.leave'))
    if from_date > to_date:
        flash('From date must be before or equal to To date.', 'danger')
        return redirect(url_for('employee.leave'))
    db.create_leave_request(session['emp_id'], from_date, to_date, reason, leave_type)
    flash('Leave request submitted.', 'success')
    return redirect(url_for('employee.leave'))


@employee_bp.route('/enquiry/update/<enq_id>', methods=['POST'])
@emp_required
def update_enquiry(enq_id):
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('Invalid CSRF token.', 'danger')
        return redirect(url_for('employee.dashboard'))

    level = _role_level()
    enq   = db.get_enquiry_by_id(enq_id)

    if not enq:
        flash('Enquiry not found.', 'danger')
        return redirect(url_for('employee.dashboard'))

    if level < 2 and session.get('emp_role') != 'Receptionist' and enq.get('assigned_employee_id') != str(session['emp_id']):
        flash('Enquiry not assigned to you.', 'danger')
        return redirect(url_for('employee.dashboard'))

    allowed_statuses = ('Pending', 'Contacted', 'Confirmed', 'Closed') if (level >= 3 or session.get('emp_role') == 'Receptionist') else ('Pending', 'Contacted', 'Confirmed')
    new_status = request.form.get('status', '').strip()
    emp_notes  = request.form.get('employee_notes', '').strip()[:1000]

    if new_status not in allowed_statuses:
        flash('Invalid status for your role.', 'danger')
        return redirect(url_for('employee.dashboard'))

    update_data = {'status': new_status, 'employee_notes': emp_notes}
    if level >= 3:
        assign_id = request.form.get('assigned_employee_id', '').strip()
        update_data['assigned_employee_id'] = assign_id if assign_id else None

    db.update_enquiry(enq_id, update_data)
    flash(f'Enquiry updated to {new_status}.', 'success')
    if session.get('emp_role') == 'Receptionist':
        return redirect(url_for('employee.receptionist_dashboard'))
    return redirect(url_for('employee.dashboard'))
