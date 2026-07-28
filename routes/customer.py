import logging
from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from flask_wtf.csrf import validate_csrf, ValidationError
from functools import wraps
import db
from email_service import send_enquiry_received_email, send_admin_new_enquiry_email

logger   = logging.getLogger(__name__)
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
    user = db.get_user_by_id(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))

    all_enqs      = db.get_enquiries_for_user(session['user_id'])
    recent_enquiries = all_enqs[:5]
    total     = len(all_enqs)
    pending   = sum(1 for e in all_enqs if e['status'] == 'Pending')
    confirmed = sum(1 for e in all_enqs if e['status'] == 'Confirmed')
    completed = sum(1 for e in all_enqs if e['status'] == 'Closed')
    cancelled = sum(1 for e in all_enqs if e['status'] in ('Cancelled', 'Closed'))
    upcoming_enquiry = next(
        (e for e in sorted(all_enqs, key=lambda x: x.get('preferred_date', ''))
         if e['status'] in ('Pending', 'Contacted', 'Confirmed')), None
    )
    today_str    = date.today().isoformat()
    today_offers = db.get_active_offers(today_str)
    all_services = db.get_all_services(active_only=True)[:6]

    return render_template('customer/dashboard.html', user=user,
                           recent_enquiries=recent_enquiries,
                           total=total, pending=pending, confirmed=confirmed,
                           completed=completed, cancelled=cancelled,
                           upcoming_enquiry=upcoming_enquiry,
                           visit_count=total,
                           today_offers=today_offers,
                           all_services=all_services)


@customer.route('/enquire', methods=['GET'])
@login_required
def enquire_page():
    services   = db.get_all_services(active_only=True)
    categories = list(dict.fromkeys(s['category'] for s in services))
    today_str  = date.today().isoformat()
    today_offers = db.get_active_offers(today_str)
    return render_template('customer/enquire.html', services=services,
                           categories=categories, today_offers=today_offers)


@customer.route('/enquire', methods=['POST'])
@login_required
def enquire():
    user = db.get_user_by_id(session['user_id'])
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))

    raw_ids            = request.form.getlist('services')
    service_ids        = list({i for i in raw_ids if i})[:20]
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

    services = db.get_services_by_ids(service_ids)
    if not services:
        flash('Selected services are no longer available.', 'warning')
        return redirect(url_for('customer.enquire_page'))

    service_names = [s['service_name'] for s in services]
    services_str  = ', '.join(service_names)

    try:
        formatted_date = enquiry_date.strftime('%d %b %Y')
    except (ValueError, AttributeError):
        formatted_date = preferred_date_str

    enquiry_id = db.create_enquiry(
        str(session['user_id']), services_str,
        preferred_date_str, preferred_time or None, message
    )

    try:
        if user.get('email'):
            send_enquiry_received_email(
                user['email'], user['full_name'],
                enquiry_id, formatted_date, preferred_time, services_str
            )
    except (OSError, RuntimeError) as e:
        logger.error('Customer email error: %s', e)

    try:
        admin_email = current_app.config.get('ADMIN_EMAIL', '')
        if admin_email:
            send_admin_new_enquiry_email(
                admin_email, user['full_name'], user['phone'],
                enquiry_id, formatted_date, preferred_time, services_str
            )
    except (OSError, RuntimeError) as e:
        logger.error('Admin email error: %s', e)

    return render_template('customer/enquiry_submitted.html',
        user=user, service_names=service_names,
        preferred_date=formatted_date, preferred_time=preferred_time,
        message=message, enquiry_id=enquiry_id)


@customer.route('/enquiries')
@login_required
def enquiries():
    enqs            = db.get_enquiries_for_user(session['user_id'])
    existing_review = db.get_review_by_user(session['user_id'])
    has_confirmed   = any(e['status'] == 'Confirmed' for e in enqs)
    return render_template('customer/enquiries.html', enquiries=enqs,
                           existing_review=existing_review, has_confirmed=has_confirmed)


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

    enqs = db.get_enquiries_for_user(session['user_id'])
    has_confirmed = any(e['status'] == 'Confirmed' for e in enqs)
    if not has_confirmed:
        flash('You can only review after a confirmed enquiry.', 'danger')
        return redirect(url_for('customer.enquiries'))

    existing = db.get_review_by_user(session['user_id'])
    if existing:
        db.update_review(session['user_id'], int(rating), comment)
    else:
        db.create_review(str(session['user_id']), int(rating), comment)

    flash('Thank you for your review!', 'success')
    return redirect(url_for('customer.enquiries'))


@customer.route('/offers')
@login_required
def offers_page():
    today_str = date.today().isoformat()
    all_offers    = db.get_all_offers()
    active_offers = db.get_active_offers(today_str)
    upcoming_offers = [o for o in all_offers
                       if o.get('is_active') and o.get('valid_from', '') > today_str]
    return render_template('customer/offers.html',
                           active_offers=active_offers,
                           upcoming_offers=upcoming_offers,
                           today_str=today_str)


@customer.route('/how-it-works')
@login_required
def how_it_works():
    today_str = date.today().isoformat()
    all_offers = db.get_all_offers()
    upcoming_offers = [o for o in all_offers
                       if o.get('is_active') and (not o.get('valid_until') or o['valid_until'] >= today_str)]
    return render_template('customer/how_it_works.html', upcoming_offers=upcoming_offers)


@customer.route('/profile', methods=['GET'])
@login_required
def profile():
    user = db.get_user_by_id(session['user_id'])
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

    user = db.get_user_by_id(session['user_id'])
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

    db.update_user(session['user_id'], {'full_name': name, 'phone': phone})
    session['user_name'] = name
    flash('Profile updated successfully.', 'success')
    return redirect(url_for('customer.profile'))


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
