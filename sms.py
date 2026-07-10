from flask import current_app
import logging

def send_sms(to, body):
    """Send SMS via Twilio. Silently logs if credentials are not configured."""
    cfg = current_app.config
    sid   = cfg.get('TWILIO_ACCOUNT_SID', '')
    token = cfg.get('TWILIO_AUTH_TOKEN', '')
    from_ = cfg.get('TWILIO_FROM', '')

    if not sid or not token or not from_ or sid.startswith('your_'):
        current_app.logger.info('[SMS SKIPPED] To: %s | %s', to, body[:80])
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
    body = (
        f"New Appointment Request\n\n"
        f"Customer Name: {customer_name}\n"
        f"Phone Number: {customer_phone}\n"
        f"Appointment Date: {appt_date}\n"
        f"Appointment Time: {appt_time or 'Flexible'}\n\n"
        f"Please log in to the Admin Dashboard to Accept or Reject."
    )
    send_sms(admin_phone, body)


def sms_confirmed(customer_phone, customer_name, appt_date, appt_time):
    body = (
        f"Hello {customer_name},\n\n"
        f"Your appointment has been confirmed.\n"
        f"Date: {appt_date}\n"
        f"Time: {appt_time or 'Flexible'}\n\n"
        f"Your digital ticket is now available in your account.\n"
        f"Please show your ticket at the salon during check-in.\n\n"
        f"Thank you for choosing New Shades."
    )
    send_sms(customer_phone, body)


def sms_rejected(customer_phone, customer_name, appt_date, appt_time):
    body = (
        f"Hello {customer_name},\n\n"
        f"Your appointment request for {appt_date} at {appt_time or 'Flexible'} has been rejected.\n\n"
        f"Please log in to the website and book another available appointment.\n\n"
        f"Thank you."
    )
    send_sms(customer_phone, body)
