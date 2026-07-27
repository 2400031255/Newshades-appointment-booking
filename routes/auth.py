from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import bcrypt
import re
import logging
import os
import time
import threading
from collections import defaultdict
import db

auth   = Blueprint('auth', __name__)
logger = logging.getLogger(__name__)

_login_attempts  = defaultdict(list)
_signup_attempts = defaultdict(list)
_login_lock      = threading.Lock()

_DUMMY_HASH = bcrypt.hashpw(os.urandom(32), bcrypt.gensalt()).decode()


def _is_rate_limited(ip, store, window=300, limit=10):
    now = time.time()
    with _login_lock:
        attempts = [t for t in store[ip] if now - t < window]
        store[ip] = attempts
        if len(attempts) >= limit:
            return True
        store[ip].append(now)
    return False


def _clear_rate_limit(ip):
    with _login_lock:
        _login_attempts.pop(ip, None)


def _validate_signup(form):
    full_name = form.get('full_name', '').strip()
    username  = form.get('username', '').strip().lower()
    email     = form.get('email', '').strip().lower()
    phone     = form.get('phone', '').strip()
    password  = form.get('password', '')
    confirm   = form.get('confirm_password', '')

    if not all([full_name, username, email, phone, password, confirm]):
        return 'All fields are required.'
    if len(full_name) > 100:
        return 'Name is too long.'
    if len(username) < 3 or not username.isalnum():
        return 'Username must be at least 3 alphanumeric characters.'
    if len(username) > 50:
        return 'Username is too long.'
    if len(email) > 100:
        return 'Email is too long.'
    digits = re.sub(r'[\s\+\-\(\)]', '', phone)
    if not digits.isdigit() or not (7 <= len(digits) <= 15):
        return 'Enter a valid phone number.'
    if password != confirm:
        return 'Passwords do not match.'
    if len(password) < 6:
        return 'Password must be at least 6 characters.'
    if len(password) > 128:
        return 'Password is too long.'
    return None


@auth.route('/signup', methods=['GET'])
def signup():
    return render_template('auth/signup.html')


@auth.route('/signup', methods=['POST'])
def signup_post():
    ip = request.remote_addr
    if _is_rate_limited(ip, _signup_attempts, window=600, limit=5):
        flash('Too many signup attempts. Please wait 10 minutes.', 'danger')
        return render_template('auth/signup.html')

    error = _validate_signup(request.form)
    if error:
        flash(error, 'danger')
        return render_template('auth/signup.html')

    full_name = request.form.get('full_name', '').strip()
    username  = request.form.get('username', '').strip().lower()
    email     = request.form.get('email', '').strip().lower()
    phone     = request.form.get('phone', '').strip()
    password  = request.form.get('password', '')

    if db.get_user_by_email(email) or db.get_user_by_username(username):
        flash('An account with those details already exists.', 'danger')
        return render_template('auth/signup.html')

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    db.create_user(full_name, username, phone, email, hashed)
    flash('Account created! Please log in.', 'success')
    return redirect(url_for('auth.login'))


@auth.route('/login', methods=['GET'])
def login():
    return render_template('auth/login.html')


@auth.route('/login', methods=['POST'])
def login_post():
    ip = request.remote_addr
    if _is_rate_limited(ip, _login_attempts, window=300, limit=10):
        flash('Too many login attempts. Please wait 5 minutes.', 'danger')
        return render_template('auth/login.html')

    identifier = request.form.get('identifier', '').strip().lower()
    password   = request.form.get('password', '')

    if not identifier or not password:
        flash('Please enter both login and password.', 'danger')
        return render_template('auth/login.html')
    if len(identifier) > 100 or len(password) > 128:
        flash('Invalid input.', 'danger')
        return render_template('auth/login.html')

    user = db.get_user_by_email_or_username(identifier)

    stored_hash = user['password_hash'].encode() if user else _DUMMY_HASH.encode()
    password_ok = bcrypt.checkpw(password.encode(), stored_hash)

    if user and password_ok:
        session.clear()
        session.permanent = True
        session['user_id']   = user['id']
        session['user_name'] = user['full_name']
        session['username']  = user['username']
        session['is_admin']  = bool(user['is_admin'])
        _clear_rate_limit(ip)
        if user['is_admin']:
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('customer.dashboard'))

    # Fallback: try employee login
    emp = db.get_employee_by_identifier(identifier)
    emp_hash = emp['password_hash'].encode() if emp else _DUMMY_HASH.encode()
    if emp and bcrypt.checkpw(password.encode(), emp_hash):
        session.clear()
        session.permanent = True
        session['emp_id']   = emp['id']
        session['emp_name'] = emp['full_name']
        session['emp_role'] = emp['role']
        return redirect(url_for('employee.dashboard'))

    flash('Invalid credentials. Please try again.', 'danger')
    return render_template('auth/login.html')


@auth.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))
