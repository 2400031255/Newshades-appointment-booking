"""
calendar_api.py — Slot availability API + Socket.IO real-time events.
All times are stored/returned as strings like '9:00 AM'.
"""
from datetime import date, datetime, timedelta
from flask import Blueprint, jsonify, request, session
from functools import wraps
from db import query, execute

try:
    from flask_wtf.csrf import exempt as csrf_exempt
except ImportError:
    csrf_exempt = None

cal_api = Blueprint('cal_api', __name__, url_prefix='/api/calendar')

# ── Salon schedule constants ──────────────────────────────────────────────────
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
    """Return base slot list for a given date string (YYYY-MM-DD)."""
    try:
        d = date.fromisoformat(date_str)
    except ValueError:
        return []
    return SUNDAY_SLOTS if d.weekday() == 6 else WEEKDAY_SLOTS


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
        # Normalise HH:MM (24h) → 'H:MM AM/PM' to match WEEKDAY_SLOTS format
        try:
            from datetime import datetime as _dt
            import platform
            parsed = _dt.strptime(t, '%H:%M')
            fmt = '%#I:%M %p' if platform.system() == 'Windows' else '%-I:%M %p'
            result.add(parsed.strftime(fmt))  # e.g. '9:00 AM'
        except Exception:
            result.add(t)  # already in correct format
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
    """GET /api/calendar/slots?date=YYYY-MM-DD
    Returns slot availability for a given date.
    """
    date_str = request.args.get('date', '')
    if not date_str:
        return jsonify({'error': 'date required'}), 400

    try:
        req_date = date.fromisoformat(date_str)
    except ValueError:
        return jsonify({'error': 'invalid date'}), 400

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
        # For today, skip past times
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
    """GET /api/calendar/month-availability?year=YYYY&month=MM
    Returns per-day availability summary for the calendar grid.
    """
    try:
        year  = int(request.args.get('year',  date.today().year))
        month = int(request.args.get('month', date.today().month))
    except ValueError:
        return jsonify({'error': 'invalid params'}), 400

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
    """GET /api/calendar/ai-recommend?duration=30
    Returns the best 3 upcoming slots based on lowest booking density.
    """
    try:
        duration = int(request.args.get('duration', 30))
    except ValueError:
        duration = 30

    today = date.today()
    max_slot = _max_per_slot()
    candidates = []

    for offset in range(1, 15):  # look 14 days ahead
        d = today + timedelta(days=offset)
        ds = d.isoformat()
        if _is_date_blocked(ds):
            continue
        base   = _slots_for_date(ds)
        booked = _booked_counts(ds)
        blocked_t = _blocked_times(ds)
        for t in base:
            if t in blocked_t:
                continue
            count = booked.get(t, 0)
            if count < max_slot:
                score = count + (offset * 0.1)  # prefer sooner + less booked
                candidates.append({
                    'date': ds,
                    'time': t,
                    'remaining': max_slot - count,
                    'score': score,
                    'day_label': d.strftime('%A, %d %b')
                })

    candidates.sort(key=lambda x: x['score'])
    top = candidates[:3]
    for c in top:
        del c['score']
    return jsonify({'recommendations': top})


@cal_api.route('/offers')
def offers():
    """GET /api/calendar/offers?date=YYYY-MM-DD
    Returns offers active for the given date.
    """
    date_str = request.args.get('date', '')
    if not date_str:
        return jsonify({'error': 'date required'}), 400

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


# ── Admin-only endpoints ──────────────────────────────────────────────────────

def _admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            return jsonify({'error': 'unauthorized'}), 403
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
    """POST /api/calendar/admin/block
    Body: {date, time (optional), reason}
    """
    data   = request.get_json() or {}
    bdate  = data.get('date', '')
    btime  = data.get('time') or None
    reason = data.get('reason', '')
    if not bdate:
        return jsonify({'error': 'date required'}), 400
    execute(
        "INSERT INTO blocked_slots (block_date, block_time, reason) VALUES (%s,%s,%s)",
        (bdate, btime, reason)
    )
    _emit_calendar_update()
    return jsonify({'ok': True})


@cal_api.route('/admin/unblock', methods=['POST'])
@_admin_required
def unblock_slot():
    data  = request.get_json() or {}
    bdate = data.get('date', '')
    btime = data.get('time') or None
    if btime:
        execute("DELETE FROM blocked_slots WHERE block_date=%s AND block_time=%s", (bdate, btime))
    else:
        execute("DELETE FROM blocked_slots WHERE block_date=%s", (bdate,))
    _emit_calendar_update()
    return jsonify({'ok': True})


@cal_api.route('/admin/reschedule', methods=['POST'])
@_admin_required
def reschedule():
    """POST /api/calendar/admin/reschedule
    Body: {id, date, time}  — drag-drop reschedule
    """
    data = request.get_json() or {}
    aid  = data.get('id')
    new_date = data.get('date', '')
    new_time = data.get('time', '')
    if not aid or not new_date:
        return jsonify({'error': 'id and date required'}), 400
    execute(
        "UPDATE appointments SET preferred_date=%s, preferred_time=%s WHERE id=%s",
        (new_date, new_time or None, aid)
    )
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

    data   = request.get_json() or {}
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
        data = request.get_json() or {}
        for k, v in data.items():
            existing = query("SELECT `key` FROM salon_config WHERE `key`=%s", (k,), one=True)
            if existing:
                execute("UPDATE salon_config SET value=%s WHERE `key`=%s", (str(v), k))
            else:
                execute("INSERT INTO salon_config (`key`, value) VALUES (%s,%s)", (k, str(v)))
        return jsonify({'ok': True})
    keys = ['max_per_slot', 'slot_duration', 'lunch_start', 'lunch_end']
    cfg  = {}
    for k in keys:
        cfg[k] = _get_config(k, {'max_per_slot': '3', 'slot_duration': '30',
                                  'lunch_start': '1:00 PM', 'lunch_end': '2:00 PM'}.get(k, ''))
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
