import logging
from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from flask_wtf.csrf import validate_csrf, ValidationError
from functools import wraps
from db import query, execute
from email_service import send_enquiry_received_email, send_admin_new_enquiry_email

logger = logging.getLogger(__name__)

customer = Blueprint('customer', __name__)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


# ── Dashboard ─────────────────────────────────────────────────────────────────

@customer.route('/dashboard')
@login_required
def dashboard():
    user = query("SELECT * FROM users WHERE id=%s", (session['user_id'],), one=True)
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))
    recent_enquiries = query(
        "SELECT * FROM enquiries WHERE user_id=%s ORDER BY created_at DESC LIMIT 3",
        (session['user_id'],)
    )
    total     = query("SELECT COUNT(*) as c FROM enquiries WHERE user_id=%s", (session['user_id'],), one=True)['c']
    pending   = query("SELECT COUNT(*) as c FROM enquiries WHERE user_id=%s AND status='Pending'", (session['user_id'],), one=True)['c']
    confirmed = query("SELECT COUNT(*) as c FROM enquiries WHERE user_id=%s AND status='Confirmed'", (session['user_id'],), one=True)['c']
    today_str = date.today().isoformat()
    today_offers = query(
        "SELECT * FROM offers WHERE is_active=1 "
        "AND (valid_from IS NULL OR valid_from <= %s) AND (valid_until IS NULL OR valid_until >= %s)",
        (today_str, today_str)
    )
    return render_template('customer/dashboard.html', user=user,
                           recent_enquiries=recent_enquiries,
                           total=total, pending=pending, confirmed=confirmed,
                           today_offers=today_offers)


# ── Enquire page (GET) ────────────────────────────────────────────────────────

@customer.route('/enquire', methods=['GET'])
@login_required
def enquire_page():
    services   = query("SELECT * FROM services WHERE is_active=1 ORDER BY category, service_name")
    categories = list(dict.fromkeys(s['category'] for s in services))
    today_str  = date.today().isoformat()
    today_offers = query(
        "SELECT * FROM offers WHERE is_active=1 "
        "AND (valid_from IS NULL OR valid_from <= %s) AND (valid_until IS NULL OR valid_until >= %s)",
        (today_str, today_str)
    )
    return render_template('customer/enquire.html', services=services,
                           categories=categories, today_offers=today_offers)


# ── Enquire (POST) ────────────────────────────────────────────────────────────

@customer.route('/enquire', methods=['POST'])
@login_required
def enquire():
    user = query("SELECT * FROM users WHERE id=%s", (session['user_id'],), one=True)
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))

    raw_ids     = request.form.getlist('services')
    service_ids = list({int(i) for i in raw_ids if str(i).isdigit()})[:20]
    preferred_date_str = request.form.get('preferred_date', '').strip()
    preferred_time     = request.form.get('preferred_time', '').strip()
    message            = request.form.get('message', '').strip()[:1000]

    if not service_ids or not preferred_date_str:
        flash('Please select at least one service and a preferred date.', 'warning')
        return redirect(url_for('customer.enquire_page'))

    try:
        enquiry_date = date.fromisoformat(preferred_date_str)
        if enquiry_date < date.today():
            flash('Please choose today or a future date.', 'warning')
            return redirect(url_for('customer.enquire_page'))
    except ValueError:
        flash('Please choose a valid date.', 'warning')
        return redirect(url_for('customer.enquire_page'))

    placeholders = ','.join(['%s'] * len(service_ids))
    services = query(
        f"SELECT service_name FROM services WHERE id IN ({placeholders}) AND is_active=1",
        tuple(service_ids)
    )
    if not services:
        flash('Selected services are no longer available.', 'warning')
        return redirect(url_for('customer.enquire_page'))

    service_names = [s['service_name'] for s in services]
    services_str  = ', '.join(service_names)

    try:
        formatted_date = enquiry_date.strftime('%d %b %Y')
    except (ValueError, AttributeError):
        formatted_date = preferred_date_str

    enquiry_id = execute(
        "INSERT INTO enquiries (user_id, selected_services, preferred_date, preferred_time, message, status) "
        "VALUES (%s,%s,%s,%s,%s,'Pending')",
        (session['user_id'], services_str, preferred_date_str, preferred_time or None, message)
    )

    # Email to customer
    try:
        if user.get('email'):
            send_enquiry_received_email(
                user['email'], user['full_name'],
                enquiry_id or 0, formatted_date, preferred_time, services_str
            )
    except (OSError, RuntimeError) as e:
        logger.error('Customer email error: %s', e)

    # Email to admin
    try:
        admin_email = current_app.config.get('ADMIN_EMAIL', '')
        if admin_email:
            send_admin_new_enquiry_email(
                admin_email, user['full_name'], user['phone'],
                enquiry_id or 0, formatted_date, preferred_time, services_str
            )
    except (OSError, RuntimeError) as e:
        logger.error('Admin email error: %s', e)

    return render_template('customer/enquiry_submitted.html',
        user=user, service_names=service_names,
        preferred_date=formatted_date, preferred_time=preferred_time,
        message=message, enquiry_id=enquiry_id or 0)


# ── My Enquiries ──────────────────────────────────────────────────────────────

@customer.route('/enquiries')
@login_required
def enquiries():
    enqs = query(
        "SELECT * FROM enquiries WHERE user_id=%s ORDER BY created_at DESC",
        (session['user_id'],)
    )
    existing_review = query("SELECT * FROM reviews WHERE user_id=%s", (session['user_id'],), one=True)
    has_confirmed   = any(e['status'] == 'Confirmed' for e in enqs)
    return render_template('customer/enquiries.html', enquiries=enqs,
                           existing_review=existing_review, has_confirmed=has_confirmed)


# ── Review ────────────────────────────────────────────────────────────────────

@customer.route('/review', methods=['POST'])
@login_required
def submit_review():
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('Invalid CSRF token.', 'danger')
        return redirect(url_for('customer.enquiries'))
    rating  = request.form.get('rating', '').strip()
    comment = request.form.get('comment', '').strip()
    if not rating.isdigit() or not (1 <= int(rating) <= 5):
        flash('Please select a valid rating.', 'danger')
        return redirect(url_for('customer.enquiries'))
    if not comment or len(comment) > 500:
        flash('Please write a review (max 500 characters).', 'danger')
        return redirect(url_for('customer.enquiries'))
    has_valid = query(
        "SELECT enquiry_id FROM enquiries WHERE user_id=%s AND status='Confirmed' LIMIT 1",
        (session['user_id'],), one=True
    )
    if not has_valid:
        flash('You can only review after a confirmed enquiry.', 'danger')
        return redirect(url_for('customer.enquiries'))
    existing = query("SELECT id FROM reviews WHERE user_id=%s", (session['user_id'],), one=True)
    if existing:
        execute("UPDATE reviews SET rating=%s, comment=%s WHERE user_id=%s",
                (int(rating), comment, session['user_id']))
    else:
        execute("INSERT INTO reviews (user_id, rating, comment) VALUES (%s,%s,%s)",
                (session['user_id'], int(rating), comment))
    flash('Thank you for your review!', 'success')
    return redirect(url_for('customer.enquiries'))


# ── How It Works ──────────────────────────────────────────────────────────────

@customer.route('/how-it-works')
@login_required
def how_it_works():
    today_str = date.today().isoformat()
    upcoming_offers = query(
        "SELECT * FROM offers WHERE is_active=1 "
        "AND (valid_until IS NULL OR valid_until >= %s) ORDER BY valid_from ASC",
        (today_str,)
    )
    return render_template('customer/how_it_works.html', upcoming_offers=upcoming_offers)


# ── Profile ───────────────────────────────────────────────────────────────────

@customer.route('/profile', methods=['GET'])
@login_required
def profile():
    user = query("SELECT * FROM users WHERE id=%s", (session['user_id'],), one=True)
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))
    return render_template('customer/profile.html', user=user)


@customer.route('/profile', methods=['POST'])
@login_required
def profile_post():
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('Invalid CSRF token.', 'danger')
        return redirect(url_for('customer.profile'))
    user = query("SELECT * FROM users WHERE id=%s", (session['user_id'],), one=True)
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))
    name  = request.form.get('full_name', '').strip()
    phone = request.form.get('phone', '').strip()
    if not name or len(name) > 100:
        flash('Please enter a valid name.', 'danger')
        return redirect(url_for('customer.profile'))
    if not phone or len(phone) > 20:
        flash('Please enter a valid phone number.', 'danger')
        return redirect(url_for('customer.profile'))
    execute("UPDATE users SET full_name=%s, phone=%s WHERE id=%s", (name, phone, session['user_id']))
    session['user_name'] = name
    flash('Profile updated successfully.', 'success')
    return redirect(url_for('customer.profile'))


# ── Legacy redirects (keep old URLs working) ──────────────────────────────────

@customer.route('/book', methods=['GET'])
@login_required
def book_page():
    return redirect(url_for('customer.enquire_page'))

@customer.route('/book', methods=['POST'])
@login_required
def book():
    return redirect(url_for('customer.enquire_page'))

@customer.route('/appointments')
@login_required
def appointments():
    return redirect(url_for('customer.enquiries'))
