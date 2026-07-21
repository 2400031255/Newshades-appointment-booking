import logging
import html as _html
import re
from markupsafe import Markup
from flask import current_app

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def _valid_email(addr):
    return bool(addr and _EMAIL_RE.match(addr))


def _send(to_email: str, subject: str, body_html: str) -> bool:
    """Send an email via Resend. Returns True on success, False on failure."""
    if not _valid_email(to_email):
        logger.warning('[EMAIL SKIPPED] Invalid address: %s', to_email)
        return False

    api_key = current_app.config.get('RESEND_API_KEY', '')
    from_   = current_app.config.get('EMAIL_FROM', 'New Shades <noreply@yourdomain.com>')

    if not api_key or api_key.startswith('your_'):
        logger.info('[EMAIL SKIPPED] To: %s | Subject: %s', to_email, subject)
        return False

    try:
        import resend
        resend.api_key = api_key
        resend.Emails.send({
            'from':    from_,
            'to':      [to_email],
            'subject': subject,
            'html':    body_html,
        })
        logger.info('[EMAIL SENT] To: %s | Subject: %s', to_email, subject)
        return True
    except Exception as e:
        logger.error('[EMAIL ERROR] To: %s | %s', to_email, e)
        return False


def _base_html(content: Markup) -> str:
    if not isinstance(content, Markup):
        content = Markup(_html.escape(str(content)))
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<style>
  body {{ margin:0; padding:0; background:#0f0d12; font-family:'Helvetica Neue',Arial,sans-serif; color:#f0e6d3; }}
  .wrap {{ max-width:560px; margin:40px auto; background:#1a1510; border-radius:16px; overflow:hidden; border:1px solid rgba(201,168,76,0.2); }}
  .header {{ background:linear-gradient(135deg,#c9a84c,#e8c96a); padding:28px 32px; text-align:center; }}
  .header h1 {{ margin:0; font-size:1.5rem; color:#120e08; font-family:Georgia,serif; letter-spacing:0.04em; }}
  .header p  {{ margin:4px 0 0; font-size:0.75rem; color:rgba(18,14,8,0.65); letter-spacing:0.18em; text-transform:uppercase; }}
  .body  {{ padding:32px; }}
  .body p {{ line-height:1.75; color:rgba(240,230,211,0.82); font-size:0.95rem; margin:0 0 14px; }}
  .detail-box {{ background:rgba(201,168,76,0.07); border:1px solid rgba(201,168,76,0.18); border-radius:12px; padding:18px 20px; margin:20px 0; }}
  .detail-row {{ display:flex; justify-content:space-between; padding:7px 0; border-bottom:1px solid rgba(255,255,255,0.05); font-size:0.88rem; }}
  .detail-row:last-child {{ border-bottom:none; }}
  .detail-label {{ color:rgba(240,230,211,0.5); }}
  .detail-val   {{ color:#fff; font-weight:600; }}
  .footer {{ padding:20px 32px; border-top:1px solid rgba(255,255,255,0.05); text-align:center; color:rgba(240,230,211,0.35); font-size:0.75rem; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <h1>New Shades</h1>
    <p>Premium Salon &amp; Studio</p>
  </div>
  <div class="body">{content}</div>
  <div class="footer">&copy; 2026 New Shades. All rights reserved.</div>
</div>
</body>
</html>"""


def send_booking_received_email(to_email: str, customer_name: str,
                                appt_date: str, appt_time: str, services: str) -> bool:
    n = _html.escape(customer_name)
    d = _html.escape(str(appt_date))
    t = _html.escape(str(appt_time or 'Flexible'))
    s = _html.escape(str(services))
    content = f"""
<p>Hello <strong style="color:#e8c96a;">{n}</strong>,</p>
<p>We've received your appointment request — it is currently <strong style="color:#f5c842;">pending review</strong>. You'll receive another email once confirmed.</p>
<div class="detail-box">
  <div class="detail-row"><span class="detail-label">Date</span><span class="detail-val">{d}</span></div>
  <div class="detail-row"><span class="detail-label">Time</span><span class="detail-val">{t}</span></div>
  <div class="detail-row"><span class="detail-label">Services</span><span class="detail-val">{s}</span></div>
  <div class="detail-row"><span class="detail-label">Status</span><span class="detail-val" style="color:#f5c842;">Pending</span></div>
</div>
<p>Thank you for choosing New Shades! ✨</p>
"""
    return _send(to_email, 'Booking Received – New Shades', _base_html(content))


def send_confirmation_email(to_email: str, customer_name: str,
                            appt_date: str, appt_time: str, services: str) -> bool:
    n = _html.escape(customer_name)
    d = _html.escape(str(appt_date))
    t = _html.escape(str(appt_time or 'Flexible'))
    s = _html.escape(str(services))
    content = f"""
<p>Hello <strong style="color:#e8c96a;">{n}</strong>,</p>
<p>Your appointment has been <strong style="color:#7ce0aa;">confirmed</strong>. We look forward to seeing you!</p>
<div class="detail-box">
  <div class="detail-row"><span class="detail-label">Date</span><span class="detail-val">{d}</span></div>
  <div class="detail-row"><span class="detail-label">Time</span><span class="detail-val">{t}</span></div>
  <div class="detail-row"><span class="detail-label">Services</span><span class="detail-val">{s}</span></div>
</div>
<p>Your digital ticket is available in <em>My Appointments</em>. Please show it at the salon during check-in.</p>
<p>Thank you for choosing New Shades. See you soon! ✨</p>
"""
    return _send(to_email, 'Appointment Confirmed – New Shades', _base_html(content))


def send_rejection_email(to_email: str, customer_name: str,
                         appt_date: str, appt_time: str) -> bool:
    n = _html.escape(customer_name)
    d = _html.escape(str(appt_date))
    t = _html.escape(str(appt_time or 'Flexible'))
    content = f"""
<p>Hello <strong style="color:#e8c96a;">{n}</strong>,</p>
<p>We regret to inform you that your appointment request has been <strong style="color:#ff9a9a;">rejected</strong>.</p>
<div class="detail-box">
  <div class="detail-row"><span class="detail-label">Requested Date</span><span class="detail-val">{d}</span></div>
  <div class="detail-row"><span class="detail-label">Requested Time</span><span class="detail-val">{t}</span></div>
</div>
<p>Please log in and book another available appointment at your convenience.</p>
<p>We apologise for any inconvenience. Thank you.</p>
"""
    return _send(to_email, 'Appointment Update – New Shades', _base_html(content))


def send_admin_new_booking_email(to_email: str, customer_name: str, customer_phone: str,
                                 appt_date: str, appt_time: str, services: str) -> bool:
    n = _html.escape(customer_name)
    p = _html.escape(customer_phone)
    d = _html.escape(str(appt_date))
    t = _html.escape(str(appt_time or 'Flexible'))
    s = _html.escape(str(services))
    content = f"""
<p>A new appointment request is <strong style="color:#f5c842;">awaiting your review</strong>.</p>
<div class="detail-box">
  <div class="detail-row"><span class="detail-label">Customer</span><span class="detail-val">{n}</span></div>
  <div class="detail-row"><span class="detail-label">Phone</span><span class="detail-val">{p}</span></div>
  <div class="detail-row"><span class="detail-label">Services</span><span class="detail-val">{s}</span></div>
  <div class="detail-row"><span class="detail-label">Date</span><span class="detail-val">{d}</span></div>
  <div class="detail-row"><span class="detail-label">Time</span><span class="detail-val">{t}</span></div>
</div>
<p>Please log in to the <strong>Admin Dashboard</strong> to accept or reject this appointment.</p>
"""
    return _send(to_email, f'New Booking – {n}', _base_html(content))


def send_reschedule_email(to_email: str, customer_name: str,
                          new_date: str, new_time: str) -> bool:
    n = _html.escape(customer_name)
    d = _html.escape(str(new_date))
    t = _html.escape(str(new_time or 'Flexible'))
    content = f"""
<p>Hello <strong style="color:#e8c96a;">{n}</strong>,</p>
<p>Your appointment has been <strong style="color:#9dc0ff;">rescheduled</strong> by our team.</p>
<div class="detail-box">
  <div class="detail-row"><span class="detail-label">New Date</span><span class="detail-val">{d}</span></div>
  <div class="detail-row"><span class="detail-label">New Time</span><span class="detail-val">{t}</span></div>
</div>
<p>Please log in to view your updated appointment details and ticket.</p>
<p>We apologise for any inconvenience. Thank you for choosing New Shades!</p>
"""
    return _send(to_email, 'Appointment Rescheduled – New Shades', _base_html(content))
