from datetime import date
import uuid
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app, make_response
from functools import wraps
from db import query, execute

customer = Blueprint('customer', __name__)

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


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
    return render_template('customer/book.html', services=services, categories=categories,
                           rebook_services=rebook_services)


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
        "SELECT service_name FROM services WHERE id IN ({})".format(','.join(['%s'] * len(service_ids))),
        tuple(service_ids)
    )
    service_names = [s['service_name'] for s in services]
    services_str  = ', '.join(service_names)

    try:
        formatted_date = date.fromisoformat(preferred_date).strftime('%d %b %Y')
    except Exception:
        formatted_date = preferred_date

    execute(
        "INSERT INTO appointments (user_id, selected_services, preferred_date, preferred_time) VALUES (%s,%s,%s,%s)",
        (session['user_id'], services_str, preferred_date, preferred_time)
    )

    # SMS admin
    try:
        from sms import sms_new_booking
        admin_phone = current_app.config.get('ADMIN_PHONE', '')
        if admin_phone:
            sms_new_booking(admin_phone, user['full_name'], user['phone'], formatted_date, preferred_time)
    except Exception as e:
        current_app.logger.error('SMS error: %s', e)

    flash('Appointment booked! We will confirm it shortly.', 'success')
    return redirect(url_for('customer.appointments'))


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
