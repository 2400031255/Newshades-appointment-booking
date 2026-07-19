from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app, Response
from functools import wraps
from db import query, execute
import bcrypt, os, csv, io, uuid, math, time
from werkzeug.utils import secure_filename
from sms import sms_confirmed, sms_rejected
from email_service import send_confirmation_email, send_rejection_email

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
    total_users    = query("SELECT COUNT(*) as c FROM users WHERE is_admin=0", one=True)['c']
    total_services = query("SELECT COUNT(*) as c FROM services", one=True)['c']
    total_appts    = query("SELECT COUNT(*) as c FROM appointments", one=True)['c']
    pending        = query("SELECT COUNT(*) as c FROM appointments WHERE status='Pending'", one=True)['c']
    revenue_total  = query("SELECT COALESCE(SUM(total_price),0) as r FROM appointments WHERE status='Completed'", one=True)['r']
    month_start    = _date.today().replace(day=1).isoformat()
    revenue_month  = query(
        "SELECT COALESCE(SUM(total_price),0) as r FROM appointments WHERE status='Completed' AND preferred_date>=%s",
        (month_start,), one=True
    )['r']
    recent = query(
        "SELECT a.*, u.full_name, u.phone FROM appointments a "
        "JOIN users u ON a.user_id=u.id ORDER BY a.created_at DESC LIMIT 5"
    )
    return render_template('admin/dashboard.html', total_users=total_users,
                           total_services=total_services, total_appts=total_appts,
                           pending=pending, recent=recent,
                           revenue_total=float(revenue_total or 0),
                           revenue_month=float(revenue_month or 0))


# ── Services ───────────────────────────────────────────────────────────────
@admin.route('/services')
@admin_required
def services():
    svcs = query("SELECT * FROM services ORDER BY category, service_name")
    return render_template('admin/services.html', services=svcs)

@admin.route('/services/add', methods=['GET', 'POST'])
@admin_required
def add_service():
    if request.method == 'POST':
        name     = request.form.get('service_name', '').strip()
        desc     = request.form.get('description', '').strip()
        category = request.form.get('category', '').strip()
        duration = request.form.get('duration', '').strip()
        img_url  = request.form.get('image_url', '').strip()
        try:
            price = float(request.form.get('price', 0))
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
        execute(
            "INSERT INTO services (service_name, description, price, duration, category, image_url) VALUES (%s,%s,%s,%s,%s,%s)",
            (name, desc[:500], price, duration[:50], category, img_url[:255])
        )
        flash('Service added.', 'success')
        return redirect(url_for('admin.services'))
    return render_template('admin/service_form.html', service=None)

@admin.route('/services/edit/<int:sid>', methods=['GET', 'POST'])
@admin_required
def edit_service(sid):
    svc = query("SELECT * FROM services WHERE id=%s", (sid,), one=True)
    if not svc:
        flash('Service not found.', 'danger')
        return redirect(url_for('admin.services'))
    if request.method == 'POST':
        name     = request.form.get('service_name', '').strip()
        desc     = request.form.get('description', '').strip()
        category = request.form.get('category', '').strip()
        duration = request.form.get('duration', '').strip()
        img_url  = request.form.get('image_url', '').strip()
        try:
            price = float(request.form.get('price', 0))
            if price < 0:
                raise ValueError
        except (ValueError, TypeError):
            flash('Enter a valid price.', 'danger')
            return render_template('admin/service_form.html', service=svc)
        if not name or len(name) > 100:
            flash('Service name is required (max 100 chars).', 'danger')
            return render_template('admin/service_form.html', service=svc)
        execute(
            "UPDATE services SET service_name=%s, description=%s, price=%s, duration=%s, category=%s, image_url=%s, is_active=%s WHERE id=%s",
            (name, desc[:500], price, duration[:50], category[:50], img_url[:255],
             1 if request.form.get('is_active') else 0, sid)
        )
        flash('Service updated.', 'success')
        return redirect(url_for('admin.services'))
    return render_template('admin/service_form.html', service=svc)

@admin.route('/services/delete/<int:sid>', methods=['POST'])
@admin_required
def delete_service(sid):
    execute("DELETE FROM services WHERE id=%s", (sid,))
    flash('Service deleted.', 'success')
    return redirect(url_for('admin.services'))


# ── Appointments ───────────────────────────────────────────────────────────
@admin.route('/appointments')
@admin_required
def appointments():
    status_filter = request.args.get('status', '')
    search        = request.args.get('q', '').strip()
    base_sql = (
        "SELECT a.*, u.full_name, u.phone, u.email FROM appointments a "
        "JOIN users u ON a.user_id=u.id"
    )
    conditions, args = [], []
    if status_filter:
        conditions.append("a.status=%s"); args.append(status_filter)
    if search:
        conditions.append("(u.full_name LIKE %s OR u.phone LIKE %s OR a.selected_services LIKE %s)")
        args += [f'%{search}%', f'%{search}%', f'%{search}%']
    if conditions:
        base_sql += ' WHERE ' + ' AND '.join(conditions)
    base_sql += ' ORDER BY a.created_at DESC'
    appts = query(base_sql, tuple(args))
    return render_template('admin/appointments.html', appointments=appts,
                           status_filter=status_filter, search=search)


@admin.route('/appointments/action/<int:aid>', methods=['POST'])
@admin_required
def appointment_action(aid):
    action = request.form.get('action')
    appt   = query(
        "SELECT a.*, u.full_name, u.phone, u.email FROM appointments a JOIN users u ON a.user_id=u.id WHERE a.id=%s",
        (aid,), one=True
    )
    if not appt:
        flash('Appointment not found.', 'danger')
        return redirect(url_for('admin.appointments'))

    try:
        d = appt['preferred_date']
        fmt_date = d.strftime('%d %b %Y') if hasattr(d, 'strftime') else str(d)
    except Exception:
        fmt_date = str(appt['preferred_date'])
    fmt_time = appt['preferred_time'] or 'Flexible'

    if action == 'accept':
        ticket_id = str(uuid.uuid4())[:8].upper()
        # Ticket expires at end of appointment date
        try:
            from datetime import date as _date, datetime as _datetime
            appt_date  = _date.fromisoformat(str(appt['preferred_date'])[:10])
            expires_at = _datetime.combine(appt_date, _datetime.max.time()).isoformat()
        except Exception:
            expires_at = None
        execute(
            "UPDATE appointments SET status='Confirmed', ticket_id=%s, ticket_expires_at=%s WHERE id=%s",
            (ticket_id, expires_at, aid)
        )
        flash('Appointment confirmed and ticket generated.', 'success')
        try:
            sms_confirmed(appt['phone'], appt['full_name'], fmt_date, fmt_time)
        except Exception as e:
            current_app.logger.error('SMS error: %s', e)
        try:
            send_confirmation_email(appt['email'], appt['full_name'],
                                    fmt_date, fmt_time, appt['selected_services'])
        except Exception as e:
            current_app.logger.error('Email error: %s', e)

    elif action == 'reject':
        execute("UPDATE appointments SET status='Rejected' WHERE id=%s", (aid,))
        flash('Appointment rejected.', 'warning')
        try:
            sms_rejected(appt['phone'], appt['full_name'], fmt_date, fmt_time)
        except Exception as e:
            current_app.logger.error('SMS error: %s', e)
        try:
            send_rejection_email(appt['email'], appt['full_name'], fmt_date, fmt_time)
        except Exception as e:
            current_app.logger.error('Email error: %s', e)

    elif action == 'checkin':
        execute("UPDATE appointments SET status='Checked In' WHERE id=%s", (aid,))
        flash('Customer checked in.', 'success')

    elif action == 'complete':
        execute("UPDATE appointments SET status='Completed' WHERE id=%s", (aid,))
        flash('Appointment marked as completed.', 'success')

    elif action == 'delete':
        execute("DELETE FROM appointments WHERE id=%s", (aid,))
        flash('Appointment deleted.', 'success')

    return redirect(url_for('admin.appointments'))


@admin.route('/appointments/export')
@admin_required
def export_appointments():
    appts = query(
        "SELECT a.id, u.full_name, u.phone, u.email, a.selected_services, "
        "a.preferred_date, a.preferred_time, a.status, a.ticket_id, a.created_at "
        "FROM appointments a JOIN users u ON a.user_id=u.id ORDER BY a.created_at DESC"
    )
    si = io.StringIO()
    w  = csv.writer(si)
    w.writerow(['ID', 'Customer', 'Phone', 'Email', 'Services', 'Date', 'Time', 'Status', 'Ticket ID', 'Booked At'])
    for a in appts:
        w.writerow([a['id'], a['full_name'], a['phone'], a['email'],
                    a['selected_services'], a['preferred_date'],
                    a['preferred_time'] or '', a['status'], a.get('ticket_id') or '', a['created_at']])
    return Response(si.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=appointments.csv'})


# ── Reviews ────────────────────────────────────────────────────────────────
@admin.route('/reviews')
@admin_required
def reviews():
    revs = query(
        "SELECT r.*, u.full_name, u.phone FROM reviews r "
        "JOIN users u ON r.user_id=u.id ORDER BY r.created_at DESC"
    )
    avg = query("SELECT AVG(rating) as a, COUNT(*) as c FROM reviews", one=True)
    return render_template('admin/reviews.html', reviews=revs, avg=avg)

@admin.route('/reviews/delete/<int:rid>', methods=['POST'])
@admin_required
def delete_review(rid):
    execute("DELETE FROM reviews WHERE id=%s", (rid,))
    flash('Review deleted.', 'success')
    return redirect(url_for('admin.reviews'))


# ── Customers ──────────────────────────────────────────────────────────────
@admin.route('/customers')
@admin_required
def customers():
    users = query(
        "SELECT u.*, COUNT(a.id) as appt_count FROM users u "
        "LEFT JOIN appointments a ON u.id=a.user_id "
        "WHERE u.is_admin=0 GROUP BY u.id ORDER BY u.created_at DESC"
    )
    return render_template('admin/customers.html', users=users)


@admin.route('/customers/<int:uid>')
@admin_required
def customer_detail(uid):
    user = query("SELECT * FROM users WHERE id=%s AND is_admin=0", (uid,), one=True)
    if not user:
        flash('Customer not found.', 'danger')
        return redirect(url_for('admin.customers'))
    appts = query(
        "SELECT * FROM appointments WHERE user_id=%s ORDER BY created_at DESC",
        (uid,)
    )
    return render_template('admin/customer_detail.html', user=user, appointments=appts)


# ── Profile ────────────────────────────────────────────────────────────────
@admin.route('/profile', methods=['GET', 'POST'])
@admin_required
def profile():
    admin_user = query("SELECT * FROM users WHERE id=%s", (session['user_id'],), one=True)
    if request.method == 'POST':
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
            if query("SELECT id FROM users WHERE username=%s AND id!=%s", (new_username, session['user_id']), one=True):
                flash('Username already taken.', 'danger')
                return redirect(url_for('admin.profile'))
            execute("UPDATE users SET username=%s WHERE id=%s", (new_username, session['user_id']))
            session['user_name'] = new_username
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
            execute("UPDATE users SET password_hash=%s WHERE id=%s",
                    (bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt()).decode(), session['user_id']))
            flash('Password updated.', 'success')
        return redirect(url_for('admin.profile'))
    return render_template('admin/profile.html', admin=admin_user)


# ── Settings ───────────────────────────────────────────────────────────────
@admin.route('/settings', methods=['GET', 'POST'])
@admin_required
def settings():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'shop':
            for f in ['shop_name','shop_tagline','shop_address','shop_phone','shop_email',
                      'shop_hours_weekday','shop_hours_saturday','shop_hours_sunday','map_embed']:
                val = request.form.get(f, '').strip()
                existing = query("SELECT `key` FROM settings WHERE `key`=%s", (f,), one=True)
                if existing:
                    execute("UPDATE settings SET value=%s WHERE `key`=%s", (val, f))
                else:
                    execute("INSERT INTO settings (`key`, value) VALUES (%s,%s)", (f, val))
            flash('Shop details updated.', 'success')
        elif action == 'whatsapp':
            wa = request.form.get('whatsapp_number', '').strip().replace('+','').replace(' ','').replace('-','')
            if not wa.isdigit() or len(wa) < 10:
                flash('Enter a valid WhatsApp number with country code.', 'danger')
            else:
                existing = query("SELECT `key` FROM settings WHERE `key`='whatsapp_number'", one=True)
                if existing:
                    execute("UPDATE settings SET value=%s WHERE `key`='whatsapp_number'", (wa,))
                else:
                    execute("INSERT INTO settings (`key`, value) VALUES ('whatsapp_number',%s)", (wa,))
                flash('WhatsApp number updated.', 'success')
        elif action == 'account':
            current_pw = request.form.get('current_password', '')
            admin_user = query("SELECT * FROM users WHERE id=%s", (session['user_id'],), one=True)
            if not admin_user or not bcrypt.checkpw(current_pw.encode(), admin_user['password_hash'].encode()):
                flash('Current password is incorrect.', 'danger')
                return redirect(url_for('admin.settings'))
            new_username = request.form.get('new_username', '').strip().lower()
            new_password = request.form.get('new_password', '')
            confirm      = request.form.get('confirm_password', '')
            if new_username and len(new_username) >= 3:
                if query("SELECT id FROM users WHERE username=%s AND id!=%s", (new_username, session['user_id']), one=True):
                    flash('Username already taken.', 'danger')
                    return redirect(url_for('admin.settings'))
                execute("UPDATE users SET username=%s WHERE id=%s", (new_username, session['user_id']))
                session['username'] = new_username
                flash('Username updated.', 'success')
            if new_password:
                if len(new_password) < 6 or new_password != confirm:
                    flash('Password must be 6+ chars and match confirmation.', 'danger')
                    return redirect(url_for('admin.settings'))
                execute("UPDATE users SET password_hash=%s WHERE id=%s",
                        (bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode(), session['user_id']))
                flash('Password updated.', 'success')
        elif action == 'maintenance':
            val = '1' if request.form.get('maintenance_mode') else '0'
            existing = query("SELECT `key` FROM settings WHERE `key`='maintenance_mode'", one=True)
            if existing:
                execute("UPDATE settings SET value=%s WHERE `key`='maintenance_mode'", (val,))
            else:
                execute("INSERT INTO settings (`key`, value) VALUES ('maintenance_mode',%s)", (val,))
            state = 'enabled' if val == '1' else 'disabled'
            flash(f'Maintenance mode {state}.', 'success' if val == '0' else 'warning')
        return redirect(url_for('admin.settings'))

    def gs(key, default=''):
        row = query("SELECT value FROM settings WHERE `key`=%s", (key,), one=True)
        return row['value'] if row else default

    s = {k: gs(k, d) for k, d in [
        ('whatsapp_number',''), ('shop_name','New Shades'), ('shop_tagline','Premium Salon & Studio'),
        ('shop_address',''), ('shop_phone',''), ('shop_email',''),
        ('shop_hours_weekday',''), ('shop_hours_saturday',''), ('shop_hours_sunday',''), ('map_embed','')
    ]}
    admin_user = query("SELECT username, email FROM users WHERE id=%s", (session['user_id'],), one=True)
    maintenance_mode = gs('maintenance_mode', '0')
    return render_template('admin/settings.html', s=s, admin_user=admin_user, maintenance_mode=maintenance_mode)


# ── Gallery ────────────────────────────────────────────────────────────────
@admin.route('/gallery')
@admin_required
def gallery():
    photos = query("SELECT * FROM gallery ORDER BY created_at DESC")
    return render_template('admin/gallery.html', photos=photos)

MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # 8 MB per file

@admin.route('/gallery/upload', methods=['POST'])
@admin_required
def gallery_upload():
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
        # Check file size
        f.seek(0, 2)
        size = f.tell()
        f.seek(0)
        if size > MAX_UPLOAD_BYTES:
            flash(f'File {safe} exceeds 8 MB limit and was skipped.', 'warning')
            continue
        base, ext = os.path.splitext(safe)
        filename  = f"{base}_{int(time.time()*1000)}{ext}"
        dest = os.path.join(upload_dir, filename)
        # Path traversal guard
        if not os.path.abspath(dest).startswith(os.path.abspath(upload_dir)):
            continue
        f.save(dest)
        execute("INSERT INTO gallery (filename, caption) VALUES (%s,%s)", (filename, caption))
        count += 1
    flash(f'{count} photo(s) uploaded.', 'success')
    return redirect(url_for('admin.gallery'))

@admin.route('/gallery/delete/<int:gid>', methods=['POST'])
@admin_required
def gallery_delete(gid):
    photo = query("SELECT filename FROM gallery WHERE id=%s", (gid,), one=True)
    if photo:
        upload_dir = os.path.join(current_app.root_path, 'static', 'images', 'gallery')
        path = os.path.join(upload_dir, secure_filename(photo['filename']))
        if os.path.abspath(path).startswith(os.path.abspath(upload_dir)) and os.path.exists(path):
            os.remove(path)
        execute("DELETE FROM gallery WHERE id=%s", (gid,))
        flash('Photo deleted.', 'success')
    return redirect(url_for('admin.gallery'))


# ── Schedule / Blocked Slots ─────────────────────────────────────────────
@admin.route('/schedule')
@admin_required
def schedule():
    from datetime import date
    blocks = query("SELECT * FROM blocked_slots ORDER BY block_date ASC, block_time ASC")
    # Format dates as dd/mm/yyyy for display
    for b in blocks:
        try:
            d = b['block_date']
            b['display_date'] = d.strftime('%d/%m/%Y') if hasattr(d, 'strftime') else (str(d)[8:10]+'/'+str(d)[5:7]+'/'+str(d)[:4] if len(str(d)) >= 10 else str(d))
        except Exception:
            b['display_date'] = str(b['block_date'])
    today = date.today().strftime('%d/%m/%Y')
    full_day_count = sum(1 for b in blocks if not b['block_time'])
    slot_count     = sum(1 for b in blocks if b['block_time'])
    return render_template('admin/schedule.html', blocks=blocks, today=today,
                           full_day_count=full_day_count, slot_count=slot_count)


@admin.route('/schedule/block', methods=['POST'])
@admin_required
def add_block():
    from datetime import datetime
    raw_date   = request.form.get('block_date', '').strip()
    block_time = request.form.get('block_time', '').strip() or None
    full_day   = request.form.get('full_day') == '1'
    reason     = request.form.get('reason', '').strip()

    # Parse dd/mm/yyyy
    try:
        block_date = datetime.strptime(raw_date, '%d/%m/%Y').strftime('%Y-%m-%d')
    except ValueError:
        flash('Invalid date format. Use DD/MM/YYYY.', 'danger')
        return redirect(url_for('admin.schedule'))

    if full_day:
        # Block entire day — remove existing slots for that day first, insert one full-day record
        execute("DELETE FROM blocked_slots WHERE block_date=%s", (block_date,))
        execute(
            "INSERT INTO blocked_slots (block_date, block_time, reason) VALUES (%s,%s,%s)",
            (block_date, None, reason or 'Full Day Blocked')
        )
        flash(f'Full day blocked: {raw_date}', 'success')
    else:
        if not block_time:
            flash('Please select a time slot or enable Full Day.', 'danger')
            return redirect(url_for('admin.schedule'))
        # Check duplicate
        existing = query(
            "SELECT id FROM blocked_slots WHERE block_date=%s AND block_time=%s",
            (block_date, block_time), one=True
        )
        if existing:
            flash('That slot is already blocked.', 'warning')
            return redirect(url_for('admin.schedule'))
        execute(
            "INSERT INTO blocked_slots (block_date, block_time, reason) VALUES (%s,%s,%s)",
            (block_date, block_time, reason)
        )
        flash(f'Slot blocked: {raw_date} at {block_time}', 'success')
    return redirect(url_for('admin.schedule'))


@admin.route('/schedule/unblock/<int:bid>', methods=['POST'])
@admin_required
def delete_block(bid):
    execute("DELETE FROM blocked_slots WHERE id=%s", (bid,))
    flash('Block removed.', 'success')
    return redirect(url_for('admin.schedule'))


@admin.route('/schedule/unblock-date', methods=['POST'])
@admin_required
def unblock_date():
    from datetime import datetime
    raw_date = request.form.get('block_date', '').strip()
    try:
        block_date = datetime.strptime(raw_date, '%d/%m/%Y').strftime('%Y-%m-%d')
    except ValueError:
        flash('Invalid date.', 'danger')
        return redirect(url_for('admin.schedule'))
    execute("DELETE FROM blocked_slots WHERE block_date=%s", (block_date,))
    flash(f'All blocks removed for {raw_date}', 'success')
    return redirect(url_for('admin.schedule'))


# ── Offers ───────────────────────────────────────────────────────────────
@admin.route('/offers')
@admin_required
def offers():
    from datetime import date as _date
    all_offers = query("SELECT * FROM offers ORDER BY created_at DESC")
    all_services = query("SELECT id, service_name, price FROM services WHERE is_active=1 ORDER BY category, service_name")
    today_str = _date.today().isoformat()
    upcoming_offers = [o for o in all_offers if o.get('valid_from') and str(o['valid_from'])[:10] > today_str]
    return render_template('admin/offers.html', offers=all_offers, all_services=all_services,
                           now_date=today_str, upcoming_offers=upcoming_offers)

@admin.route('/offers/save', methods=['POST'])
@admin_required
def save_offer():
    from datetime import datetime
    oid                  = request.form.get('offer_id', '').strip()
    title                = request.form.get('title', '').strip()
    description          = request.form.get('description', '').strip()
    discount_text        = request.form.get('discount_text', '').strip()
    discount_percent     = request.form.get('discount_percent', '0').strip() or '0'
    applicable_services  = ','.join(request.form.getlist('applicable_services'))
    is_active            = 1 if request.form.get('is_active') else 0

    # Parse dd/mm/yyyy → yyyy-mm-dd for DB storage
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

    valid_from  = parse_date(request.form.get('valid_from'))
    valid_until = parse_date(request.form.get('valid_until'))

    # If admin does not supply a starting date, make the offer effective immediately
    if not valid_from:
        valid_from = datetime.today().strftime('%Y-%m-%d')

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
    description   = description[:1000]
    discount_text = discount_text[:100]

    if oid:
        execute(
            "UPDATE offers SET title=%s, description=%s, discount_text=%s, discount_percent=%s, "
            "applicable_services=%s, valid_from=%s, valid_until=%s, is_active=%s WHERE id=%s",
            (title, description, discount_text, discount_percent,
             applicable_services, valid_from, valid_until, is_active, int(oid))
        )
        flash('Offer updated.', 'success')
    else:
        execute(
            "INSERT INTO offers (title, description, discount_text, discount_percent, "
            "applicable_services, valid_from, valid_until, is_active) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (title, description, discount_text, discount_percent,
             applicable_services, valid_from, valid_until, is_active)
        )
        flash('Offer created.', 'success')
    return redirect(url_for('admin.offers'))

@admin.route('/offers/delete/<int:oid>', methods=['POST'])
@admin_required
def delete_offer(oid):
    execute("DELETE FROM offers WHERE id=%s", (oid,))
    flash('Offer deleted.', 'success')
    return redirect(url_for('admin.offers'))
