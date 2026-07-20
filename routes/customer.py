import math
import logging
from datetime import date, datetime, timezone
import time
import threading
from collections import defaultdict
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from functools import wraps
from db import query, execute
from sms import sms_new_booking
from email_service import send_booking_received_email

logger = logging.getLogger(__name__)

_booking_attempts = defaultdict(list)
_booking_lock     = threading.Lock()


def _is_booking_rate_limited(ip):
    now = time.time()
    with _booking_lock:
        attempts = [t for t in _booking_attempts[ip] if now - t < 600]
        _booking_attempts[ip] = attempts
        if len(attempts) >= 5:
            return True
        _booking_attempts[ip].append(now)
    return False


def _safe_pct(val):
    """Return a valid float 0-100, rejecting NaN/Inf/out-of-range."""
    try:
        v = float(val or 0)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(v) or math.isinf(v) or not (0.0 <= v <= 100.0):
        return 0.0
    return v


def _build_offer_map(active_offers):
    """Only includes offers with blank coupon_code (auto-apply). Coupon-gated offers are skipped."""
    offer_map, global_offer = {}, None
    for o in active_offers:
        if not _safe_pct(o.get('discount_percent')):
            continue
        if (o.get('coupon_code') or '').strip():  # skip coupon-gated offers
            continue
        app_svcs = (o.get('applicable_services') or '').strip()
        if not app_svcs:
            if not global_offer:
                global_offer = o
        else:
            for sname in app_svcs.split(','):
                key = sname.strip().lower()
                if key and key not in offer_map:
                    offer_map[key] = o
    return offer_map, global_offer


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
    appts     = query("SELECT * FROM appointments WHERE user_id=%s ORDER BY created_at DESC LIMIT 3", (session['user_id'],))
    total     = query("SELECT COUNT(*) as c FROM appointments WHERE user_id=%s", (session['user_id'],), one=True)['c']
    pending   = query("SELECT COUNT(*) as c FROM appointments WHERE user_id=%s AND status='Pending'", (session['user_id'],), one=True)['c']
    confirmed = query("SELECT COUNT(*) as c FROM appointments WHERE user_id=%s AND status='Confirmed'", (session['user_id'],), one=True)['c']
    today_str = date.today().isoformat()
    today_offers = query(
        "SELECT * FROM offers WHERE is_active=1 "
        "AND (valid_from IS NULL OR valid_from <= %s) AND (valid_until IS NULL OR valid_until >= %s)",
        (today_str, today_str)
    )
    return render_template('customer/dashboard.html', user=user, recent_appts=appts,
                           total=total, pending=pending, confirmed=confirmed,
                           today_offers=today_offers)


# ── Book page (GET) ───────────────────────────────────────────────────────────

@customer.route('/book', methods=['GET'])
@login_required
def book_page():
    services   = query("SELECT * FROM services WHERE is_active=1 ORDER BY category, service_name")
    categories = list(dict.fromkeys(s['category'] for s in services))
    rebook_names = session.pop('rebook_services', None)
    rebook_ids   = [str(s['id']) for s in services
                    if rebook_names and s['service_name'].lower() in
                    [n.strip().lower() for n in rebook_names.split(',')]]

    today_str     = date.today().isoformat()
    active_offers = query(
        "SELECT * FROM offers WHERE is_active=1 "
        "AND (valid_from IS NULL OR valid_from <= %s) AND (valid_until IS NULL OR valid_until >= %s)",
        (today_str, today_str)
    )
    offer_map, global_offer = _build_offer_map(active_offers)

    for svc in services:
        key     = svc['service_name'].lower()
        matched = offer_map.get(key) or global_offer
        if matched:
            pct = _safe_pct(matched['discount_percent'])
            svc['offer_title']      = matched['title']
            svc['offer_pct']        = pct
            svc['offer_text']       = matched.get('discount_text') or f"{pct:.0f}% OFF"
            svc['discounted_price'] = round(float(svc['price']) * (1 - pct / 100), 2)
        else:
            svc['offer_title']      = None
            svc['offer_pct']        = 0
            svc['offer_text']       = None
            svc['discounted_price'] = float(svc['price'])

    return render_template('customer/book.html', services=services, categories=categories,
                           rebook_ids=rebook_ids, today_offers=active_offers)


# ── Book (POST) ───────────────────────────────────────────────────────────────

@customer.route('/book', methods=['POST'])
@login_required
def book():
    ip = request.remote_addr
    if _is_booking_rate_limited(ip):
        flash('Too many booking attempts. Please wait a few minutes.', 'danger')
        return redirect(url_for('customer.book_page'))

    user = query("SELECT * FROM users WHERE id=%s", (session['user_id'],), one=True)
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))

    raw_ids     = request.form.getlist('services')
    service_ids = list({int(i) for i in raw_ids if str(i).isdigit()})[:20]
    preferred_date_str = request.form.get('preferred_date', '').strip()
    preferred_time     = request.form.get('preferred_time', '').strip()

    if not service_ids or not preferred_date_str:
        flash('Please select at least one service and a date.', 'warning')
        return redirect(url_for('customer.book_page'))

    try:
        booking_date = date.fromisoformat(preferred_date_str)
        if booking_date < date.today():
            flash('Please choose today or a future date.', 'warning')
            return redirect(url_for('customer.book_page'))
    except ValueError:
        flash('Please choose a valid booking date.', 'warning')
        return redirect(url_for('customer.book_page'))

    placeholders = ','.join(['%s'] * len(service_ids))
    services = query(
        f"SELECT service_name, price FROM services WHERE id IN ({placeholders}) AND is_active=1",
        tuple(service_ids)
    )
    if not services:
        flash('Selected services are no longer available.', 'warning')
        return redirect(url_for('customer.book_page'))

    service_names = [s['service_name'] for s in services]
    services_str  = ', '.join(service_names)
    total_price   = sum(float(s['price'] or 0) for s in services)

    # Check coupon code submitted with form
    coupon_code_input = (request.form.get('coupon_code') or '').strip().upper()
    coupon_discount   = 0.0
    coupon_applied    = None
    if coupon_code_input:
        today_str2 = preferred_date_str
        coupon_row = query(
            "SELECT * FROM coupons WHERE UPPER(code)=%s AND is_active=1 "
            "AND (valid_until IS NULL OR valid_until >= %s)",
            (coupon_code_input, today_str2), one=True
        )
        if coupon_row:
            pct = float(coupon_row.get('discount_percent') or 0)
            max_uses = int(coupon_row.get('max_uses') or 0)
            used     = int(coupon_row.get('used_count') or 0)
            if pct and (max_uses == 0 or used < max_uses):
                coupon_discount = round(total_price * pct / 100, 2)
                coupon_applied  = coupon_row

    active_offers = query(
        "SELECT * FROM offers WHERE is_active=1 "
        "AND (valid_from IS NULL OR valid_from <= %s) AND (valid_until IS NULL OR valid_until >= %s)",
        (preferred_date_str, preferred_date_str)
    )
    offer_map, global_offer = _build_offer_map(active_offers)

    discount_amount = 0.0
    applied_offer   = None
    if not coupon_applied:  # only auto-apply offer if no coupon used
        for svc in services:
            matched = offer_map.get(svc['service_name'].lower()) or global_offer
            if matched:
                applied_offer    = matched
                discount_amount += float(svc['price'] or 0) * _safe_pct(matched['discount_percent']) / 100

    if coupon_applied:
        discount_amount  = coupon_discount
        discount_percent = float(coupon_applied['discount_percent'])
        offer_label      = f'Coupon: {coupon_code_input}'
    else:
        discount_amount  = round(discount_amount, 2)
        discount_percent = _safe_pct(applied_offer['discount_percent']) if applied_offer else 0.0
        offer_label      = applied_offer['title'] if applied_offer else ''

    final_price = round(total_price - discount_amount, 2)

    try:
        formatted_date = booking_date.strftime('%d %b %Y')
    except (ValueError, AttributeError):
        formatted_date = preferred_date_str

    execute(
        "INSERT INTO appointments (user_id, selected_services, preferred_date, preferred_time, "
        "total_price, discount_percent, offer_applied) VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (session['user_id'], services_str, preferred_date_str, preferred_time or None,
         final_price, discount_percent, offer_label)
    )
    if coupon_applied:
        execute("UPDATE coupons SET used_count=used_count+1 WHERE id=%s", (coupon_applied['id'],))

    try:
        admin_phone = current_app.config.get('ADMIN_PHONE', '')
        if admin_phone:
            sms_new_booking(admin_phone, user['full_name'], user['phone'], formatted_date, preferred_time)
    except (OSError, RuntimeError) as e:
        logger.error('SMS error: %s', e)

    try:
        admin_email = current_app.config.get('ADMIN_EMAIL', '')
        if admin_email:
            from email_service import send_admin_new_booking_email
            send_admin_new_booking_email(admin_email, user['full_name'], user['phone'],
                                         formatted_date, preferred_time, services_str)
    except (OSError, RuntimeError) as e:
        logger.error('Admin email error: %s', e)

    try:
        if user.get('email'):
            send_booking_received_email(user['email'], user['full_name'],
                                        formatted_date, preferred_time, services_str)
    except (OSError, RuntimeError) as e:
        logger.error('Email error: %s', e)

    return render_template('customer/confirm.html',
        user=user, service_names=service_names,
        preferred_date=formatted_date, preferred_time=preferred_time,
        total_price=total_price, discount_amount=discount_amount,
        final_price=final_price, applied_offer=coupon_applied or applied_offer)


# ── Ticket ────────────────────────────────────────────────────────────────────

@customer.route('/ticket/<int:aid>')
@login_required
def ticket(aid):
    appt = query(
        "SELECT a.*, u.full_name, u.phone, u.email FROM appointments a "
        "JOIN users u ON a.user_id=u.id WHERE a.id=%s AND a.user_id=%s",
        (aid, session['user_id']), one=True
    )
    if not appt or appt['status'] not in ('Confirmed', 'Checked In', 'Completed'):
        flash('Ticket not available.', 'danger')
        return redirect(url_for('customer.appointments'))
    if appt['status'] == 'Confirmed' and appt.get('ticket_expires_at'):
        try:
            exp = datetime.fromisoformat(str(appt['ticket_expires_at']))
            if datetime.now() > exp:
                flash('This ticket has expired.', 'danger')
                return redirect(url_for('customer.appointments'))
        except ValueError as e:
            logger.warning('ticket expiry parse error: %s', e)
    shop_name = query("SELECT value FROM settings WHERE `key`='shop_name'", one=True)
    shop_name = shop_name['value'] if shop_name else 'New Shades'
    return render_template('customer/ticket.html', appt=appt, shop_name=shop_name)


# ── Cancel ────────────────────────────────────────────────────────────────────

@customer.route('/cancel/<int:aid>', methods=['POST'])
@login_required
def cancel_appointment(aid):
    appt = query(
        "SELECT a.*, u.full_name, u.phone, u.email FROM appointments a "
        "JOIN users u ON a.user_id=u.id WHERE a.id=%s AND a.user_id=%s",
        (aid, session['user_id']), one=True
    )
    if appt and appt['status'] in ('Pending', 'Confirmed'):
        execute("UPDATE appointments SET status='Cancelled' WHERE id=%s", (aid,))
        flash('Appointment cancelled successfully.', 'success')
        # Notify admin
        try:
            admin_email = current_app.config.get('ADMIN_EMAIL', '')
            if admin_email:
                from email_service import _send, _base_html
                import html as _html
                n = _html.escape(appt['full_name'])
                d = _html.escape(str(appt['preferred_date']))
                t = _html.escape(str(appt['preferred_time'] or 'Flexible'))
                content = f"<p>Customer <strong style='color:#e8c96a;'>{n}</strong> has cancelled their appointment.</p><div class='detail-box'><div class='detail-row'><span class='detail-label'>Date</span><span class='detail-val'>{d}</span></div><div class='detail-row'><span class='detail-label'>Time</span><span class='detail-val'>{t}</span></div></div>"
                _send(admin_email, f'Appointment Cancelled – {n}', _base_html(content))
        except Exception as e:
            logger.error('Cancel notify error: %s', e)
    else:
        flash('Only pending or confirmed appointments can be cancelled.', 'danger')
    return redirect(url_for('customer.appointments'))


# ── Rebook ────────────────────────────────────────────────────────────────────

@customer.route('/rebook/<int:aid>')
@login_required
def rebook(aid):
    appt = query("SELECT * FROM appointments WHERE id=%s AND user_id=%s", (aid, session['user_id']), one=True)
    if not appt:
        return redirect(url_for('customer.book_page'))
    session['rebook_services'] = appt['selected_services']
    return redirect(url_for('customer.book_page'))


# ── Appointments list ─────────────────────────────────────────────────────────

@customer.route('/appointments')
@login_required
def appointments():
    appts = query("SELECT * FROM appointments WHERE user_id=%s ORDER BY created_at DESC", (session['user_id'],))
    existing_review = query("SELECT * FROM reviews WHERE user_id=%s", (session['user_id'],), one=True)
    has_confirmed   = any(a['status'] in ('Confirmed', 'Checked In', 'Completed') for a in appts)
    return render_template('customer/appointments.html', appointments=appts,
                           existing_review=existing_review, has_confirmed=has_confirmed)


# ── Review ────────────────────────────────────────────────────────────────────

@customer.route('/review', methods=['POST'])
@login_required
def submit_review():
    rating  = request.form.get('rating', '').strip()
    comment = request.form.get('comment', '').strip()
    if not rating.isdigit() or not (1 <= int(rating) <= 5):
        flash('Please select a valid rating.', 'danger')
        return redirect(url_for('customer.appointments'))
    if not comment or len(comment) > 500:
        flash('Please write a review (max 500 characters).', 'danger')
        return redirect(url_for('customer.appointments'))
    has_valid = query(
        "SELECT id FROM appointments WHERE user_id=%s "
        "AND status IN ('Confirmed','Checked In','Completed') LIMIT 1",
        (session['user_id'],), one=True
    )
    if not has_valid:
        flash('You can only review after a confirmed appointment.', 'danger')
        return redirect(url_for('customer.appointments'))
    existing = query("SELECT id FROM reviews WHERE user_id=%s", (session['user_id'],), one=True)
    if existing:
        execute("UPDATE reviews SET rating=%s, comment=%s WHERE user_id=%s",
                (int(rating), comment, session['user_id']))
    else:
        execute("INSERT INTO reviews (user_id, rating, comment) VALUES (%s,%s,%s)",
                (session['user_id'], int(rating), comment))
    flash('Thank you for your review!', 'success')
    return redirect(url_for('customer.appointments'))


# ── How It Works ─────────────────────────────────────────────────────────────

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
