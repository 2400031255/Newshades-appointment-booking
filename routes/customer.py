import math
from datetime import date
import uuid
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from functools import wraps
from db import query, execute
from sms import sms_new_booking, sms_confirmed, sms_rejected
from email_service import send_booking_received_email, send_confirmation_email, send_rejection_email


def _safe_pct(val):
    """Convert val to a valid discount percent 0-100, returning 0 on any bad input."""
    try:
        v = float(val or 0)
        if math.isnan(v) or math.isinf(v) or not (0 <= v <= 100):
            return 0.0
        return v
    except (TypeError, ValueError):
        return 0.0


def _build_offer_map(active_offers):
    """Return (offer_map, global_offer) from a list of active offers."""
    offer_map, global_offer = {}, None
    for o in active_offers:
        if not _safe_pct(o.get('discount_percent')):
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


@customer.route('/calendar')
@login_required
def calendar_page():
    services = query("SELECT * FROM services WHERE is_active=1 ORDER BY category, service_name")
    return render_template('customer/calendar.html', services=services)


@customer.route('/dashboard')
@login_required
def dashboard():
    user = query("SELECT * FROM users WHERE id=%s", (session['user_id'],), one=True)
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))
    appts = query(
        "SELECT * FROM appointments WHERE user_id=%s ORDER BY created_at DESC LIMIT 3",
        (session['user_id'],)
    )
    total     = query("SELECT COUNT(*) as c FROM appointments WHERE user_id=%s", (session['user_id'],), one=True)['c']
    pending   = query("SELECT COUNT(*) as c FROM appointments WHERE user_id=%s AND status='Pending'", (session['user_id'],), one=True)['c']
    confirmed = query("SELECT COUNT(*) as c FROM appointments WHERE user_id=%s AND status='Confirmed'", (session['user_id'],), one=True)['c']
    return render_template('customer/dashboard.html', user=user, recent_appts=appts,
                           total=total, pending=pending, confirmed=confirmed)


@customer.route('/book')
@login_required
def book_page():
    services   = query("SELECT * FROM services WHERE is_active=1 ORDER BY category, service_name")
    categories = list(dict.fromkeys(s['category'] for s in services))
    rebook_services = session.pop('rebook_services', None)

    # Build offer map: service_name (lower) → best offer
    today_str = date.today().isoformat()
    active_offers = query(
        "SELECT * FROM offers WHERE is_active=1 "
        "AND (valid_from IS NULL OR valid_from <= %s) "
        "AND (valid_until IS NULL OR valid_until >= %s)",
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
                           rebook_services=rebook_services, active_offers=active_offers)


@customer.route('/book', methods=['POST'])
@login_required
def book():
    user = query("SELECT * FROM users WHERE id=%s", (session['user_id'],), one=True)
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))

    service_ids    = [int(i) for i in request.form.getlist('services') if i.isdigit()]
    preferred_date = request.form.get('preferred_date', '')
    preferred_time = request.form.get('preferred_time', '')

    if not service_ids or not preferred_date:
        flash('Please select at least one service and a date.', 'warning')
        return redirect(url_for('customer.book_page'))

    try:
        booking_date = date.fromisoformat(preferred_date)
        if booking_date < date.today():
            flash('Please choose today or a future date.', 'warning')
            return redirect(url_for('customer.book_page'))
    except ValueError:
        flash('Please choose a valid booking date.', 'warning')
        return redirect(url_for('customer.book_page'))

    services = query(
        "SELECT service_name, price FROM services WHERE id IN ({})".format(','.join(['%s'] * len(service_ids))),
        tuple(service_ids)
    )
    service_names = [s['service_name'] for s in services]
    services_str  = ', '.join(service_names)
    total_price   = sum(float(s['price'] or 0) for s in services)

    # Find best active offer — discount ONLY on matching services
    today_str = date.today().isoformat()
    active_offers = query(
        "SELECT * FROM offers WHERE is_active=1 AND (valid_from IS NULL OR valid_from <= %s) AND (valid_until IS NULL OR valid_until >= %s)",
        (today_str, today_str)
    )
    offer_map, global_offer = _build_offer_map(active_offers)

    discount_amount = 0.0
    applied_offer   = None
    for svc in services:
        key     = svc['service_name'].lower()
        matched = offer_map.get(key) or global_offer
        if matched:
            applied_offer    = matched
            pct              = _safe_pct(matched['discount_percent'])
            discount_amount += float(svc['price'] or 0) * pct / 100

    discount_amount  = round(discount_amount, 2)
    discount_percent = _safe_pct(applied_offer['discount_percent']) if applied_offer else 0.0
    final_price      = round(total_price - discount_amount, 2)

    try:
        formatted_date = date.fromisoformat(preferred_date).strftime('%d %b %Y')
    except Exception:
        formatted_date = preferred_date

    execute(
        "INSERT INTO appointments (user_id, selected_services, preferred_date, preferred_time, total_price, discount_percent, offer_applied) VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (session['user_id'], services_str, preferred_date, preferred_time,
         final_price, discount_percent, applied_offer['title'] if applied_offer else '')
    )

    # SMS admin
    try:
        admin_phone = current_app.config.get('ADMIN_PHONE', '')
        if admin_phone:
            sms_new_booking(admin_phone, user['full_name'], user['phone'], formatted_date, preferred_time)
    except Exception as e:
        current_app.logger.error('SMS error: %s', e)

    # Email customer
    try:
        if user.get('email'):
            send_booking_received_email(
                user['email'], user['full_name'],
                formatted_date, preferred_time, services_str
            )
    except Exception as e:
        current_app.logger.error('Email error: %s', e)

    return render_template('customer/confirm.html',
        user=user,
        service_names=service_names,
        preferred_date=formatted_date,
        preferred_time=preferred_time,
        total_price=total_price,
        discount_amount=discount_amount,
        final_price=final_price,
        applied_offer=applied_offer
    )


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
    shop_name = query("SELECT value FROM settings WHERE `key`='shop_name'", one=True)
    shop_name = shop_name['value'] if shop_name else 'New Shades'
    return render_template('customer/ticket.html', appt=appt, shop_name=shop_name)


@customer.route('/cancel/<int:aid>', methods=['POST'])
@login_required
def cancel_appointment(aid):
    appt = query("SELECT * FROM appointments WHERE id=%s AND user_id=%s", (aid, session['user_id']), one=True)
    if appt and appt['status'] == 'Pending':
        execute("UPDATE appointments SET status='Cancelled' WHERE id=%s", (aid,))
        flash('Appointment cancelled successfully.', 'success')
    else:
        flash('Only pending appointments can be cancelled.', 'danger')
    return redirect(url_for('customer.appointments'))


@customer.route('/rebook/<int:aid>')
@login_required
def rebook(aid):
    appt = query("SELECT * FROM appointments WHERE id=%s AND user_id=%s", (aid, session['user_id']), one=True)
    if not appt:
        return redirect(url_for('customer.book_page'))
    session['rebook_services'] = appt['selected_services']
    return redirect(url_for('customer.book_page'))


@customer.route('/appointments')
@login_required
def appointments():
    appts = query(
        "SELECT * FROM appointments WHERE user_id=%s ORDER BY created_at DESC",
        (session['user_id'],)
    )
    existing_review = query("SELECT * FROM reviews WHERE user_id=%s", (session['user_id'],), one=True)
    has_confirmed   = any(a['status'] in ('Confirmed', 'Checked In', 'Completed') for a in appts)
    return render_template('customer/appointments.html', appointments=appts,
                           existing_review=existing_review, has_confirmed=has_confirmed)


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
    existing = query("SELECT id FROM reviews WHERE user_id=%s", (session['user_id'],), one=True)
    if existing:
        execute("UPDATE reviews SET rating=%s, comment=%s WHERE user_id=%s",
                (int(rating), comment, session['user_id']))
    else:
        execute("INSERT INTO reviews (user_id, rating, comment) VALUES (%s,%s,%s)",
                (session['user_id'], int(rating), comment))
    flash('Thank you for your review!', 'success')
    return redirect(url_for('customer.appointments'))


@customer.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = query("SELECT * FROM users WHERE id=%s", (session['user_id'],), one=True)
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))
    if request.method == 'POST':
        name  = request.form['full_name'].strip()
        phone = request.form['phone'].strip()
        execute("UPDATE users SET full_name=%s, phone=%s WHERE id=%s",
                (name, phone, session['user_id']))
        session['user_name'] = name
        flash('Profile updated successfully.', 'success')
        return redirect(url_for('customer.profile'))
    return render_template('customer/profile.html', user=user)
