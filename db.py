import os
import json
import bcrypt
from datetime import datetime, timezone

import firebase_admin
from firebase_admin import credentials, firestore

_db = None


def _get_firestore():
    global _db
    if _db is not None:
        return _db

    if not firebase_admin._apps:
        cred_json = os.environ.get('FIREBASE_CREDENTIALS', '')
        if not cred_json:
            raise RuntimeError('FIREBASE_CREDENTIALS env var not set')
        cred_dict = json.loads(cred_json)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)

    _db = firestore.client()
    _seed_initial_data(_db)
    return _db


# ── Seed ──────────────────────────────────────────────────────────────────────

_DEFAULT_SERVICES = [
    {'service_name': 'Hair Cut',     'description': 'Professional haircut styled to your preference', 'price': 300.0, 'duration': '30 mins', 'category': 'Hair',     'image_url': '', 'is_active': 1, 'price_on_request': 0},
    {'service_name': 'Beard Trim',   'description': 'Clean beard shaping and trimming',               'price': 150.0, 'duration': '20 mins', 'category': 'Beard',    'image_url': '', 'is_active': 1, 'price_on_request': 0},
    {'service_name': 'Hair Color',   'description': 'Full hair coloring with premium products',       'price': 800.0, 'duration': '90 mins', 'category': 'Hair',     'image_url': '', 'is_active': 1, 'price_on_request': 0},
    {'service_name': 'Facial',       'description': 'Deep cleansing facial treatment',                'price': 500.0, 'duration': '45 mins', 'category': 'Skin',     'image_url': '', 'is_active': 1, 'price_on_request': 0},
    {'service_name': 'Head Massage', 'description': 'Relaxing scalp and head massage',                'price': 250.0, 'duration': '30 mins', 'category': 'Wellness', 'image_url': '', 'is_active': 1, 'price_on_request': 0},
    {'service_name': 'Hair Spa',     'description': 'Nourishing hair spa treatment',                  'price': 600.0, 'duration': '60 mins', 'category': 'Hair',     'image_url': '', 'is_active': 1, 'price_on_request': 0},
]


def _seed_initial_data(db):
    # Seed admin user if no admin exists
    admins = db.collection('users').where('is_admin', '==', 1).limit(1).get()
    if not admins:
        seed_hash = os.environ.get('SEED_ADMIN_HASH', '')
        if not seed_hash:
            seed_hash = bcrypt.hashpw(
                os.environ.get('SEED_ADMIN_PASSWORD', 'komali123').encode(),
                bcrypt.gensalt()
            ).decode()
        admin_ref = db.collection('users').document()
        admin_ref.set({
            'id':            admin_ref.id,
            'full_name':     os.environ.get('SEED_ADMIN_NAME', 'Admin'),
            'username':      os.environ.get('SEED_ADMIN_USERNAME', 'komali'),
            'phone':         os.environ.get('SEED_ADMIN_PHONE', '0000000000'),
            'email':         os.environ.get('SEED_ADMIN_EMAIL', 'admin@newshades.com'),
            'password_hash': seed_hash,
            'is_admin':      1,
            'created_at':    datetime.now(timezone.utc).isoformat(),
        })

    # Seed default services if none exist
    services = db.collection('services').limit(1).get()
    if not services:
        for svc in _DEFAULT_SERVICES:
            ref = db.collection('services').document()
            svc['id'] = ref.id
            svc['created_at'] = datetime.now(timezone.utc).isoformat()
            ref.set(svc)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _doc_to_dict(doc):
    d = doc.to_dict()
    if d is None:
        return None
    d['id'] = doc.id
    return d


def _auto_id(db, collection):
    return db.collection(collection).document().id


# ── Public API (mirrors old query/execute interface) ──────────────────────────

def get_db():
    return _get_firestore()


def close_db(e=None):
    pass  # Firestore connections are managed by the SDK


# ── Collection helpers ────────────────────────────────────────────────────────

def _col(name):
    return _get_firestore().collection(name)


# ── Users ─────────────────────────────────────────────────────────────────────

def get_user_by_id(uid):
    doc = _col('users').document(str(uid)).get()
    return _doc_to_dict(doc) if doc.exists else None


def get_user_by_email_or_username(identifier):
    db = _get_firestore()
    by_email = db.collection('users').where('email', '==', identifier).limit(1).get()
    if by_email:
        return _doc_to_dict(by_email[0])
    by_user = db.collection('users').where('username', '==', identifier).limit(1).get()
    if by_user:
        return _doc_to_dict(by_user[0])
    return None


def get_user_by_email(email):
    docs = _col('users').where('email', '==', email).limit(1).get()
    return _doc_to_dict(docs[0]) if docs else None


def get_user_by_username(username):
    docs = _col('users').where('username', '==', username).limit(1).get()
    return _doc_to_dict(docs[0]) if docs else None


def create_user(full_name, username, phone, email, password_hash, is_admin=0):
    ref = _col('users').document()
    ref.set({
        'id': ref.id, 'full_name': full_name, 'username': username,
        'phone': phone, 'email': email, 'password_hash': password_hash,
        'is_admin': is_admin, 'created_at': datetime.now(timezone.utc).isoformat(),
    })
    return ref.id


def update_user(uid, data):
    _col('users').document(str(uid)).update(data)


def get_all_customers():
    docs = _col('users').get()
    users = [_doc_to_dict(d) for d in docs if not _doc_to_dict(d).get('is_admin')]
    users = sorted(users, key=lambda x: x.get('created_at', ''), reverse=True)
    for u in users:
        enqs = _col('enquiries').where('user_id', '==', u['id']).get()
        u['appt_count'] = len(enqs)
    return users


# ── Services ──────────────────────────────────────────────────────────────────

def get_all_services(active_only=False):
    q = _col('services')
    if active_only:
        q = q.where('is_active', '==', 1)
    docs = q.get()
    svcs = [_doc_to_dict(d) for d in docs]
    return sorted(svcs, key=lambda x: (x.get('category', ''), x.get('service_name', '')))


def get_service_by_id(sid):
    doc = _col('services').document(str(sid)).get()
    return _doc_to_dict(doc) if doc.exists else None


def create_service(data):
    ref = _col('services').document()
    data['id'] = ref.id
    data['created_at'] = datetime.now(timezone.utc).isoformat()
    ref.set(data)
    return ref.id


def update_service(sid, data):
    _col('services').document(str(sid)).update(data)


def delete_service(sid):
    _col('services').document(str(sid)).delete()


def get_services_by_ids(ids):
    result = []
    for sid in ids:
        doc = _col('services').document(str(sid)).get()
        if doc.exists:
            d = _doc_to_dict(doc)
            if d.get('is_active'):
                result.append(d)
    return result


# ── Enquiries ─────────────────────────────────────────────────────────────────

def create_enquiry(user_id, selected_services, preferred_date, preferred_time, message):
    ref = _col('enquiries').document()
    ref.set({
        'id': ref.id, 'enquiry_id': ref.id, 'user_id': user_id,
        'selected_services': selected_services, 'preferred_date': preferred_date,
        'preferred_time': preferred_time, 'message': message,
        'status': 'Pending', 'admin_notes': '', 'assigned_employee_id': None,
        'employee_notes': '', 'created_at': datetime.now(timezone.utc).isoformat(),
        'updated_at': datetime.now(timezone.utc).isoformat(),
    })
    return ref.id


def get_enquiry_by_id(eid):
    doc = _col('enquiries').document(str(eid)).get()
    if not doc.exists:
        return None
    enq = _doc_to_dict(doc)
    # Attach user info
    user = get_user_by_id(enq['user_id'])
    if user:
        enq['full_name'] = user.get('full_name', '')
        enq['phone']     = user.get('phone', '')
        enq['email']     = user.get('email', '')
    # Attach employee info
    if enq.get('assigned_employee_id'):
        emp = get_employee_by_id(enq['assigned_employee_id'])
        enq['emp_name'] = emp.get('full_name', '') if emp else ''
    else:
        enq['emp_name'] = ''
    return enq


def get_enquiries_for_user(user_id):
    docs = _col('enquiries').where('user_id', '==', str(user_id)).get()
    enqs = []
    for d in docs:
        enq = _doc_to_dict(d)
        if enq.get('assigned_employee_id'):
            emp = get_employee_by_id(enq['assigned_employee_id'])
            enq['emp_name'] = emp.get('full_name', '') if emp else ''
        else:
            enq['emp_name'] = ''
        enqs.append(enq)
    return enqs


def get_all_enquiries(status_filter=None, search=None):
    docs = _col('enquiries').get()
    enqs = []
    for d in docs:
        enq = _doc_to_dict(d)
        user = get_user_by_id(enq['user_id'])
        if user:
            enq['full_name'] = user.get('full_name', '')
            enq['phone']     = user.get('phone', '')
            enq['email']     = user.get('email', '')
        else:
            enq['full_name'] = enq['phone'] = enq['email'] = ''
        if enq.get('assigned_employee_id'):
            emp = get_employee_by_id(enq['assigned_employee_id'])
            enq['emp_name'] = emp.get('full_name', '') if emp else ''
        else:
            enq['emp_name'] = ''
        if status_filter and enq.get('status') != status_filter:
            continue
        if search:
            s = search.lower()
            if s not in enq.get('full_name', '').lower() and \
               s not in enq.get('phone', '').lower() and \
               s not in enq.get('selected_services', '').lower():
                continue
        enqs.append(enq)
    return sorted(enqs, key=lambda x: x.get('created_at', ''), reverse=True)
    data['updated_at'] = datetime.now(timezone.utc).isoformat()
    _col('enquiries').document(str(eid)).update(data)


def update_enquiry(eid, data):
    data['updated_at'] = datetime.now(timezone.utc).isoformat()
    _col('enquiries').document(str(eid)).update(data)


def delete_enquiry(eid):
    _col('enquiries').document(str(eid)).delete()


def get_enquiries_for_date(date_str):
    docs = _col('enquiries').where('preferred_date', '==', date_str).get()
    enqs = []
    for d in docs:
        enq = _doc_to_dict(d)
        user = get_user_by_id(enq['user_id'])
        if user:
            enq['full_name'] = user.get('full_name', '')
            enq['phone']     = user.get('phone', '')
        if enq.get('assigned_employee_id'):
            emp = get_employee_by_id(enq['assigned_employee_id'])
            enq['emp_name'] = emp.get('full_name', '') if emp else ''
        else:
            enq['emp_name'] = ''
        enqs.append(enq)
    return sorted(enqs, key=lambda x: x.get('preferred_time') or '')


# ── Employees ─────────────────────────────────────────────────────────────────

def get_employee_by_id(eid):
    doc = _col('employees').document(str(eid)).get()
    return _doc_to_dict(doc) if doc.exists else None


def get_employee_by_identifier(identifier):
    docs = _col('employees').get()
    for doc in docs:
        e = _doc_to_dict(doc)
        if not e.get('is_active'):
            continue
        if e.get('username') == identifier or e.get('email') == identifier:
            return e
    return None


def get_all_employees(active_only=False):
    docs = _col('employees').get()
    emps = [_doc_to_dict(d) for d in docs]
    if active_only:
        emps = [e for e in emps if e.get('is_active')]
    return sorted(emps, key=lambda x: x.get('full_name', '').lower())


def create_employee(data):
    ref = _col('employees').document()
    data['id'] = ref.id
    data['created_at'] = datetime.now(timezone.utc).isoformat()
    ref.set(data)
    return ref.id


def update_employee(eid, data):
    _col('employees').document(str(eid)).update(data)


def delete_employee(eid):
    # Unassign from enquiries
    docs = _col('enquiries').where('assigned_employee_id', '==', str(eid)).get()
    for d in docs:
        d.reference.update({'assigned_employee_id': None})
    _col('employees').document(str(eid)).delete()


# ── Reviews ───────────────────────────────────────────────────────────────────

def get_all_reviews():
    docs = _col('reviews').get()
    reviews = []
    for d in docs:
        r = _doc_to_dict(d)
        user = get_user_by_id(r['user_id'])
        if user:
            r['full_name'] = user.get('full_name', '')
            r['phone']     = user.get('phone', '')
        reviews.append(r)
    return reviews


def get_review_by_user(user_id):
    docs = _col('reviews').where('user_id', '==', str(user_id)).limit(1).get()
    return _doc_to_dict(docs[0]) if docs else None


def create_review(user_id, rating, comment):
    ref = _col('reviews').document()
    ref.set({
        'id': ref.id, 'user_id': str(user_id), 'rating': rating,
        'comment': comment, 'created_at': datetime.now(timezone.utc).isoformat(),
    })
    return ref.id


def update_review(user_id, rating, comment):
    docs = _col('reviews').where('user_id', '==', str(user_id)).limit(1).get()
    if docs:
        docs[0].reference.update({'rating': rating, 'comment': comment})


def delete_review(rid):
    _col('reviews').document(str(rid)).delete()


def get_recent_reviews(limit=6):
    docs = _col('reviews').get()
    reviews = []
    for d in docs:
        r = _doc_to_dict(d)
        user = get_user_by_id(r['user_id'])
        r['full_name'] = user.get('full_name', '') if user else ''
        reviews.append(r)
    return reviews


# ── Settings ──────────────────────────────────────────────────────────────────

def get_setting(key, default=''):
    doc = _col('settings').document(key).get()
    return doc.to_dict().get('value', default) if doc.exists else default


def set_setting(key, value):
    _col('settings').document(key).set({'key': key, 'value': value})


def get_all_settings():
    docs = _col('settings').get()
    return {d.id: d.to_dict().get('value', '') for d in docs}


# ── Gallery ───────────────────────────────────────────────────────────────────

def get_all_gallery():
    docs = _col('gallery').get()
    items = [_doc_to_dict(d) for d in docs]
    return sorted(items, key=lambda x: x.get('created_at', ''), reverse=True)


def add_gallery_photo(filename, caption):
    ref = _col('gallery').document()
    ref.set({'id': ref.id, 'filename': filename, 'caption': caption,
             'created_at': datetime.now(timezone.utc).isoformat()})
    return ref.id


def delete_gallery_photo(gid):
    _col('gallery').document(str(gid)).delete()


def get_gallery_photo(gid):
    doc = _col('gallery').document(str(gid)).get()
    return _doc_to_dict(doc) if doc.exists else None


# ── Blocked Slots ─────────────────────────────────────────────────────────────

def get_all_blocked_slots():
    docs = _col('blocked_slots').get()
    items = [_doc_to_dict(d) for d in docs]
    return sorted(items, key=lambda x: (x.get('block_date', ''), x.get('block_time', '') or ''))


def add_blocked_slot(block_date, block_time, reason):
    ref = _col('blocked_slots').document()
    ref.set({'id': ref.id, 'block_date': block_date, 'block_time': block_time,
             'reason': reason, 'created_at': datetime.now(timezone.utc).isoformat()})
    return ref.id


def delete_blocked_slot(bid):
    _col('blocked_slots').document(str(bid)).delete()


def delete_blocked_slots_for_date(block_date):
    docs = _col('blocked_slots').where('block_date', '==', block_date).get()
    for d in docs:
        d.reference.delete()


def get_blocked_slot(block_date, block_time):
    docs = _col('blocked_slots').where('block_date', '==', block_date).where('block_time', '==', block_time).limit(1).get()
    return _doc_to_dict(docs[0]) if docs else None


# ── Offers ────────────────────────────────────────────────────────────────────

def get_all_offers():
    docs = _col('offers').get()
    items = [_doc_to_dict(d) for d in docs]
    return sorted(items, key=lambda x: x.get('created_at', ''), reverse=True)


def get_active_offers(today_str):
    docs = _col('offers').get()
    result = []
    for d in docs:
        o = _doc_to_dict(d)
        if not o.get('is_active'):
            continue
        vf = o.get('valid_from') or ''
        vu = o.get('valid_until') or ''
        if (not vf or vf <= today_str) and (not vu or vu >= today_str):
            result.append(o)
    return result


def get_offer_by_id(oid):
    doc = _col('offers').document(str(oid)).get()
    return _doc_to_dict(doc) if doc.exists else None


def create_offer(data):
    ref = _col('offers').document()
    data['id'] = ref.id
    data['created_at'] = datetime.now(timezone.utc).isoformat()
    ref.set(data)
    return ref.id


def update_offer(oid, data):
    _col('offers').document(str(oid)).update(data)


def delete_offer(oid):
    _col('offers').document(str(oid)).delete()


# ── Coupons ───────────────────────────────────────────────────────────────────

def get_all_coupons():
    docs = _col('coupons').get()
    items = [_doc_to_dict(d) for d in docs]
    return sorted(items, key=lambda x: x.get('created_at', ''), reverse=True)


def get_coupon_by_code(code):
    docs = _col('coupons').where('code', '==', code.upper()).limit(1).get()
    return _doc_to_dict(docs[0]) if docs else None


def create_coupon(data):
    ref = _col('coupons').document()
    data['id'] = ref.id
    data['created_at'] = datetime.now(timezone.utc).isoformat()
    ref.set(data)
    return ref.id


def update_coupon_by_code(code, data):
    docs = _col('coupons').where('code', '==', code.upper()).limit(1).get()
    if docs:
        docs[0].reference.update(data)


def delete_coupon(cid):
    _col('coupons').document(str(cid)).delete()


# ── Attendance ────────────────────────────────────────────────────────────────

def clock_in(employee_id):
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    existing = _col('attendance').where('employee_id', '==', str(employee_id)).where('date', '==', today).limit(1).get()
    if existing:
        return None, 'Already clocked in today.'
    now = datetime.now(timezone.utc)
    clock_in_time = now.strftime('%H:%M')
    # Determine status: late if after 09:30
    hour, minute = now.hour, now.minute
    status = 'Late' if (hour > 9 or (hour == 9 and minute > 30)) else 'Present'
    ref = _col('attendance').document()
    ref.set({
        'id': ref.id, 'employee_id': str(employee_id), 'date': today,
        'clock_in': clock_in_time, 'clock_out': None, 'status': status,
        'total_hours': None, 'overtime_hours': 0.0,
        'created_at': now.isoformat(),
    })
    return ref.id, None


def clock_out(employee_id):
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    docs = _col('attendance').where('employee_id', '==', str(employee_id)).where('date', '==', today).limit(1).get()
    if not docs:
        return None, 'No clock-in record found for today.'
    doc = docs[0]
    rec = doc.to_dict()
    if rec.get('clock_out'):
        return None, 'Already clocked out today.'
    now = datetime.now(timezone.utc)
    clock_out_time = now.strftime('%H:%M')
    # Calculate total hours
    try:
        ci_h, ci_m = map(int, rec['clock_in'].split(':'))
        co_h, co_m = map(int, clock_out_time.split(':'))
        total_mins = (co_h * 60 + co_m) - (ci_h * 60 + ci_m)
        total_hours = round(total_mins / 60, 2) if total_mins > 0 else 0.0
        # Standard day = 9 hours; overtime beyond that
        overtime = round(max(0, total_hours - 9), 2)
        # Half day if < 5 hours
        status = rec.get('status', 'Present')
        if total_hours < 5:
            status = 'Half Day'
    except Exception:
        total_hours, overtime = 0.0, 0.0
        status = rec.get('status', 'Present')
    doc.reference.update({
        'clock_out': clock_out_time, 'total_hours': total_hours,
        'overtime_hours': overtime, 'status': status,
    })
    return doc.id, None


def get_attendance_today(employee_id):
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    docs = _col('attendance').where('employee_id', '==', str(employee_id)).where('date', '==', today).limit(1).get()
    return _doc_to_dict(docs[0]) if docs else None


def get_attendance_for_month(employee_id, year, month):
    prefix = f'{year}-{month:02d}'
    docs = _col('attendance').where('employee_id', '==', str(employee_id)).get()
    records = [_doc_to_dict(d) for d in docs if _doc_to_dict(d).get('date', '').startswith(prefix)]
    return sorted(records, key=lambda x: x.get('date', ''))


def get_all_attendance_for_date(date_str):
    docs = _col('attendance').where('date', '==', date_str).get()
    records = []
    for d in docs:
        rec = _doc_to_dict(d)
        emp = get_employee_by_id(rec['employee_id'])
        rec['emp_name'] = emp.get('full_name', '') if emp else ''
        rec['emp_role'] = emp.get('role', '') if emp else ''
        records.append(rec)
    return sorted(records, key=lambda x: x.get('emp_name', ''))


def get_all_attendance_for_month(year, month):
    prefix = f'{year}-{month:02d}'
    docs = _col('attendance').get()
    records = []
    for d in docs:
        rec = _doc_to_dict(d)
        if rec.get('date', '').startswith(prefix):
            emp = get_employee_by_id(rec['employee_id'])
            rec['emp_name'] = emp.get('full_name', '') if emp else ''
            rec['emp_role'] = emp.get('role', '') if emp else ''
            records.append(rec)
    return sorted(records, key=lambda x: (x.get('emp_name', ''), x.get('date', '')))


def admin_mark_attendance(employee_id, date_str, status, clock_in=None, clock_out=None):
    docs = _col('attendance').where('employee_id', '==', str(employee_id)).where('date', '==', date_str).limit(1).get()
    total_hours = None
    overtime = 0.0
    if clock_in and clock_out:
        try:
            ci_h, ci_m = map(int, clock_in.split(':'))
            co_h, co_m = map(int, clock_out.split(':'))
            total_mins = (co_h * 60 + co_m) - (ci_h * 60 + ci_m)
            total_hours = round(total_mins / 60, 2) if total_mins > 0 else 0.0
            overtime = round(max(0, total_hours - 9), 2)
        except Exception:
            pass
    data = {
        'employee_id': str(employee_id), 'date': date_str, 'status': status,
        'clock_in': clock_in, 'clock_out': clock_out,
        'total_hours': total_hours, 'overtime_hours': overtime,
    }
    if docs:
        docs[0].reference.update(data)
        return docs[0].id
    else:
        ref = _col('attendance').document()
        data['id'] = ref.id
        data['created_at'] = datetime.now(timezone.utc).isoformat()
        ref.set(data)
        return ref.id


# ── Salary ────────────────────────────────────────────────────────────────────

def calculate_salary(employee_id, year, month):
    emp = get_employee_by_id(str(employee_id))
    if not emp:
        return None
    monthly_salary = float(emp.get('monthly_salary', 0) or 0)
    working_days = int(emp.get('working_days_per_month', 26) or 26)
    overtime_rate = float(emp.get('overtime_rate', 150) or 150)
    per_day = round(monthly_salary / working_days, 2) if working_days else 0

    records = get_attendance_for_month(employee_id, year, month)
    present = sum(1 for r in records if r.get('status') in ('Present', 'Late'))
    half_day = sum(1 for r in records if r.get('status') == 'Half Day')
    absent = sum(1 for r in records if r.get('status') == 'Absent')
    on_leave = sum(1 for r in records if r.get('status') == 'Leave')
    total_overtime = sum(float(r.get('overtime_hours') or 0) for r in records)

    absent_deduction = round(absent * per_day, 2)
    half_day_deduction = round(half_day * per_day * 0.5, 2)
    overtime_amount = round(total_overtime * overtime_rate, 2)
    net_salary = round(monthly_salary - absent_deduction - half_day_deduction + overtime_amount, 2)

    return {
        'employee_id': str(employee_id), 'emp_name': emp.get('full_name', ''),
        'emp_role': emp.get('role', ''), 'month': f'{year}-{month:02d}',
        'monthly_salary': monthly_salary, 'working_days': working_days,
        'per_day': per_day, 'present': present, 'half_day': half_day,
        'absent': absent, 'on_leave': on_leave,
        'total_overtime': round(total_overtime, 2), 'overtime_rate': overtime_rate,
        'overtime_amount': overtime_amount, 'absent_deduction': absent_deduction,
        'half_day_deduction': half_day_deduction, 'net_salary': net_salary,
    }


def get_salary_record(employee_id, month_str):
    docs = _col('salary').where('employee_id', '==', str(employee_id)).where('month', '==', month_str).limit(1).get()
    return _doc_to_dict(docs[0]) if docs else None


def save_salary_record(data):
    existing = _col('salary').where('employee_id', '==', str(data['employee_id'])).where('month', '==', data['month']).limit(1).get()
    if existing:
        existing[0].reference.update(data)
        return existing[0].id
    ref = _col('salary').document()
    data['id'] = ref.id
    data['generated_at'] = datetime.now(timezone.utc).isoformat()
    data['paid'] = data.get('paid', False)
    ref.set(data)
    return ref.id


def get_all_salary_records(month_str=None):
    q = _col('salary')
    if month_str:
        q = q.where('month', '==', month_str)
    docs = q.get()
    return [_doc_to_dict(d) for d in docs]


def mark_salary_paid(salary_id, paid=True):
    _col('salary').document(str(salary_id)).update({'paid': paid, 'paid_at': datetime.now(timezone.utc).isoformat()})


# ── Leave Requests ────────────────────────────────────────────────────────────

def create_leave_request(employee_id, from_date, to_date, reason, leave_type='Casual'):
    ref = _col('leave_requests').document()
    ref.set({
        'id': ref.id, 'employee_id': str(employee_id),
        'from_date': from_date, 'to_date': to_date,
        'reason': reason, 'leave_type': leave_type,
        'status': 'Pending',
        'created_at': datetime.now(timezone.utc).isoformat(),
    })
    return ref.id


def get_leave_requests_for_employee(employee_id):
    docs = _col('leave_requests').where('employee_id', '==', str(employee_id)).get()
    return sorted([_doc_to_dict(d) for d in docs], key=lambda x: x.get('created_at', ''), reverse=True)


def get_all_leave_requests(status=None):
    q = _col('leave_requests')
    if status:
        q = q.where('status', '==', status)
    docs = q.get()
    records = []
    for d in docs:
        rec = _doc_to_dict(d)
        emp = get_employee_by_id(rec['employee_id'])
        rec['emp_name'] = emp.get('full_name', '') if emp else ''
        rec['emp_role'] = emp.get('role', '') if emp else ''
        records.append(rec)
    return sorted(records, key=lambda x: x.get('created_at', ''), reverse=True)


def update_leave_request(leave_id, status, admin_note=''):
    _col('leave_requests').document(str(leave_id)).update({
        'status': status, 'admin_note': admin_note,
        'reviewed_at': datetime.now(timezone.utc).isoformat(),
    })
    # If approved, mark attendance as Leave for those dates
    if status == 'Approved':
        doc = _col('leave_requests').document(str(leave_id)).get()
        if doc.exists:
            rec = doc.to_dict()
            try:
                from datetime import date as _date, timedelta
                start = _date.fromisoformat(rec['from_date'])
                end = _date.fromisoformat(rec['to_date'])
                current = start
                while current <= end:
                    admin_mark_attendance(rec['employee_id'], current.isoformat(), 'Leave')
                    current += timedelta(days=1)
            except Exception:
                pass


# ── Legacy query/execute shim (kept so nothing breaks) ───────────────────────
# These are no longer used — all routes now call the functions above directly.

def query(sql, args=(), one=False):
    raise NotImplementedError('Use Firestore helper functions instead of query()')


def execute(sql, args=()):
    raise NotImplementedError('Use Firestore helper functions instead of execute()')
