"""
calendar_api.py — Slot availability API + Socket.IO real-time events.
All times are stored/returned as strings like '9:00 AM'.
"""
from datetime import date, datetime, timedelta
from flask import Blueprint, jsonify, request, session
from functools import wraps
from db import query, execute
from collections import defaultdict
import threading
import time

try:
    from flask_wtf.csrf import exempt as csrf_exempt
except ImportError:
    csrf_exempt = None

cal_api = Blueprint('cal_api', __name__, url_prefix='/api/calendar')

# ── Rate limiting for public endpoints ───────────────────────────────────────
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

# ── Salon schedule constants ──────────────────────────────────────────────────
# Default slots — overridable via salon_config keys:
#   weekday_slots  (comma-separated, e.g. "9:00 AM,10:00 AM,...")
#   sunday_slots
WEEKDAY_SLOTS = [
    '9:00 AM','10:00 AM','11:00 AM','12:00 PM',
    '2:00 PM','3:00 PM','4:00 PM','5:00 PM','6:00 PM','7:00 PM'
]
SUNDAY_SLOTS = [
    '10:00 AM','11:00 AM','12:00 PM',
    '2:00 PM','3:00 PM','4:00 PM'
]
MAX_PER_SLOT = 3   # configurable via salon_config


def _get_config(key, default):
    row = query("SELECT value FROM salon_config WHERE `key`=%s", (key,), one=True)
    return row['value'] if row else default


def _max_per_slot():
    try:
        return int(_get_config('max_per_slot', MAX_PER_SLOT))
    except Exception:
        return MAX_PER_SLOT


def _slots_for_date(date_str: str):
    """Return base slot list for a given date string (YYYY-MM-DD).
    Respects custom slots stored in salon_config (weekday_slots / sunday_slots).
    """
    try:
        d = date.fromisoformat(date_str)
    except ValueError:
        return []
    is_sunday = d.weekday() == 6
    cfg_key   = 'sunday_slots' if is_sunday else 'weekday_slots'
    custom    = _get_config(cfg_key, '')
    if custom:
        return [s.strip() for s in custom.split(',') if s.strip()]
    return SUNDAY_SLOTS if is_sunday else WEEKDAY_SLOTS


def _booked_counts(date_str: str) -> dict:
    """Return {time_str: count} for active (non-cancelled/rejected) bookings."""
    rows = query(
        "SELECT preferred_time, COUNT(*) as c FROM appointments "
        "WHERE preferred_date=%s AND status NOT IN ('Cancelled','Rejected') "
        "GROUP BY preferred_time",
        (date_str,)
    )
    return {r['preferred_time']: int(r['c']) for r in rows if r['preferred_time']}


def _blocked_times(date_str: str) -> set:
    rows = query(
        "SELECT block_time FROM blocked_slots WHERE block_date=%s",
        (date_str,)
    )
    result = set()
    for r in rows:
        t = r['block_time']
        if not t:
            continue
        try:
            from datetime import datetime as _dt
            parsed = _dt.strptime(t, '%H:%M')
            # Use lstrip to avoid platform-specific %-I issues
            result.add(parsed.strftime('%I:%M %p').lstrip('0'))
        except Exception:
            result.add(t)
    return result


def _is_date_blocked(date_str: str) -> bool:
    row = query(
        "SELECT id FROM blocked_slots WHERE block_date=%s AND block_time IS NULL",
        (date_str,), one=True
    )
    return bool(row)


# ── Public slot availability endpoint ────────────────────────────────────────

@cal_api.route('/slots')
def slots():
    date_str = request.args.get('date', '')
    if not date_str:
        return jsonify({'error': 'date required'}), 400
    try:
        req_date = date.fromisoformat(date_str)
    except ValueError:
        return jsonify({'error': 'invalid date'}), 400
    # Reject dates more than 1 year in the future
    if req_date > date.today() + timedelta(days=365):
        return jsonify({'error': 'date too far in future'}), 400

    today = date.today()
    if req_date < today:
        return jsonify({'date': date_str, 'slots': [], 'past': True})

    if _is_date_blocked(date_str):
        return jsonify({'date': date_str, 'slots': [], 'blocked': True,
                        'message': 'Salon is closed on this day'})

    base_slots  = _slots_for_date(date_str)
    booked      = _booked_counts(date_str)
    blocked_t   = _blocked_times(date_str)
    max_slot    = _max_per_slot()
    now         = datetime.now()

    result = []
    for t in base_slots:
        if t in blocked_t:
            result.append({'time': t, 'available': False, 'reason': 'blocked',
                           'booked': 0, 'max': max_slot})
            continue
        # For today, skip slots that are at or before current time
        if req_date == today:
            try:
                slot_dt = datetime.strptime(f"{date_str} {t}", "%Y-%m-%d %I:%M %p")
                if slot_dt <= now:
                    result.append({'time': t, 'available': False, 'reason': 'past',
                                   'booked': max_slot, 'max': max_slot})
                    continue
            except Exception:
                pass
        count = booked.get(t, 0)
        result.append({
            'time': t,
            'available': count < max_slot,
            'booked': count,
            'max': max_slot,
            'remaining': max(0, max_slot - count)
        })

    return jsonify({'date': date_str, 'slots': result})


@cal_api.route('/month-availability')
def month_availability():
    try:
        year  = int(request.args.get('year',  date.today().year))
        month = int(request.args.get('month', date.today().month))
    except ValueError:
        return jsonify({'error': 'invalid params'}), 400
    if not (1 <= month <= 12) or not (2020 <= year <= date.today().year + 2):
        return jsonify({'error': 'invalid year or month'}), 400

    today = date.today()
    # First and last day of month
    first = date(year, month, 1)
    if month == 12:
        last = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)

    # Fetch all bookings in range
    rows = query(
        "SELECT preferred_date, preferred_time, COUNT(*) as c FROM appointments "
        "WHERE preferred_date >= %s AND preferred_date <= %s "
        "AND status NOT IN ('Cancelled','Rejected') "
        "GROUP BY preferred_date, preferred_time",
        (first.isoformat(), last.isoformat())
    )
    # Build {date_str: {time: count}}
    date_map: dict = {}
    for r in rows:
        ds = str(r['preferred_date'])[:10]
        date_map.setdefault(ds, {})[r['preferred_time']] = int(r['c'])

    # Blocked full days
    blocked_days = set()
    brows = query(
        "SELECT block_date FROM blocked_slots WHERE block_date >= %s AND block_date <= %s AND block_time IS NULL",
        (first.isoformat(), last.isoformat())
    )
    for b in brows:
        blocked_days.add(str(b['block_date'])[:10])

    max_slot = _max_per_slot()
    result = {}
    cur = first
    while cur <= last:
        ds = cur.isoformat()
        if cur < today:
            result[ds] = 'past'
        elif ds in blocked_days:
            result[ds] = 'closed'
        else:
            base = _slots_for_date(ds)
            booked_map = date_map.get(ds, {})
            total_cap  = len(base) * max_slot
            total_book = sum(booked_map.get(t, 0) for t in base)
            if total_book >= total_cap:
                result[ds] = 'full'
            elif total_book >= total_cap * 0.7:
                result[ds] = 'limited'
            else:
                result[ds] = 'available'
        cur += timedelta(days=1)

    return jsonify({'year': year, 'month': month, 'days': result})


@cal_api.route('/ai-recommend')
def ai_recommend():
    """GET /api/calendar/ai-recommend?duration=30&count=4
    Returns the best upcoming slots based on:
    - Lowest booking density (most remaining capacity)
    - Soonest date (prefer tomorrow over next week)
    - Preferred morning/afternoon spread
    - Avoids fully-booked and blocked slots
    """
    try:
        duration = int(request.args.get('duration', 30))
    except ValueError:
        duration = 30
    try:
        count = min(int(request.args.get('count', 4)), 6)
    except ValueError:
        count = 4

    today    = date.today()
    now      = datetime.now()
    max_slot = _max_per_slot()
    candidates = []

    for offset in range(1, 21):  # look 20 days ahead for better variety
        d  = today + timedelta(days=offset)
        ds = d.isoformat()
        if _is_date_blocked(ds):
            continue
        base      = _slots_for_date(ds)
        booked    = _booked_counts(ds)
        blocked_t = _blocked_times(ds)

        for t in base:
            if t in blocked_t:
                continue
            count_booked = booked.get(t, 0)
            remaining    = max_slot - count_booked
            if remaining <= 0:
                continue

            # Score: lower = better
            # Weight: remaining capacity (inverse), offset (sooner = better)
            capacity_score = (max_slot - remaining) / max_slot  # 0=empty, 1=full
            time_score     = offset * 0.08
            # Slight preference for morning slots (9-12) and afternoon (2-5)
            try:
                slot_hour = datetime.strptime(t, '%I:%M %p').hour
                peak_bonus = -0.05 if slot_hour in (9, 10, 11, 14, 15, 16) else 0
            except Exception:
                peak_bonus = 0

            score = capacity_score + time_score + peak_bonus

            # Determine time-of-day label
            try:
                h = datetime.strptime(t, '%I:%M %p').hour
                if h < 12:   tod = 'Morning'
                elif h < 17: tod = 'Afternoon'
                else:        tod = 'Evening'
            except Exception:
                tod = ''

            candidates.append({
                'date':      ds,
                'time':      t,
                'remaining': remaining,
                'score':     score,
                'day_label': d.strftime('%A'),
                'date_label': d.strftime('%d %b'),
                'tod':       tod,
                'is_today':  False,
                'is_tomorrow': offset == 1,
            })

    candidates.sort(key=lambda x: x['score'])

    # Pick top N ensuring date variety (max 2 per date)
    seen_dates: dict = {}
    top = []
    for c in candidates:
        if len(top) >= count:
            break
        dc = seen_dates.get(c['date'], 0)
        if dc >= 2:
            continue
        seen_dates[c['date']] = dc + 1
        del c['score']
        top.append(c)

    return jsonify({'recommendations': top})


@cal_api.route('/offers')
def offers():
    date_str = request.args.get('date', '')
    if not date_str:
        return jsonify({'error': 'date required'}), 400
    try:
        date.fromisoformat(date_str)
    except ValueError:
        return jsonify({'error': 'invalid date'}), 400

    rows = query(
        "SELECT * FROM offers WHERE is_active=1 AND (valid_from IS NULL OR valid_from <= %s) AND (valid_until IS NULL OR valid_until >= %s)",
        (date_str, date_str)
    )
    result = []
    for r in rows:
        result.append({
            'id': r['id'],
            'title': r.get('title'),
            'description': r.get('description') or '',
            'discount_text': r.get('discount_text') or '',
            'discount_percent': float(r.get('discount_percent') or 0),
            'applicable_services': r.get('applicable_services') or ''
        })

    return jsonify({'date': date_str, 'offers': result})


@cal_api.route('/coupon/validate', methods=['POST'])
def validate_coupon():
    """POST {code} — validates against coupons table, returns discount info."""
    ip = request.remote_addr
    if _coupon_rate_limited(ip):
        return jsonify({'valid': False, 'message': 'Too many attempts. Please wait.'}), 429

    data = request.get_json(silent=True) or {}
    code = (data.get('code') or '').strip().upper()

    if not code:
        return jsonify({'valid': False, 'message': 'Please enter a coupon code.'})

    today_str = date.today().isoformat()

    coupon = query(
        "SELECT * FROM coupons WHERE UPPER(code)=%s AND is_active=1 "
        "AND (valid_until IS NULL OR valid_until >= %s)",
        (code, today_str), one=True
    )

    if not coupon:
        return jsonify({'valid': False, 'message': 'Invalid or expired coupon code.'})

    pct = float(coupon.get('discount_percent') or 0)
    if not pct:
        return jsonify({'valid': False, 'message': 'This coupon has no discount value.'})

    max_uses  = int(coupon.get('max_uses') or 0)
    used      = int(coupon.get('used_count') or 0)
    if max_uses > 0 and used >= max_uses:
        return jsonify({'valid': False, 'message': 'This coupon has reached its usage limit.'})

    return jsonify({
        'valid': True,
        'discount_percent': pct,
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
        # CSRF protection for state-changing requests on the CSRF-exempt blueprint:
        # validate that the request originates from our own origin
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
    """GET /api/calendar/admin/appointments?start=YYYY-MM-DD&end=YYYY-MM-DD
    Returns appointments as FullCalendar-compatible event objects.
    """
    start = request.args.get('start', date.today().isoformat())
    end   = request.args.get('end',   (date.today() + timedelta(days=30)).isoformat())

    rows = query(
        "SELECT a.id, a.preferred_date, a.preferred_time, a.status, "
        "a.selected_services, a.ticket_id, a.total_price, "
        "u.full_name, u.phone, u.email "
        "FROM appointments a JOIN users u ON a.user_id=u.id "
        "WHERE a.preferred_date >= %s AND a.preferred_date <= %s "
        "ORDER BY a.preferred_date, a.preferred_time",
        (start, end)
    )

    COLOR_MAP = {
        'Confirmed':  '#22c55e',
        'Pending':    '#f59e0b',
        'Cancelled':  '#ef4444',
        'Rejected':   '#ef4444',
        'Completed':  '#3b82f6',
        'Checked In': '#8b5cf6',
    }

    events = []
    for r in rows:
        ds = str(r['preferred_date'])[:10]
        t  = r['preferred_time'] or '09:00'
        # Convert "9:00 AM" → "09:00"
        try:
            dt = datetime.strptime(t, '%I:%M %p')
            t24 = dt.strftime('%H:%M')
        except Exception:
            t24 = '09:00'
        start_iso = f"{ds}T{t24}:00"
        # Estimate end (30 min default)
        try:
            end_dt = datetime.strptime(start_iso, '%Y-%m-%dT%H:%M:%S') + timedelta(minutes=30)
            end_iso = end_dt.strftime('%Y-%m-%dT%H:%M:%S')
        except Exception:
            end_iso = start_iso

        status = r['status']
        events.append({
            'id':    r['id'],
            'title': f"{r['full_name']} — {r['selected_services'][:30]}",
            'start': start_iso,
            'end':   end_iso,
            'color': COLOR_MAP.get(status, '#6b7280'),
            'extendedProps': {
                'customer':  r['full_name'],
                'phone':     r['phone'],
                'email':     r['email'],
                'services':  r['selected_services'],
                'time':      r['preferred_time'] or 'Flexible',
                'status':    status,
                'ticket_id': r.get('ticket_id') or '',
                'price':     float(r['total_price'] or 0),
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
    execute(
        "INSERT INTO blocked_slots (block_date, block_time, reason) VALUES (%s,%s,%s)",
        (bdate, btime, reason)
    )
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
        execute("DELETE FROM blocked_slots WHERE block_date=%s AND block_time=%s", (bdate, btime))
    else:
        execute("DELETE FROM blocked_slots WHERE block_date=%s", (bdate,))
    _emit_calendar_update()
    return jsonify({'ok': True})


@cal_api.route('/admin/reschedule', methods=['POST'])
@_admin_required
def reschedule():
    from flask import current_app
    from email_service import send_reschedule_email
    from sms import send_sms
    data = request.get_json(silent=True) or {}
    aid  = data.get('id')
    new_date = data.get('date', '')
    new_time = data.get('time', '')
    if not aid or not new_date:
        return jsonify({'error': 'id and date required'}), 400
    appt = query(
        "SELECT a.*, u.full_name, u.phone, u.email FROM appointments a "
        "JOIN users u ON a.user_id=u.id WHERE a.id=%s", (aid,), one=True
    )
    execute(
        "UPDATE appointments SET preferred_date=%s, preferred_time=%s WHERE id=%s",
        (new_date, new_time or None, aid)
    )
    if appt:
        try:
            fmt_date = date.fromisoformat(new_date).strftime('%d %b %Y')
        except Exception:
            fmt_date = new_date
        fmt_time = new_time or 'Flexible'
        try:
            send_sms(appt['phone'],
                f"Hello {appt['full_name']}, your New Shades appointment has been rescheduled "
                f"to {fmt_date} at {fmt_time}. Please log in to view your updated ticket.")
        except Exception as e:
            current_app.logger.error('Reschedule SMS error: %s', e)
        try:
            send_reschedule_email(appt['email'], appt['full_name'], fmt_date, fmt_time)
        except Exception as e:
            current_app.logger.error('Reschedule email error: %s', e)
    _emit_calendar_update()
    return jsonify({'ok': True})


@cal_api.route('/admin/action', methods=['POST'])
@_admin_required
def admin_action():
    """POST /api/calendar/admin/action
    Body: {id, action}  — accept/reject/checkin/complete
    """
    import uuid as _uuid
    from flask import current_app
    from email_service import send_confirmation_email, send_rejection_email
    from sms import sms_confirmed, sms_rejected

    data   = request.get_json(silent=True) or {}
    aid    = data.get('id')
    action = data.get('action', '')
    if not aid:
        return jsonify({'error': 'id required'}), 400

    appt = query(
        "SELECT a.*, u.full_name, u.phone, u.email FROM appointments a "
        "JOIN users u ON a.user_id=u.id WHERE a.id=%s",
        (aid,), one=True
    )
    if not appt:
        return jsonify({'error': 'not found'}), 404

    try:
        d = appt['preferred_date']
        fmt_date = d.strftime('%d %b %Y') if hasattr(d, 'strftime') else str(d)[:10]
    except Exception:
        fmt_date = str(appt['preferred_date'])[:10]
    fmt_time = appt['preferred_time'] or 'Flexible'

    if action == 'accept':
        ticket_id = str(_uuid.uuid4())[:8].upper()
        try:
            appt_date = date.fromisoformat(str(appt['preferred_date'])[:10])
            expires_at = datetime.combine(appt_date, datetime.max.time()).isoformat()
        except Exception:
            expires_at = None
        execute(
            "UPDATE appointments SET status='Confirmed', ticket_id=%s, ticket_expires_at=%s WHERE id=%s",
            (ticket_id, expires_at, aid)
        )
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

    elif action == 'complete':
        execute("UPDATE appointments SET status='Completed' WHERE id=%s", (aid,))

    _emit_calendar_update()
    return jsonify({'ok': True, 'action': action})


@cal_api.route('/admin/config', methods=['GET', 'POST'])
@_admin_required
def salon_config():
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        allowed_keys = {'max_per_slot', 'slot_duration', 'lunch_start', 'lunch_end',
                        'weekday_slots', 'sunday_slots'}
        for k, v in data.items():
            if k not in allowed_keys:
                continue
            existing = query("SELECT `key` FROM salon_config WHERE `key`=%s", (k,), one=True)
            if existing:
                execute("UPDATE salon_config SET value=%s WHERE `key`=%s", (str(v), k))
            else:
                execute("INSERT INTO salon_config (`key`, value) VALUES (%s,%s)", (k, str(v)))
        return jsonify({'ok': True})
    keys = ['max_per_slot', 'slot_duration', 'lunch_start', 'lunch_end',
            'weekday_slots', 'sunday_slots']
    defaults = {
        'max_per_slot':   '3',
        'slot_duration':  '60',
        'lunch_start':    '1:00 PM',
        'lunch_end':      '2:00 PM',
        'weekday_slots':  ','.join(WEEKDAY_SLOTS),
        'sunday_slots':   ','.join(SUNDAY_SLOTS),
    }
    cfg = {k: _get_config(k, defaults.get(k, '')) for k in keys}
    return jsonify(cfg)


@cal_api.route('/admin/blocked-dates')
@_admin_required
def blocked_dates():
    rows = query("SELECT * FROM blocked_slots ORDER BY block_date, block_time")
    result = []
    for r in rows:
        result.append({
            'id':         r['id'],
            'block_date': str(r['block_date'])[:10],
            'block_time': r['block_time'] or '',
            'reason':     r.get('reason') or '',
        })
    return jsonify(result)


# ── Socket.IO helper ──────────────────────────────────────────────────────────

def _emit_calendar_update():
    """Broadcast calendar_update event to all connected clients."""
    try:
        from app import socketio
        socketio.emit('calendar_update', {'ts': datetime.now().isoformat()})
    except Exception:
        pass
