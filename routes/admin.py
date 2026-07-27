from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app, Response
from flask_wtf.csrf import validate_csrf, ValidationError
from functools import wraps
import db as _db
import bcrypt, os, csv, io, math, time
from werkzeug.utils import secure_filename
from email_service import send_enquiry_confirmed_email, send_enquiry_closed_email

ALLOWED_EXT = {'jpg', 'jpeg', 'png', 'webp', 'gif'}

def allowed_file(f):
    return '.' in f and f.rsplit('.', 1)[1].lower() in ALLOWED_EXT

admin = Blueprint('admin', __name__, url_prefix='/admin')

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        if not session.get('is_admin'):
            flash('Access denied.', 'danger')
            return redirect(url_for('customer.dashboard'))
        return f(*args, **kwargs)
    return decorated


# ── Calendar ──────────────────────────────────────────────────────────────
@admin.route('/calendar')
@admin_required
def calendar():
    return render_template('admin/calendar.html')


# ── Dashboard ──────────────────────────────────────────────────────────────
@admin.route('/')
@admin_required
def dashboard():
    from datetime import date as _date
    all_users  = _db.get_all_customers()
    all_svcs   = _db.get_all_services()
    all_enqs   = _db.get_all_enquiries()
    total_users    = len(all_users)
    total_services = len(all_svcs)
    total_enqs     = len(all_enqs)
    pending   = sum(1 for e in all_enqs if e.get('status') == 'Pending')
    contacted = sum(1 for e in all_enqs if e.get('status') == 'Contacted')
    confirmed = sum(1 for e in all_enqs if e.get('status') == 'Confirmed')
    recent    = all_enqs[:5]
    today_str = _date.today().isoformat()
    today_enqs = [e for e in all_enqs if str(e.get('preferred_date', ''))[:10] == today_str]
    today_enqs = sorted(today_enqs, key=lambda x: x.get('preferred_time') or '')
    all_employees = _db.get_all_employees(active_only=True)
    return render_template('admin/dashboard.html',
                           total_users=total_users, total_services=total_services,
                           total_enqs=total_enqs, pending=pending,
                           contacted=contacted, confirmed=confirmed,
                           recent=recent, today_enqs=today_enqs,
                           all_employees=all_employees)


# ── Services ───────────────────────────────────────────────────────────────
@admin.route('/services')
@admin_required
def services():
    svcs = _db.get_all_services()
    return render_template('admin/services.html', services=svcs)


@admin.route('/services/add', methods=['GET', 'POST'])
@admin_required
def add_service():
    if request.method == 'POST':
        try:
            validate_csrf(request.form.get('csrf_token'))
        except ValidationError:
            flash('Invalid CSRF token.', 'danger')
            return redirect(url_for('admin.add_service'))
        name     = request.form.get('service_name', '').strip()
        desc     = request.form.get('description', '').strip()
        category = request.form.get('category', '').strip()
        duration = request.form.get('duration', '').strip()
        img_url  = request.form.get('image_url', '').strip()
        price_on_request = 1 if request.form.get('price_on_request') else 0
        try:
            price = 0.0 if price_on_request else float(request.form.get('price', 0))
            if price < 0:
                raise ValueError
        except (ValueError, TypeError):
            flash('Enter a valid price.', 'danger')
            return render_template('admin/service_form.html', service=None)
        if not name or len(name) > 100:
            flash('Service name is required (max 100 chars).', 'danger')
            return render_template('admin/service_form.html', service=None)
        if not category or len(category) > 50:
            flash('Category is required (max 50 chars).', 'danger')
            return render_template('admin/service_form.html', service=None)
        _db.create_service({
            'service_name': name, 'description': desc[:500], 'price': price,
            'duration': duration[:50], 'category': category[:50],
            'image_url': img_url[:255], 'is_active': 1,
            'price_on_request': price_on_request,
        })
        flash('Service added.', 'success')
        return redirect(url_for('admin.services'))
    return render_template('admin/service_form.html', service=None)


@admin.route('/services/edit/<sid>', methods=['GET', 'POST'])
@admin_required
def edit_service(sid):
    svc = _db.get_service_by_id(sid)
    if not svc:
        flash('Service not found.', 'danger')
        return redirect(url_for('admin.services'))
    if request.method == 'POST':
        try:
            validate_csrf(request.form.get('csrf_token'))
        except ValidationError:
            flash('Invalid CSRF token.', 'danger')
            return redirect(url_for('admin.edit_service', sid=sid))
        name     = request.form.get('service_name', '').strip()
        desc     = request.form.get('description', '').strip()
        category = request.form.get('category', '').strip()
        duration = request.form.get('duration', '').strip()
        img_url  = request.form.get('image_url', '').strip()
        price_on_request = 1 if request.form.get('price_on_request') else 0
        try:
            price = 0.0 if price_on_request else float(request.form.get('price', 0))
            if price < 0:
                raise ValueError
        except (ValueError, TypeError):
            flash('Enter a valid price.', 'danger')
            return render_template('admin/service_form.html', service=svc)
        if not name or len(name) > 100:
            flash('Service name is required (max 100 chars).', 'danger')
            return render_template('admin/service_form.html', service=svc)
        _db.update_service(sid, {
            'service_name': name, 'description': desc[:500], 'price': price,
            'duration': duration[:50], 'category': category[:50],
            'image_url': img_url[:255],
            'is_active': 1 if request.form.get('is_active') else 0,
            'price_on_request': price_on_request,
        })
        flash('Service updated.', 'success')
        return redirect(url_for('admin.services'))
    return render_template('admin/service_form.html', service=svc)


@admin.route('/services/delete/<sid>', methods=['POST'])
@admin_required
def delete_service(sid):
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('Invalid CSRF token.', 'danger')
        return redirect(url_for('admin.services'))
    _db.delete_service(sid)
    flash('Service deleted.', 'success')
    return redirect(url_for('admin.services'))


# ── Enquiries ───────────────────────────────────────────────────────────────
@admin.route('/enquiries')
@admin_required
def enquiries():
    status_filter = request.args.get('status', '')
    search        = request.args.get('q', '').strip()
    page          = max(1, int(request.args.get('page', 1) or 1))
    per_page      = 20

    all_enqs = _db.get_all_enquiries(
        status_filter=status_filter if status_filter else None,
        search=search if search else None
    )
    total_count = len(all_enqs)
    total_pages = max(1, math.ceil(total_count / per_page))
    offset      = (page - 1) * per_page
    enqs        = all_enqs[offset: offset + per_page]
    all_employees = _db.get_all_employees(active_only=True)
    return render_template('admin/enquiries.html', enquiries=enqs,
                           status_filter=status_filter, search=search,
                           page=page, total_pages=total_pages,
                           total_count=total_count,
                           all_employees=all_employees)


@admin.route('/enquiries/update/<eid>', methods=['POST'])
@admin_required
def enquiry_update(eid):
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('Invalid CSRF token.', 'danger')
        return redirect(url_for('admin.enquiries'))

    new_status  = request.form.get('status', '').strip()
    admin_notes = request.form.get('admin_notes', '').strip()[:1000]
    assign_emp  = request.form.get('assigned_employee_id', '').strip()
    valid_statuses = ('Pending', 'Contacted', 'Confirmed', 'Closed')
    if new_status not in valid_statuses:
        flash('Invalid status.', 'danger')
        return redirect(url_for('admin.enquiries'))

    enq = _db.get_enquiry_by_id(eid)
    if not enq:
        flash('Enquiry not found.', 'danger')
        return redirect(url_for('admin.enquiries'))

    _db.update_enquiry(eid, {
        'status': new_status,
        'admin_notes': admin_notes,
        'assigned_employee_id': assign_emp if assign_emp else None,
    })
    flash(f'Enquiry updated to {new_status}.', 'success')

    fmt_date = str(enq.get('preferred_date', ''))
    fmt_time = enq.get('preferred_time') or 'Flexible'

    if new_status == 'Confirmed':
        try:
            send_enquiry_confirmed_email(
                enq.get('email', ''), enq.get('full_name', ''),
                eid, fmt_date, fmt_time,
                enq.get('selected_services', ''), admin_notes
            )
        except Exception as e:
            current_app.logger.error('Email error: %s', e)
    elif new_status == 'Closed':
        try:
            send_enquiry_closed_email(
                enq.get('email', ''), enq.get('full_name', ''), eid, admin_notes
            )
        except Exception as e:
            current_app.logger.error('Email error: %s', e)

    return redirect(url_for('admin.enquiries'))


@admin.route('/enquiries/delete/<eid>', methods=['POST'])
@admin_required
def enquiry_delete(eid):
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('Invalid CSRF token.', 'danger')
        return redirect(url_for('admin.enquiries'))
    _db.delete_enquiry(eid)
    flash('Enquiry deleted.', 'success')
    return redirect(url_for('admin.enquiries'))


@admin.route('/enquiries/export')
@admin_required
def export_enquiries():
    enqs = _db.get_all_enquiries()
    si = io.StringIO()
    w  = csv.writer(si)
    w.writerow(['ID', 'Customer', 'Phone', 'Email', 'Services',
                'Preferred Date', 'Preferred Time', 'Message',
                'Status', 'Admin Notes', 'Submitted At'])
    for e in enqs:
        w.writerow([e.get('id',''), e.get('full_name',''), e.get('phone',''),
                    e.get('email',''), e.get('selected_services',''),
                    e.get('preferred_date',''), e.get('preferred_time',''),
                    e.get('message',''), e.get('status',''),
                    e.get('admin_notes',''), e.get('created_at','')])
    return Response(si.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=enquiries.csv'})


# ── Legacy appointment redirects ───────────────────────────────────────────
@admin.route('/appointments')
@admin_required
def appointments():
    return redirect(url_for('admin.enquiries'))

@admin.route('/appointments/action/<aid>', methods=['POST'])
@admin_required
def appointment_action(aid):
    return redirect(url_for('admin.enquiries'))

@admin.route('/appointments/export')
@admin_required
def export_appointments():
    return redirect(url_for('admin.export_enquiries'))


# ── Reviews ────────────────────────────────────────────────────────────────
@admin.route('/reviews')
@admin_required
def reviews():
    revs = _db.get_all_reviews()
    total = len(revs)
    avg_rating = round(sum(r.get('rating', 0) for r in revs) / total, 1) if total else 0
    avg = {'a': avg_rating, 'c': total}
    return render_template('admin/reviews.html', reviews=revs, avg=avg)


@admin.route('/reviews/delete/<rid>', methods=['POST'])
@admin_required
def delete_review(rid):
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('Invalid CSRF token.', 'danger')
        return redirect(url_for('admin.reviews'))
    _db.delete_review(rid)
    flash('Review deleted.', 'success')
    return redirect(url_for('admin.reviews'))


# ── Customers ──────────────────────────────────────────────────────────────
@admin.route('/customers')
@admin_required
def customers():
    users = _db.get_all_customers()
    return render_template('admin/customers.html', users=users)


@admin.route('/customers/<uid>')
@admin_required
def customer_detail(uid):
    user = _db.get_user_by_id(uid)
    if not user or user.get('is_admin'):
        flash('Customer not found.', 'danger')
        return redirect(url_for('admin.customers'))
    appts = _db.get_enquiries_for_user(uid)
    return render_template('admin/customer_detail.html', user=user, appointments=appts)


# ── Profile ────────────────────────────────────────────────────────────────
@admin.route('/profile', methods=['GET', 'POST'])
@admin_required
def profile():
    admin_user = _db.get_user_by_id(session['user_id'])
    if request.method == 'POST':
        try:
            validate_csrf(request.form.get('csrf_token'))
        except ValidationError:
            flash('Invalid CSRF token.', 'danger')
            return redirect(url_for('admin.profile'))
        action           = request.form.get('action')
        current_password = request.form.get('current_password', '')
        if not bcrypt.checkpw(current_password.encode(), admin_user['password_hash'].encode()):
            flash('Current password is incorrect.', 'danger')
            return redirect(url_for('admin.profile'))
        if action == 'username':
            new_username = request.form.get('new_username', '').strip().lower()
            if len(new_username) < 3:
                flash('Username must be at least 3 characters.', 'danger')
                return redirect(url_for('admin.profile'))
            existing = _db.get_user_by_username(new_username)
            if existing and existing['id'] != session['user_id']:
                flash('Username already taken.', 'danger')
                return redirect(url_for('admin.profile'))
            _db.update_user(session['user_id'], {'username': new_username})
            session['username'] = new_username
            flash('Username updated.', 'success')
        elif action == 'password':
            new_pw  = request.form.get('new_password', '')
            confirm = request.form.get('confirm_password', '')
            if len(new_pw) < 6:
                flash('Password must be at least 6 characters.', 'danger')
                return redirect(url_for('admin.profile'))
            if new_pw != confirm:
                flash('Passwords do not match.', 'danger')
                return redirect(url_for('admin.profile'))
            _db.update_user(session['user_id'], {
                'password_hash': bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt()).decode()
            })
            session.clear()
            flash('Password updated. Please log in again.', 'success')
            return redirect(url_for('auth.login'))
        return redirect(url_for('admin.profile'))
    return render_template('admin/profile.html', admin=admin_user)


# ── Settings ───────────────────────────────────────────────────────────────
@admin.route('/settings', methods=['GET', 'POST'])
@admin_required
def settings():
    if request.method == 'POST':
        try:
            validate_csrf(request.form.get('csrf_token'))
        except ValidationError:
            flash('Invalid CSRF token.', 'danger')
            return redirect(url_for('admin.settings'))
        action = request.form.get('action')
        if action == 'shop':
            for f in ['shop_name', 'shop_tagline', 'shop_address', 'shop_phone',
                      'shop_email', 'shop_hours_weekday', 'shop_hours_saturday',
                      'shop_hours_sunday', 'map_embed']:
                _db.set_setting(f, request.form.get(f, '').strip())
            flash('Shop details updated.', 'success')
        elif action == 'whatsapp':
            wa = request.form.get('whatsapp_number', '').strip().replace('+','').replace(' ','').replace('-','')
            if not wa.isdigit() or len(wa) < 10:
                flash('Enter a valid WhatsApp number with country code.', 'danger')
            else:
                _db.set_setting('whatsapp_number', wa)
                flash('WhatsApp number updated.', 'success')
        elif action == 'account':
            current_pw = request.form.get('current_password', '')
            admin_user = _db.get_user_by_id(session['user_id'])
            if not admin_user or not bcrypt.checkpw(current_pw.encode(), admin_user['password_hash'].encode()):
                flash('Current password is incorrect.', 'danger')
                return redirect(url_for('admin.settings'))
            new_username = request.form.get('new_username', '').strip().lower()
            new_password = request.form.get('new_password', '')
            confirm      = request.form.get('confirm_password', '')
            if new_username and len(new_username) >= 3:
                existing = _db.get_user_by_username(new_username)
                if existing and existing['id'] != session['user_id']:
                    flash('Username already taken.', 'danger')
                    return redirect(url_for('admin.settings'))
                _db.update_user(session['user_id'], {'username': new_username})
                session['username'] = new_username
                flash('Username updated.', 'success')
            if new_password:
                if len(new_password) < 6 or new_password != confirm:
                    flash('Password must be 6+ chars and match confirmation.', 'danger')
                    return redirect(url_for('admin.settings'))
                _db.update_user(session['user_id'], {
                    'password_hash': bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
                })
                flash('Password updated.', 'success')
        elif action == 'maintenance':
            val = '1' if request.form.get('maintenance_mode') else '0'
            _db.set_setting('maintenance_mode', val)
            state = 'enabled' if val == '1' else 'disabled'
            flash(f'Maintenance mode {state}.', 'success' if val == '0' else 'warning')
        return redirect(url_for('admin.settings'))

    s = {k: _db.get_setting(k, d) for k, d in [
        ('whatsapp_number', ''), ('shop_name', 'New Shades'),
        ('shop_tagline', 'Premium Salon & Studio'), ('shop_address', ''),
        ('shop_phone', ''), ('shop_email', ''), ('shop_hours_weekday', ''),
        ('shop_hours_saturday', ''), ('shop_hours_sunday', ''), ('map_embed', ''),
    ]}
    admin_user = _db.get_user_by_id(session['user_id'])
    maintenance_mode = _db.get_setting('maintenance_mode', '0')
    return render_template('admin/settings.html', s=s, admin_user=admin_user,
                           maintenance_mode=maintenance_mode)


# ── Gallery ────────────────────────────────────────────────────────────────
@admin.route('/gallery')
@admin_required
def gallery():
    photos = _db.get_all_gallery()
    return render_template('admin/gallery.html', photos=photos)

MAX_UPLOAD_BYTES = 8 * 1024 * 1024

@admin.route('/gallery/upload', methods=['POST'])
@admin_required
def gallery_upload():
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('Invalid CSRF token.', 'danger')
        return redirect(url_for('admin.gallery'))
    files      = request.files.getlist('photos')
    caption    = request.form.get('caption', '').strip()[:255]
    upload_dir = os.path.join(current_app.root_path, 'static', 'images', 'gallery')
    os.makedirs(upload_dir, exist_ok=True)
    count = 0
    for f in files:
        if not f or not f.filename:
            continue
        if not allowed_file(f.filename):
            continue
        safe = secure_filename(f.filename)
        if not safe:
            continue
        f.seek(0, 2)
        size = f.tell()
        f.seek(0)
        if size > MAX_UPLOAD_BYTES:
            flash(f'File {safe} exceeds 8 MB limit and was skipped.', 'warning')
            continue
        base, ext = os.path.splitext(safe)
        filename  = f"{base}_{int(time.time()*1000)}{ext}"
        dest = os.path.join(upload_dir, filename)
        if not os.path.abspath(dest).startswith(os.path.abspath(upload_dir)):
            continue
        f.save(dest)
        _db.add_gallery_photo(filename, caption)
        count += 1
    flash(f'{count} photo(s) uploaded.', 'success')
    return redirect(url_for('admin.gallery'))


@admin.route('/gallery/delete/<gid>', methods=['POST'])
@admin_required
def gallery_delete(gid):
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('Invalid CSRF token.', 'danger')
        return redirect(url_for('admin.gallery'))
    photo = _db.get_gallery_photo(gid)
    if photo:
        upload_dir = os.path.join(current_app.root_path, 'static', 'images', 'gallery')
        path = os.path.join(upload_dir, secure_filename(photo['filename']))
        if os.path.abspath(path).startswith(os.path.abspath(upload_dir)) and os.path.exists(path):
            os.remove(path)
        _db.delete_gallery_photo(gid)
        flash('Photo deleted.', 'success')
    return redirect(url_for('admin.gallery'))


# ── Schedule / Blocked Slots ─────────────────────────────────────────────
@admin.route('/schedule')
@admin_required
def schedule():
    from datetime import date
    blocks = _db.get_all_blocked_slots()
    for b in blocks:
        try:
            d = b['block_date']
            b['display_date'] = (str(d)[8:10] + '/' + str(d)[5:7] + '/' + str(d)[:4]) if len(str(d)) >= 10 else str(d)
        except Exception:
            b['display_date'] = str(b.get('block_date', ''))
    today = date.today().strftime('%d/%m/%Y')
    full_day_count = sum(1 for b in blocks if not b.get('block_time'))
    slot_count     = sum(1 for b in blocks if b.get('block_time'))
    return render_template('admin/schedule.html', blocks=blocks, today=today,
                           full_day_count=full_day_count, slot_count=slot_count)


@admin.route('/schedule/block', methods=['POST'])
@admin_required
def add_block():
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('Invalid CSRF token.', 'danger')
        return redirect(url_for('admin.schedule'))
    from datetime import datetime
    raw_date   = request.form.get('block_date', '').strip()
    block_time = request.form.get('block_time', '').strip() or None
    full_day   = request.form.get('full_day') == '1'
    reason     = request.form.get('reason', '').strip()
    try:
        block_date = datetime.strptime(raw_date, '%d/%m/%Y').strftime('%Y-%m-%d')
    except ValueError:
        flash('Invalid date format. Use DD/MM/YYYY.', 'danger')
        return redirect(url_for('admin.schedule'))
    if full_day:
        _db.delete_blocked_slots_for_date(block_date)
        _db.add_blocked_slot(block_date, None, reason or 'Full Day Blocked')
        flash(f'Full day blocked: {raw_date}', 'success')
    else:
        if not block_time:
            flash('Please select a time slot or enable Full Day.', 'danger')
            return redirect(url_for('admin.schedule'))
        existing = _db.get_blocked_slot(block_date, block_time)
        if existing:
            flash('That slot is already blocked.', 'warning')
            return redirect(url_for('admin.schedule'))
        _db.add_blocked_slot(block_date, block_time, reason)
        flash(f'Slot blocked: {raw_date} at {block_time}', 'success')
    return redirect(url_for('admin.schedule'))


@admin.route('/schedule/unblock/<bid>', methods=['POST'])
@admin_required
def delete_block(bid):
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('Invalid CSRF token.', 'danger')
        return redirect(url_for('admin.schedule'))
    _db.delete_blocked_slot(bid)
    flash('Block removed.', 'success')
    return redirect(url_for('admin.schedule'))


@admin.route('/schedule/unblock-date', methods=['POST'])
@admin_required
def unblock_date():
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('Invalid CSRF token.', 'danger')
        return redirect(url_for('admin.schedule'))
    from datetime import datetime
    raw_date = request.form.get('block_date', '').strip()
    try:
        block_date = datetime.strptime(raw_date, '%d/%m/%Y').strftime('%Y-%m-%d')
    except ValueError:
        flash('Invalid date.', 'danger')
        return redirect(url_for('admin.schedule'))
    _db.delete_blocked_slots_for_date(block_date)
    flash(f'All blocks removed for {raw_date}', 'success')
    return redirect(url_for('admin.schedule'))


# ── Offers ───────────────────────────────────────────────────────────────
@admin.route('/offers')
@admin_required
def offers():
    from datetime import date as _date
    all_offers   = _db.get_all_offers()
    all_services = _db.get_all_services(active_only=True)
    all_coupons  = _db.get_all_coupons()
    today_str    = _date.today().isoformat()
    upcoming_offers = [o for o in all_offers if o.get('valid_from') and str(o['valid_from'])[:10] > today_str]
    return render_template('admin/offers.html', offers=all_offers,
                           all_services=all_services, all_coupons=all_coupons,
                           now_date=today_str, upcoming_offers=upcoming_offers)


@admin.route('/offers/save', methods=['POST'])
@admin_required
def save_offer():
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('Invalid CSRF token.', 'danger')
        return redirect(url_for('admin.offers'))
    from datetime import datetime
    oid                 = request.form.get('offer_id', '').strip()
    title               = request.form.get('title', '').strip()
    description         = request.form.get('description', '').strip()
    discount_text       = request.form.get('discount_text', '').strip()
    discount_percent    = request.form.get('discount_percent', '0').strip() or '0'
    applicable_services = ','.join(request.form.getlist('applicable_services'))
    is_active           = 1 if request.form.get('is_active') else 0

    def parse_date(val):
        val = (val or '').strip()
        if not val:
            return None
        for fmt in ('%d/%m/%Y', '%Y-%m-%d'):
            try:
                return datetime.strptime(val, fmt).strftime('%Y-%m-%d')
            except ValueError:
                continue
        return None

    valid_from  = parse_date(request.form.get('valid_from')) or datetime.today().strftime('%Y-%m-%d')
    valid_until = parse_date(request.form.get('valid_until'))

    if not title or len(title) > 150:
        flash('Offer title is required (max 150 chars).', 'danger')
        return redirect(url_for('admin.offers'))
    try:
        discount_percent = float(discount_percent)
        if math.isnan(discount_percent) or not (0 <= discount_percent <= 100):
            raise ValueError
    except (ValueError, TypeError):
        flash('Discount % must be between 0 and 100.', 'danger')
        return redirect(url_for('admin.offers'))

    data = {
        'title': title, 'description': description[:1000],
        'discount_text': discount_text[:100],
        'discount_percent': discount_percent,
        'applicable_services': applicable_services,
        'valid_from': valid_from, 'valid_until': valid_until,
        'is_active': is_active,
    }
    if oid:
        _db.update_offer(oid, data)
        flash('Offer updated.', 'success')
    else:
        _db.create_offer(data)
        flash('Offer created.', 'success')
    return redirect(url_for('admin.offers'))


@admin.route('/offers/delete/<oid>', methods=['POST'])
@admin_required
def delete_offer(oid):
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('Invalid CSRF token.', 'danger')
        return redirect(url_for('admin.offers'))
    _db.delete_offer(oid)
    flash('Offer deleted.', 'success')
    return redirect(url_for('admin.offers'))


# ── Coupons ───────────────────────────────────────────────────────────────────
@admin.route('/coupons/save', methods=['POST'])
@admin_required
def save_coupon():
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('Invalid CSRF token.', 'danger')
        return redirect(url_for('admin.offers'))
    code             = request.form.get('code', '').strip().upper()[:30]
    discount_percent = request.form.get('discount_percent', '0').strip() or '0'
    max_uses         = request.form.get('max_uses', '0').strip() or '0'
    valid_until      = request.form.get('valid_until', '').strip() or None
    is_active        = 1 if request.form.get('is_active') else 0
    if not code:
        flash('Coupon code is required.', 'danger')
        return redirect(url_for('admin.offers'))
    try:
        discount_percent = float(discount_percent)
        if not (0 < discount_percent <= 100):
            raise ValueError
    except (ValueError, TypeError):
        flash('Discount % must be between 1 and 100.', 'danger')
        return redirect(url_for('admin.offers'))
    try:
        max_uses = int(max_uses)
        if max_uses < 0:
            raise ValueError
    except (ValueError, TypeError):
        max_uses = 0

    existing = _db.get_coupon_by_code(code)
    if existing:
        _db.update_coupon_by_code(code, {
            'discount_percent': discount_percent,
            'max_uses': max_uses,
            'valid_until': valid_until,
            'is_active': is_active,
        })
        flash(f'Coupon {code} updated.', 'success')
    else:
        _db.create_coupon({
            'code': code, 'discount_percent': discount_percent,
            'max_uses': max_uses, 'valid_until': valid_until,
            'is_active': is_active, 'used_count': 0,
        })
        flash(f'Coupon {code} created.', 'success')
    return redirect(url_for('admin.offers'))


@admin.route('/coupons/delete/<cid>', methods=['POST'])
@admin_required
def delete_coupon(cid):
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('Invalid CSRF token.', 'danger')
        return redirect(url_for('admin.offers'))
    _db.delete_coupon(cid)
    flash('Coupon deleted.', 'success')
    return redirect(url_for('admin.offers'))


# ── Employee Management ───────────────────────────────────────────────────────
@admin.route('/employees')
@admin_required
def employees():
    emps = _db.get_all_employees()
    return render_template('admin/employees.html', employees=emps)


@admin.route('/employees/create', methods=['POST'])
@admin_required
def create_employee():
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('Invalid CSRF token.', 'danger')
        return redirect(url_for('admin.employees'))
    full_name = request.form.get('full_name', '').strip()
    username  = request.form.get('username', '').strip().lower()
    phone     = request.form.get('phone', '').strip()
    email     = request.form.get('email', '').strip().lower()
    password  = request.form.get('password', '')
    role      = request.form.get('role', 'Consultant').strip()
    try:
        monthly_salary = float(request.form.get('monthly_salary', 0) or 0)
        working_days   = int(request.form.get('working_days_per_month', 26) or 26)
        overtime_rate  = float(request.form.get('overtime_rate', 150) or 150)
    except (ValueError, TypeError):
        monthly_salary, working_days, overtime_rate = 0.0, 26, 150.0
    if not all([full_name, username, phone, email, password]):
        flash('All fields are required.', 'danger')
        return redirect(url_for('admin.employees'))
    if len(password) < 6:
        flash('Password must be at least 6 characters.', 'danger')
        return redirect(url_for('admin.employees'))
    if _db.get_employee_by_identifier(username) or _db.get_employee_by_identifier(email):
        flash('Username or email already exists.', 'danger')
        return redirect(url_for('admin.employees'))
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    _db.create_employee({
        'full_name': full_name, 'username': username, 'phone': phone,
        'email': email, 'password_hash': hashed, 'role': role,
        'is_active': 1, 'monthly_salary': monthly_salary,
        'working_days_per_month': working_days, 'overtime_rate': overtime_rate,
        'can_mark_attendance': True,
    })
    flash(f'Employee {full_name} created. Username: {username}', 'success')
    return redirect(url_for('admin.employees'))


@admin.route('/employees/toggle/<eid>', methods=['POST'])
@admin_required
def toggle_employee(eid):
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('Invalid CSRF token.', 'danger')
        return redirect(url_for('admin.employees'))
    emp = _db.get_employee_by_id(str(eid))
    if not emp:
        flash('Employee not found.', 'danger')
        return redirect(url_for('admin.employees'))
    new_status = 0 if emp.get('is_active') else 1
    _db.update_employee(str(eid), {'is_active': new_status})
    flash(f"{emp['full_name']} {'activated' if new_status else 'deactivated'}.", 'success')
    return redirect(url_for('admin.employees'))


@admin.route('/employees/reset-password/<eid>', methods=['POST'])
@admin_required
def reset_employee_password(eid):
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('Invalid CSRF token.', 'danger')
        return redirect(url_for('admin.employees'))
    new_pw = request.form.get('new_password', '').strip()
    if len(new_pw) < 6:
        flash('Password must be at least 6 characters.', 'danger')
        return redirect(url_for('admin.employees'))
    hashed = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt()).decode()
    _db.update_employee(str(eid), {'password_hash': hashed})
    flash('Password reset successfully.', 'success')
    return redirect(url_for('admin.employees'))


@admin.route('/employees/delete/<eid>', methods=['POST'])
@admin_required
def delete_employee(eid):
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('Invalid CSRF token.', 'danger')
        return redirect(url_for('admin.employees'))
    _db.delete_employee(str(eid))
    flash('Employee deleted.', 'success')
    return redirect(url_for('admin.employees'))


@admin.route('/employees/toggle-attendance/<eid>', methods=['POST'])
@admin_required
def toggle_attendance_access(eid):
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('Invalid CSRF token.', 'danger')
        return redirect(url_for('admin.employees'))
    emp = _db.get_employee_by_id(str(eid))
    if not emp:
        flash('Employee not found.', 'danger')
        return redirect(url_for('admin.employees'))
    new_val = not bool(emp.get('can_mark_attendance', True))
    _db.update_employee(str(eid), {'can_mark_attendance': new_val})
    state = 'enabled' if new_val else 'disabled'
    flash(f"Attendance access {state} for {emp['full_name']}.", 'success')
    return redirect(url_for('admin.employees'))


# ── Attendance Management ────────────────────────────────────────────────────
@admin.route('/attendance')
@admin_required
def attendance():
    from datetime import datetime as _dt
    import calendar
    year     = int(request.args.get('year',  _dt.utcnow().year))
    month    = int(request.args.get('month', _dt.utcnow().month))
    month_name = calendar.month_name[month]
    date_str   = request.args.get('date', _dt.utcnow().strftime('%Y-%m-%d'))
    daily   = _db.get_all_attendance_for_date(date_str)
    monthly = _db.get_all_attendance_for_month(year, month)
    emps    = _db.get_all_employees(active_only=True)
    return render_template('admin/attendance.html',
                           daily=daily, monthly=monthly, emps=emps,
                           date_str=date_str, year=year, month=month,
                           month_name=month_name)


@admin.route('/attendance/mark', methods=['POST'])
@admin_required
def mark_attendance():
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('Invalid CSRF token.', 'danger')
        return redirect(url_for('admin.attendance'))
    emp_id    = request.form.get('employee_id', '').strip()
    date_str  = request.form.get('date', '').strip()
    status    = request.form.get('status', 'Present').strip()
    clock_in  = request.form.get('clock_in', '').strip() or None
    clock_out = request.form.get('clock_out', '').strip() or None
    if not emp_id or not date_str:
        flash('Employee and date are required.', 'danger')
        return redirect(url_for('admin.attendance'))
    _db.admin_mark_attendance(emp_id, date_str, status, clock_in, clock_out)
    flash('Attendance marked.', 'success')
    return redirect(url_for('admin.attendance', date=date_str))


@admin.route('/attendance/export')
@admin_required
def export_attendance():
    from datetime import datetime as _dt
    import calendar
    year  = int(request.args.get('year',  _dt.utcnow().year))
    month = int(request.args.get('month', _dt.utcnow().month))
    records = _db.get_all_attendance_for_month(year, month)
    si = io.StringIO()
    w  = csv.writer(si)
    w.writerow(['Employee', 'Role', 'Date', 'Clock In', 'Clock Out',
                'Status', 'Total Hours', 'Overtime Hours'])
    for r in records:
        w.writerow([r.get('emp_name',''), r.get('emp_role',''), r.get('date',''),
                    r.get('clock_in',''), r.get('clock_out',''), r.get('status',''),
                    r.get('total_hours',''), r.get('overtime_hours','')])
    month_name = calendar.month_name[month]
    return Response(si.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename=attendance_{month_name}_{year}.csv'})


# ── Payroll / Salary ──────────────────────────────────────────────────────────
@admin.route('/payroll')
@admin_required
def payroll():
    from datetime import datetime as _dt
    import calendar
    year       = int(request.args.get('year',  _dt.utcnow().year))
    month      = int(request.args.get('month', _dt.utcnow().month))
    month_str  = f'{year}-{month:02d}'
    month_name = calendar.month_name[month]
    emps       = _db.get_all_employees(active_only=True)
    records    = _db.get_all_salary_records(month_str)
    saved_map  = {r['employee_id']: r for r in records}
    return render_template('admin/payroll.html', emps=emps, saved_map=saved_map,
                           year=year, month=month, month_name=month_name,
                           month_str=month_str)


@admin.route('/payroll/generate', methods=['POST'])
@admin_required
def generate_salary():
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('Invalid CSRF token.', 'danger')
        return redirect(url_for('admin.payroll'))
    emp_id = request.form.get('employee_id', '').strip()
    year   = int(request.form.get('year',  0))
    month  = int(request.form.get('month', 0))
    if not emp_id or not year or not month:
        flash('Invalid request.', 'danger')
        return redirect(url_for('admin.payroll'))
    calc = _db.calculate_salary(emp_id, year, month)
    if not calc:
        flash('Employee not found.', 'danger')
        return redirect(url_for('admin.payroll', year=year, month=month))
    _db.save_salary_record(calc)
    flash(f"Salary generated for {calc['emp_name']} – ₹{calc['net_salary']:,.2f}", 'success')
    return redirect(url_for('admin.payroll', year=year, month=month))


@admin.route('/payroll/generate-all', methods=['POST'])
@admin_required
def generate_all_salaries():
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('Invalid CSRF token.', 'danger')
        return redirect(url_for('admin.payroll'))
    year  = int(request.form.get('year',  0))
    month = int(request.form.get('month', 0))
    emps  = _db.get_all_employees(active_only=True)
    count = 0
    for emp in emps:
        calc = _db.calculate_salary(emp['id'], year, month)
        if calc:
            _db.save_salary_record(calc)
            count += 1
    flash(f'Salary generated for {count} employees.', 'success')
    return redirect(url_for('admin.payroll', year=year, month=month))


@admin.route('/payroll/mark-paid/<salary_id>', methods=['POST'])
@admin_required
def mark_salary_paid(salary_id):
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('Invalid CSRF token.', 'danger')
        return redirect(url_for('admin.payroll'))
    year  = request.form.get('year',  '')
    month = request.form.get('month', '')
    _db.mark_salary_paid(salary_id)
    flash('Salary marked as paid.', 'success')
    return redirect(url_for('admin.payroll', year=year, month=month))


@admin.route('/payroll/slip/<salary_id>')
@admin_required
def salary_slip(salary_id):
    import calendar
    records = _db.get_all_salary_records()
    slip = next((r for r in records if r.get('id') == salary_id), None)
    if not slip:
        flash('Salary record not found.', 'danger')
        return redirect(url_for('admin.payroll'))
    emp = _db.get_employee_by_id(slip['employee_id'])
    year, month = map(int, slip['month'].split('-'))
    month_name = calendar.month_name[month]
    return render_template('admin/salary_slip.html', slip=slip, emp=emp,
                           month_name=month_name, year=year)


@admin.route('/payroll/export')
@admin_required
def export_payroll():
    from datetime import datetime as _dt
    import calendar
    year      = int(request.args.get('year',  _dt.utcnow().year))
    month     = int(request.args.get('month', _dt.utcnow().month))
    month_str = f'{year}-{month:02d}'
    records   = _db.get_all_salary_records(month_str)
    si = io.StringIO()
    w  = csv.writer(si)
    w.writerow(['Employee', 'Role', 'Month', 'Monthly Salary', 'Working Days',
                'Present', 'Absent', 'Half Day', 'Leave', 'Overtime Hrs',
                'Overtime Amount', 'Deduction', 'Net Salary', 'Status'])
    for r in records:
        deduction = float(r.get('absent_deduction', 0)) + float(r.get('half_day_deduction', 0))
        w.writerow([r.get('emp_name',''), r.get('emp_role',''), r.get('month',''),
                    r.get('monthly_salary',''), r.get('working_days',''),
                    r.get('present',''), r.get('absent',''), r.get('half_day',''),
                    r.get('on_leave',''), r.get('total_overtime',''),
                    r.get('overtime_amount',''), round(deduction, 2),
                    r.get('net_salary',''), 'Paid' if r.get('paid') else 'Pending'])
    month_name = calendar.month_name[month]
    return Response(si.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename=payroll_{month_name}_{year}.csv'})


# ── Leave Approvals ───────────────────────────────────────────────────────────
@admin.route('/leave-requests')
@admin_required
def leave_requests():
    status = request.args.get('status', '')
    reqs   = _db.get_all_leave_requests(status if status else None)
    return render_template('admin/leave_requests.html', requests=reqs, status_filter=status)


@admin.route('/leave-requests/action/<leave_id>', methods=['POST'])
@admin_required
def leave_action(leave_id):
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        flash('Invalid CSRF token.', 'danger')
        return redirect(url_for('admin.leave_requests'))
    action     = request.form.get('action', '').strip()
    admin_note = request.form.get('admin_note', '').strip()[:500]
    if action not in ('Approved', 'Rejected'):
        flash('Invalid action.', 'danger')
        return redirect(url_for('admin.leave_requests'))
    _db.update_leave_request(leave_id, action, admin_note)
    flash(f'Leave request {action.lower()}.', 'success')
    return redirect(url_for('admin.leave_requests'))


# ── Live feed ─────────────────────────────────────────────────────────────────
@admin.route('/enquiries/live-feed')
@admin_required
def enquiries_live_feed():
    from flask import jsonify
    enqs = _db.get_all_enquiries()[:20]
    result = []
    for e in enqs:
        result.append({
            'id':       e.get('id', ''),
            'status':   e.get('status', ''),
            'employee': e.get('emp_name') or '—',
            'note':     (e.get('employee_notes') or '')[:80],
            'updated':  str(e.get('updated_at', ''))[:16],
        })
    return jsonify(result)
