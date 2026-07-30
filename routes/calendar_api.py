from datetime import date, datetime, timedelta
from flask import Blueprint, jsonify, request, session
from functools import wraps
import db as _db
from collections import defaultdict
import threading
import time

cal_api = Blueprint('cal_api', __name__, url_prefix='/api/calendar')

_coupon_attempts = defaultdict(list)
_coupon_lock     = threading.Lock()

def _coupon_rate_limited(ip):
    now = time.time()
    with _coupon_lock:
        attempts = [t for t in _coupon_attempts[ip] if now - t < 300]
        _coupon_attempts[ip] = attempts
        if len(attempts) >= 10:
            return True
        _coupon_attempts[ip].append(now)
    return False

WEEKDAY_SLOTS = [
    '9:00 AM','10:00 AM','11:00 AM','12:00 PM',
    '2:00 PM','3:00 PM','4:00 PM','5:00 PM','6:00 PM','7:00 PM'
]
SUNDAY_SLOTS = [
    '10:00 AM','11:00 AM','12:00 PM',
    '2:00 PM','3:00 PM','4:00 PM'
]
MAX_PER_SLOT = 3


def _slots_for_date(date_str: str):
    try:
        d = date.fromisoformat(date_str)
    except ValueError:
        return []
    is_sunday = d.weekday() == 6
    return SUNDAY_SLOTS if is_sunday else WEEKDAY_SLOTS


def _booked_counts(date_str: str) -> dict:
    enqs = _db.get_enquiries_for_date(date_str)
    counts = {}
    for e in enqs:
        if e.get('status') in ('Cancelled', 'Rejected', 'Closed'):
            continue
        t = e.get('preferred_time')
        if t:
            counts[t] = counts.get(t, 0) + 1
    return counts


def _blocked_times(date_str: str) -> set:
    slots = _db.get_all_blocked_slots()
    result = set()
    for r in slots:
        if str(r.get('block_date', ''))[:10] != date_str:
            continue
        t = r.get('block_time')
        if not t:
            continue
        try:
            parsed = datetime.strptime(t, '%H:%M')
            result.add(parsed.strftime('%I:%M %p').lstrip('0'))
        except ValueError:
            result.add(t)
    return result


def _is_date_blocked(date_str: str) -> bool:
    slots = _db.get_all_blocked_slots()
    for r in slots:
        if str(r.get('block_date', ''))[:10] == date_str and not r.get('block_time'):
            return True
    return False


# ── Slot availability ────────────────────────────────────────────────────────
@cal_api.route('/slots')
def slots():
    date_str = request.args.get('date', '')
    if not date_str:
        return jsonify({'error': 'date required'}), 400
    try:
        req_date = date.fromisoformat(date_str)
    except ValueError:
        return jsonify({'error': 'invalid date'}), 400
    if req_date > date.today() + timedelta(days=365):
        return jsonify({'error': 'date too far in future'}), 400

    today = date.today()
    if req_date < today:
        return jsonify({'date': date_str, 'slots': [], 'past': True})
    if _is_date_blocked(date_str):
        return jsonify({'date': date_str, 'slots': [], 'blocked': True,
                        'message': 'Salon is closed on this day'})

    base_slots = _slots_for_date(date_str)
    booked     = _booked_counts(date_str)
    blocked_t  = _blocked_times(date_str)
    now        = datetime.now()

    result = []
    for t in base_slots:
        if t in blocked_t:
            result.append({'time': t, 'available': False, 'reason': 'blocked',
                           'booked': 0, 'max': MAX_PER_SLOT})
            continue
        if req_date == today:
            try:
                slot_dt = datetime.strptime(f"{date_str} {t}", "%Y-%m-%d %I:%M %p")
                if slot_dt <= now:
                    result.append({'time': t, 'available': False, 'reason': 'past',
                                   'booked': MAX_PER_SLOT, 'max': MAX_PER_SLOT})
                    continue
            except ValueError:
                pass
        count = booked.get(t, 0)
        result.append({
            'time': t, 'available': count < MAX_PER_SLOT,
            'booked': count, 'max': MAX_PER_SLOT,
            'remaining': max(0, MAX_PER_SLOT - count)
        })
    return jsonify({'date': date_str, 'slots': result})


@cal_api.route('/month-availability')
def month_availability():
    try:
        year  = int(request.args.get('year',  date.today().year))
        month = int(request.args.get('month', date.today().month))
    except (ValueError, TypeError):
        return jsonify({'error': 'invalid params'}), 400
    if not (1 <= month <= 12) or not (2020 <= year <= date.today().year + 2):
        return jsonify({'error': 'invalid year or month'}), 400

    today = date.today()
    first = date(year, month, 1)
    last  = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year + 1, 1, 1) - timedelta(days=1)

    blocked_days = set()
    all_blocks = _db.get_all_blocked_slots()
    for b in all_blocks:
        ds = str(b.get('block_date', ''))[:10]
        if first.isoformat() <= ds <= last.isoformat() and not b.get('block_time'):
            blocked_days.add(ds)

    result = {}
    cur = first
    while cur <= last:
        ds = cur.isoformat()
        if cur < today:
            result[ds] = 'past'
        elif ds in blocked_days:
            result[ds] = 'closed'
        else:
            base      = _slots_for_date(ds)
            booked    = _booked_counts(ds)
            total_cap = len(base) * MAX_PER_SLOT
            total_bk  = sum(booked.get(t, 0) for t in base)
            if total_bk >= total_cap:
                result[ds] = 'full'
            elif total_bk >= total_cap * 0.7:
                result[ds] = 'limited'
            else:
                result[ds] = 'available'
        cur += timedelta(days=1)

    return jsonify({'year': year, 'month': month, 'days': result})


@cal_api.route('/offers')
def offers():
    date_str = request.args.get('date', '')
    if not date_str:
        return jsonify({'error': 'date required'}), 400
    try:
        date.fromisoformat(date_str)
    except ValueError:
        return jsonify({'error': 'invalid date'}), 400
    active = _db.get_active_offers(date_str)
    result = [{
        'id': o.get('id'), 'title': o.get('title'),
        'description': o.get('description') or '',
        'discount_text': o.get('discount_text') or '',
        'discount_percent': float(o.get('discount_percent') or 0),
        'applicable_services': o.get('applicable_services') or '',
    } for o in active]
    return jsonify({'date': date_str, 'offers': result})


@cal_api.route('/coupon/validate', methods=['POST'])
def validate_coupon():
    ip = request.remote_addr
    if _coupon_rate_limited(ip):
        return jsonify({'valid': False, 'message': 'Too many attempts. Please wait.'}), 429
    data = request.get_json(silent=True) or {}
    code = (data.get('code') or '').strip().upper()
    if not code:
        return jsonify({'valid': False, 'message': 'Please enter a coupon code.'})
    today_str = date.today().isoformat()
    coupon = _db.get_coupon_by_code(code)
    if not coupon or not coupon.get('is_active'):
        return jsonify({'valid': False, 'message': 'Invalid or expired coupon code.'})
    vu = coupon.get('valid_until')
    if vu and str(vu)[:10] < today_str:
        return jsonify({'valid': False, 'message': 'Invalid or expired coupon code.'})
    pct = float(coupon.get('discount_percent') or 0)
    if not pct:
        return jsonify({'valid': False, 'message': 'This coupon has no discount value.'})
    max_uses = int(coupon.get('max_uses') or 0)
    used     = int(coupon.get('used_count') or 0)
    if max_uses > 0 and used >= max_uses:
        return jsonify({'valid': False, 'message': 'This coupon has reached its usage limit.'})
    return jsonify({
        'valid': True, 'discount_percent': pct,
        'discount_text': f'{pct:.0f}% OFF',
        'applicable_services': '',
        'message': f'Coupon applied! {pct:.0f}% OFF your total bill'
    })


# ── Admin-only endpoints ──────────────────────────────────────────────────────
def _admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            return jsonify({'error': 'unauthorized'}), 403
        if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
            origin  = request.headers.get('Origin', '')
            referer = request.headers.get('Referer', '')
            host    = request.host_url.rstrip('/')
            if origin and not origin.startswith(host):
                return jsonify({'error': 'forbidden'}), 403
            if not origin and referer and not referer.startswith(host):
                return jsonify({'error': 'forbidden'}), 403
        return f(*args, **kwargs)
    return decorated


@cal_api.route('/admin/appointments')
@_admin_required
def admin_appointments():
    start = request.args.get('start', date.today().isoformat())
    end   = request.args.get('end',   (date.today() + timedelta(days=30)).isoformat())
    all_enqs = _db.get_all_enquiries()
    COLOR_MAP = {
        'Confirmed': '#22c55e', 'Pending': '#f59e0b',
        'Closed': '#3b82f6',    'Contacted': '#8b5cf6',
    }
    events = []
    for e in all_enqs:
        ds = str(e.get('preferred_date', ''))[:10]
        if not ds or ds < start or ds > end:
            continue
        t = e.get('preferred_time') or '09:00 AM'
        try:
            t24 = datetime.strptime(t, '%I:%M %p').strftime('%H:%M')
        except ValueError:
            t24 = '09:00'
        start_iso = f"{ds}T{t24}:00"
        status = e.get('status', '')
        events.append({
            'id':    e.get('id'),
            'title': f"{e.get('full_name','?')} — {str(e.get('selected_services',''))[:30]}",
            'start': start_iso,
            'color': COLOR_MAP.get(status, '#6b7280'),
            'extendedProps': {
                'customer': e.get('full_name',''),
                'phone':    e.get('phone',''),
                'services': e.get('selected_services',''),
                'time':     e.get('preferred_time') or 'Flexible',
                'status':   status,
            }
        })
    return jsonify(events)


@cal_api.route('/admin/block', methods=['POST'])
@_admin_required
def block_slot():
    data   = request.get_json(silent=True) or {}
    bdate  = data.get('date', '')
    btime  = data.get('time') or None
    reason = str(data.get('reason', ''))[:255]
    if not bdate:
        return jsonify({'error': 'date required'}), 400
    try:
        date.fromisoformat(bdate)
    except ValueError:
        return jsonify({'error': 'invalid date'}), 400
    _db.add_blocked_slot(bdate, btime, reason)
    _emit_calendar_update()
    return jsonify({'ok': True})


@cal_api.route('/admin/unblock', methods=['POST'])
@_admin_required
def unblock_slot():
    data  = request.get_json(silent=True) or {}
    bdate = data.get('date', '')
    btime = data.get('time') or None
    if not bdate:
        return jsonify({'error': 'date required'}), 400
    if btime:
        slot = _db.get_blocked_slot(bdate, btime)
        if slot:
            _db.delete_blocked_slot(slot['id'])
    else:
        _db.delete_blocked_slots_for_date(bdate)
    _emit_calendar_update()
    return jsonify({'ok': True})


@cal_api.route('/admin/blocked-dates')
@_admin_required
def blocked_dates():
    rows = _db.get_all_blocked_slots()
    result = [{'id': r.get('id'), 'block_date': str(r.get('block_date',''))[:10],
               'block_time': r.get('block_time') or '', 'reason': r.get('reason') or ''}
              for r in rows]
    return jsonify(result)


def _emit_calendar_update():
    try:
        from app import socketio
        socketio.emit('calendar_update', {'ts': datetime.now().isoformat()})
    except (ImportError, RuntimeError):
        pass
