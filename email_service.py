import logging
import html
from flask import current_app

logger = logging.getLogger(__name__)


def _send(to_email: str, subject: str, html: str) -> bool:
    """Send an email via Resend. Returns True on success, False on failure."""
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
            'html':    html,
        })
        logger.info('[EMAIL SENT] To: %s | Subject: %s', to_email, subject)
        return True
    except Exception as e:
        logger.error('[EMAIL ERROR] To: %s | %s', to_email, e)
        return False


def _base_html(content: str) -> str:
    """Wrap content in a branded HTML email shell."""
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
  .btn {{ display:inline-block; margin-top:8px; padding:12px 28px; border-radius:999px; background:linear-gradient(135deg,#e8c96a,#c9a84c); color:#120e08; font-weight:700; text-decoration:none; font-size:0.92rem; }}
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
  <div class="footer">© 2026 New Shades. All rights reserved.</div>
</div>
</body>
</html>"""


def send_confirmation_email(to_email: str, customer_name: str,
                             appt_date: str, appt_time: str, services: str) -> bool:
    time_display = appt_time or 'Flexible'
    n = html.escape(customer_name)
    d = html.escape(str(appt_date))
    t = html.escape(str(time_display))
    s = html.escape(str(services))
    content = f"""
<p>Hello <strong style="color:#e8c96a;">{n}</strong>,</p>
<p>Your appointment has been <strong style="color:#7ce0aa;">confirmed</strong>. We look forward to seeing you!</p>
<div class="detail-box">
  <div class="detail-row"><span class="detail-label">📅 Date</span><span class="detail-val">{d}</span></div>
  <div class="detail-row"><span class="detail-label">🕐 Time</span><span class="detail-val">{t}</span></div>
  <div class="detail-row"><span class="detail-label">✂️ Services</span><span class="detail-val">{s}</span></div>
</div>
<p>Your <strong>digital appointment ticket</strong> is now available in your <em>My Appointments</em> section.</p>
<p>Please log in to the website and show your digital ticket at the salon during check-in.</p>
<p>Thank you for choosing New Shades. See you soon! ✨</p>
"""
    return _send(to_email, 'Appointment Confirmed – New Shades', _base_html(content))


def send_rejection_email(to_email: str, customer_name: str,
                          appt_date: str, appt_time: str) -> bool:
    time_display = appt_time or 'Flexible'
    n = html.escape(customer_name)
    d = html.escape(str(appt_date))
    t = html.escape(str(time_display))
    content = f"""
<p>Hello <strong style="color:#e8c96a;">{n}</strong>,</p>
<p>We regret to inform you that your appointment request has been <strong style="color:#ff9a9a;">rejected</strong>.</p>
<div class="detail-box">
  <div class="detail-row"><span class="detail-label">📅 Requested Date</span><span class="detail-val">{d}</span></div>
  <div class="detail-row"><span class="detail-label">🕐 Requested Time</span><span class="detail-val">{t}</span></div>
</div>
<p>Please log in to the website and book another available appointment at your convenience.</p>
<p>We apologise for any inconvenience and hope to serve you soon.</p>
<p>Thank you.</p>
"""
    return _send(to_email, 'Appointment Update – New Shades', _base_html(content))
