from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import bcrypt
from db import query, execute
from collections import defaultdict
import time

auth = Blueprint('auth', __name__)

# Simple in-memory rate limiter: max 5 attempts per IP per 5 minutes
_login_attempts = defaultdict(list)

def _is_rate_limited(ip):
    now = time.time()
    attempts = [t for t in _login_attempts[ip] if now - t < 300]
    _login_attempts[ip] = attempts
    if len(attempts) >= 5:
        return True
    _login_attempts[ip].append(now)
    return False

@auth.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        username  = request.form.get('username', '').strip().lower()
        email     = request.form.get('email', '').strip().lower()
        phone     = request.form.get('phone', '').strip()
        password  = request.form.get('password', '')
        confirm   = request.form.get('confirm_password', '')

        if not full_name or not username or not email or not phone or not password or not confirm:
            flash('All fields are required.', 'danger')
            return render_template('auth/signup.html')
        if len(username) < 3 or not username.isalnum():
            flash('Username must be at least 3 characters and contain only letters or numbers.', 'danger')
            return render_template('auth/signup.html')
        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/signup.html')
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return render_template('auth/signup.html')
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
    return render_template('auth/signup.html')

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
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

        # Allow login by username or email
        user = query("SELECT * FROM users WHERE email=%s OR username=%s", (identifier, identifier), one=True)

        if user and bcrypt.checkpw(password.encode(), user['password_hash'].encode()):
            session['user_id']   = user['id']
            session['user_name'] = user['full_name']
            session['username']  = user['username']
            session['is_admin']  = bool(user['is_admin'])
            if user['is_admin']:
                return redirect(url_for('admin.dashboard'))
            return redirect(url_for('customer.dashboard'))
        flash('Invalid credentials. Please try again.', 'danger')
    return render_template('auth/login.html')

@auth.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))
