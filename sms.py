from flask import current_app
import re


def _sanitize(text, max_len=100):
    """Strip control characters and limit length for SMS body safety."""
    if not text:
        return ''
    text = re.sub(r'[\x00-\x1f\x7f]', '', str(text))
    return text[:max_len]


def _valid_phone(number):
    """Basic E.164-ish check — digits only, 7–15 chars."""
    if not number:
        return False
    digits = re.sub(r'[\s\+\-\(\)]', '', str(number))
    return digits.isdigit() and 7 <= len(digits) <= 15


def send_sms(to, body):
    """Send SMS via Twilio. Silently logs if credentials are not configured."""
    cfg   = current_app.config
    sid   = cfg.get('TWILIO_ACCOUNT_SID', '')
    token = cfg.get('TWILIO_AUTH_TOKEN', '')
    from_ = cfg.get('TWILIO_FROM', '')

    if not sid or not token or not from_ or sid.startswith('your_'):
        current_app.logger.info('[SMS SKIPPED] To: %s | %s', to, body[:80])
        return False

    if not _valid_phone(to):
        current_app.logger.warning('[SMS SKIPPED] Invalid phone: %s', to)
        return False

    try:
        from twilio.rest import Client
        client = Client(sid, token)
        client.messages.create(body=body, from_=from_, to=to)
        return True
    except Exception as e:
        current_app.logger.error('[SMS ERROR] %s', e)
        return False


def sms_new_booking(admin_phone, customer_name, customer_phone, appt_date, appt_time):
    name  = _sanitize(customer_name)
    phone = _sanitize(customer_phone, 20)
    date  = _sanitize(appt_date, 30)
    time  = _sanitize(appt_time or 'Flexible', 20)
    body  = (
        f"New Appointment Request\n\n"
        f"Customer: {name}\n"
        f"Phone: {phone}\n"
        f"Date: {date}\n"
        f"Time: {time}\n\n"
        f"Log in to Admin Dashboard to Accept or Reject."
    )
    send_sms(admin_phone, body)


def sms_confirmed(customer_phone, customer_name, appt_date, appt_time):
    name = _sanitize(customer_name)
    date = _sanitize(appt_date, 30)
    time = _sanitize(appt_time or 'Flexible', 20)
    body = (
        f"Hello {name},\n\n"
        f"Your appointment has been confirmed.\n"
        f"Date: {date}\n"
        f"Time: {time}\n\n"
        f"Show your digital ticket at the salon during check-in.\n\n"
        f"Thank you for choosing New Shades."
    )
    send_sms(customer_phone, body)


def sms_rejected(customer_phone, customer_name, appt_date, appt_time):
    name = _sanitize(customer_name)
    date = _sanitize(appt_date, 30)
    time = _sanitize(appt_time or 'Flexible', 20)
    body = (
        f"Hello {name},\n\n"
        f"Your appointment request for {date} at {time} has been rejected.\n\n"
        f"Please log in and book another available appointment.\n\n"
        f"Thank you."
    )
    send_sms(customer_phone, body)
