from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import bcrypt
import re
import logging
from db import query, execute
from collections import defaultdict
import time
import threading

auth   = Blueprint('auth', __name__)
logger = logging.getLogger(__name__)

_login_attempts = defaultdict(list)
_login_lock     = threading.Lock()


def _is_rate_limited(ip):
    now = time.time()
    with _login_lock:
        attempts = [t for t in _login_attempts[ip] if now - t < 300]
        _login_attempts[ip] = attempts
        if len(attempts) >= 10:
            return True
        _login_attempts[ip].append(now)
    return False


def _clear_rate_limit(ip):
    with _login_lock:
        _login_attempts.pop(ip, None)


def _validate_signup(form):
    """Return error string or None if valid."""
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


# ── Signup ────────────────────────────────────────────────────────────────────

@auth.route('/signup', methods=['GET'])
def signup():
    return render_template('auth/signup.html')


@auth.route('/signup', methods=['POST'])
def signup_post():
    error = _validate_signup(request.form)
    if error:
        flash(error, 'danger')
        return render_template('auth/signup.html')

    full_name = request.form.get('full_name', '').strip()
    username  = request.form.get('username', '').strip().lower()
    email     = request.form.get('email', '').strip().lower()
    phone     = request.form.get('phone', '').strip()
    password  = request.form.get('password', '')

    if query("SELECT id FROM users WHERE email=%s", (email,), one=True):
        flash('Email already registered.', 'danger')
        return render_template('auth/signup.html')
    if query("SELECT id FROM users WHERE username=%s", (username,), one=True):
        flash('Username already taken.', 'danger')
        return render_template('auth/signup.html')

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    execute(
        "INSERT INTO users (full_name, username, phone, email, password_hash) VALUES (%s,%s,%s,%s,%s)",
        (full_name, username, phone, email, hashed)
    )
    flash('Account created! Please log in.', 'success')
    return redirect(url_for('auth.login'))


# ── Login ─────────────────────────────────────────────────────────────────────

@auth.route('/login', methods=['GET'])
def login():
    return render_template('auth/login.html')


@auth.route('/login', methods=['POST'])
def login_post():
    ip = request.remote_addr
    if _is_rate_limited(ip):
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

    user = query("SELECT * FROM users WHERE email=%s OR username=%s", (identifier, identifier), one=True)

    if user and bcrypt.checkpw(password.encode(), user['password_hash'].encode()):
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

    flash('Invalid credentials. Please try again.', 'danger')
    return render_template('auth/login.html')


# ── Logout ────────────────────────────────────────────────────────────────────

@auth.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))
