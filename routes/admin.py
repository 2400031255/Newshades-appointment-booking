from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app, Response
from functools import wraps
from db import query, execute
import bcrypt, os, csv, io
from werkzeug.utils import secure_filename

ALLOWED_EXT = {'jpg','jpeg','png','webp','gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.',1)[1].lower() in ALLOWED_EXT

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

@admin.route('/')
@admin_required
def dashboard():
    total_users = query("SELECT COUNT(*) as c FROM users WHERE is_admin=0", one=True)['c']
    total_services = query("SELECT COUNT(*) as c FROM services", one=True)['c']
    total_appts = query("SELECT COUNT(*) as c FROM appointments", one=True)['c']
    pending = query("SELECT COUNT(*) as c FROM appointments WHERE status='Pending'", one=True)['c']
    recent = query(
        "SELECT a.*, u.full_name, u.phone FROM appointments a JOIN users u ON a.user_id=u.id ORDER BY a.created_at DESC LIMIT 5"
    )
    return render_template('admin/dashboard.html',
                           total_users=total_users, total_services=total_services,
                           total_appts=total_appts, pending=pending, recent=recent)

# --- Services ---
@admin.route('/services')
@admin_required
def services():
    svcs = query("SELECT * FROM services ORDER BY category, service_name")
    return render_template('admin/services.html', services=svcs)

@admin.route('/services/add', methods=['GET', 'POST'])
@admin_required
def add_service():
    if request.method == 'POST':
        execute(
            "INSERT INTO services (service_name, description, price, duration, category, image_url) VALUES (%s,%s,%s,%s,%s,%s)",
            (request.form['service_name'], request.form['description'],
             request.form['price'], request.form['duration'],
             request.form['category'], request.form.get('image_url', ''))
        )
        flash('Service added.', 'success')
        return redirect(url_for('admin.services'))
    return render_template('admin/service_form.html', service=None)

@admin.route('/services/edit/<int:sid>', methods=['GET', 'POST'])
@admin_required
def edit_service(sid):
    svc = query("SELECT * FROM services WHERE id=%s", (sid,), one=True)
    if request.method == 'POST':
        execute(
            "UPDATE services SET service_name=%s, description=%s, price=%s, duration=%s, category=%s, image_url=%s, is_active=%s WHERE id=%s",
            (request.form['service_name'], request.form['description'],
             request.form['price'], request.form['duration'],
             request.form['category'], request.form.get('image_url', ''),
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

# --- Appointments ---
@admin.route('/appointments')
@admin_required
def appointments():
    status_filter = request.args.get('status', '')
    if status_filter:
        appts = query(
            "SELECT a.*, u.full_name, u.phone, u.email FROM appointments a JOIN users u ON a.user_id=u.id WHERE a.status=%s ORDER BY a.created_at DESC",
            (status_filter,)
        )
    else:
        appts = query(
            "SELECT a.*, u.full_name, u.phone, u.email FROM appointments a JOIN users u ON a.user_id=u.id ORDER BY a.created_at DESC"
        )
    return render_template('admin/appointments.html', appointments=appts, status_filter=status_filter)

@admin.route('/appointments/export')
@admin_required
def export_appointments():
    appts = query(
        "SELECT a.id, u.full_name, u.phone, u.email, a.selected_services, a.preferred_date, a.preferred_time, a.status, a.created_at "
        "FROM appointments a JOIN users u ON a.user_id=u.id ORDER BY a.created_at DESC"
    )
    si = io.StringIO()
    writer = csv.writer(si)
    writer.writerow(['ID','Customer','Phone','Email','Services','Date','Time','Status','Booked At'])
    for a in appts:
        writer.writerow([a['id'], a['full_name'], a['phone'], a['email'],
                         a['selected_services'], a['preferred_date'],
                         a['preferred_time'] or '', a['status'], a['created_at']])
    output = si.getvalue()
    return Response(output, mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=appointments.csv'})


@admin.route('/appointments/status/<int:aid>', methods=['POST'])
@admin_required
def update_status(aid):
    execute("UPDATE appointments SET status=%s WHERE id=%s", (request.form['status'], aid))
    flash('Status updated.', 'success')
    return redirect(url_for('admin.appointments'))

# --- Reviews ---
@admin.route('/reviews')
@admin_required
def reviews():
    revs = query(
        "SELECT r.*, u.full_name, u.phone FROM reviews r JOIN users u ON r.user_id=u.id ORDER BY r.created_at DESC"
    )
    avg = query("SELECT AVG(rating) as a, COUNT(*) as c FROM reviews", one=True)
    return render_template('admin/reviews.html', reviews=revs, avg=avg)

@admin.route('/reviews/delete/<int:rid>', methods=['POST'])
@admin_required
def delete_review(rid):
    execute("DELETE FROM reviews WHERE id=%s", (rid,))
    flash('Review deleted.', 'success')
    return redirect(url_for('admin.reviews'))

# --- Customers ---
@admin.route('/customers')
@admin_required
def customers():
    users = query("SELECT u.*, COUNT(a.id) as appt_count FROM users u LEFT JOIN appointments a ON u.id=a.user_id WHERE u.is_admin=0 GROUP BY u.id ORDER BY u.created_at DESC")
    return render_template('admin/customers.html', users=users)

# --- Profile ---
@admin.route('/profile', methods=['GET', 'POST'])
@admin_required
def profile():
    admin_user = query("SELECT * FROM users WHERE id=%s", (session['user_id'],), one=True)
    if request.method == 'POST':
        action = request.form.get('action')
        current_password = request.form.get('current_password', '')

        if not bcrypt.checkpw(current_password.encode(), admin_user['password_hash'].encode()):
            flash('Current password is incorrect.', 'danger')
            return redirect(url_for('admin.profile'))

        if action == 'username':
            new_username = request.form.get('new_username', '').strip().lower()
            if len(new_username) < 3:
                flash('Username must be at least 3 characters.', 'danger')
                return redirect(url_for('admin.profile'))
            existing = query("SELECT id FROM users WHERE username=%s AND id!=%s", (new_username, session['user_id']), one=True)
            if existing:
                flash('Username already taken.', 'danger')
                return redirect(url_for('admin.profile'))
            execute("UPDATE users SET username=%s WHERE id=%s", (new_username, session['user_id']))
            session['user_name'] = new_username
            flash('Username updated successfully.', 'success')

        elif action == 'password':
            new_password = request.form.get('new_password', '')
            confirm = request.form.get('confirm_password', '')
            if len(new_password) < 6:
                flash('Password must be at least 6 characters.', 'danger')
                return redirect(url_for('admin.profile'))
            if new_password != confirm:
                flash('Passwords do not match.', 'danger')
                return redirect(url_for('admin.profile'))
            hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
            execute("UPDATE users SET password_hash=%s WHERE id=%s", (hashed, session['user_id']))
            flash('Password updated successfully.', 'success')

        return redirect(url_for('admin.profile'))

    return render_template('admin/profile.html', admin=admin_user)

# --- Settings ---
@admin.route('/settings', methods=['GET', 'POST'])
@admin_required
def settings():
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'shop':
            fields = ['shop_name','shop_tagline','shop_address','shop_phone','shop_email','shop_hours_weekday','shop_hours_saturday','shop_hours_sunday','map_embed']
            for f in fields:
                val = request.form.get(f, '').strip()
                execute("INSERT INTO settings (`key`, value) VALUES (%s, %s) ON DUPLICATE KEY UPDATE value=%s", (f, val, val))
            flash('Shop details updated successfully.', 'success')

        elif action == 'whatsapp':
            wa = request.form.get('whatsapp_number', '').strip().replace('+','').replace(' ','').replace('-','')
            if not wa.isdigit() or len(wa) < 10:
                flash('Enter a valid WhatsApp number with country code.', 'danger')
            else:
                execute("INSERT INTO settings (`key`, value) VALUES ('whatsapp_number', %s) ON DUPLICATE KEY UPDATE value=%s", (wa, wa))
                flash('WhatsApp number updated.', 'success')

        elif action == 'account':
            new_username = request.form.get('new_username', '').strip().lower()
            new_password = request.form.get('new_password', '')
            confirm      = request.form.get('confirm_password', '')
            admin_user   = query("SELECT * FROM users WHERE id=%s", (session['user_id'],), one=True)

            if new_username and len(new_username) >= 3:
                existing = query("SELECT id FROM users WHERE username=%s AND id!=%s", (new_username, session['user_id']), one=True)
                if existing:
                    flash('Username already taken.', 'danger')
                    return redirect(url_for('admin.settings'))
                execute("UPDATE users SET username=%s WHERE id=%s", (new_username, session['user_id']))
                session['username'] = new_username
                flash('Username updated.', 'success')

            if new_password:
                if len(new_password) < 6:
                    flash('Password must be at least 6 characters.', 'danger')
                    return redirect(url_for('admin.settings'))
                if new_password != confirm:
                    flash('Passwords do not match.', 'danger')
                    return redirect(url_for('admin.settings'))
                hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
                execute("UPDATE users SET password_hash=%s WHERE id=%s", (hashed, session['user_id']))
                flash('Password updated successfully.', 'success')

        return redirect(url_for('admin.settings'))

    def get_setting(key, default=''):
        row = query("SELECT value FROM settings WHERE `key`=%s", (key,), one=True)
        return row['value'] if row else default

    s = {
        'whatsapp_number':    get_setting('whatsapp_number'),
        'shop_name':          get_setting('shop_name', 'New Shades'),
        'shop_tagline':       get_setting('shop_tagline', 'Premium Salon & Studio'),
        'shop_address':       get_setting('shop_address', '123 Salon Street, City'),
        'shop_phone':         get_setting('shop_phone', ''),
        'shop_email':         get_setting('shop_email', ''),
        'shop_hours_weekday': get_setting('shop_hours_weekday', ''),
        'shop_hours_saturday':get_setting('shop_hours_saturday', ''),
        'shop_hours_sunday':  get_setting('shop_hours_sunday', ''),
        'map_embed':          get_setting('map_embed', ''),
    }
    admin_user = query("SELECT username, email FROM users WHERE id=%s", (session['user_id'],), one=True)
    return render_template('admin/settings.html', s=s, admin_user=admin_user)

# --- Gallery ---
@admin.route('/gallery')
@admin_required
def gallery():
    photos = query("SELECT * FROM gallery ORDER BY created_at DESC")
    return render_template('admin/gallery.html', photos=photos)

@admin.route('/gallery/upload', methods=['POST'])
@admin_required
def gallery_upload():
    files = request.files.getlist('photos')
    caption = request.form.get('caption', '').strip()
    upload_dir = os.path.join(current_app.root_path, 'static', 'images', 'gallery')
    os.makedirs(upload_dir, exist_ok=True)
    count = 0
    for f in files:
        if f and allowed_file(f.filename):
            filename = secure_filename(f.filename)
            # avoid overwrite
            base, ext = os.path.splitext(filename)
            import time
            filename = f"{base}_{int(time.time()*1000)}{ext}"
            f.save(os.path.join(upload_dir, filename))
            execute("INSERT INTO gallery (filename, caption) VALUES (%s, %s)", (filename, caption))
            count += 1
    flash(f'{count} photo(s) uploaded successfully.', 'success')
    return redirect(url_for('admin.gallery'))

@admin.route('/gallery/delete/<int:gid>', methods=['POST'])
@admin_required
def gallery_delete(gid):
    photo = query("SELECT filename FROM gallery WHERE id=%s", (gid,), one=True)
    if photo:
        safe_name = secure_filename(photo['filename'])
        upload_dir = os.path.join(current_app.root_path, 'static', 'images', 'gallery')
        path = os.path.join(upload_dir, safe_name)
        # prevent path traversal — ensure file is inside gallery dir
        if os.path.abspath(path).startswith(os.path.abspath(upload_dir)) and os.path.exists(path):
            os.remove(path)
        execute("DELETE FROM gallery WHERE id=%s", (gid,))
        flash('Photo deleted.', 'success')
    return redirect(url_for('admin.gallery'))
