import os
import secrets
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Secret key — must be set via env in production
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)

    # Database
    DATABASE_URL   = os.environ.get('DATABASE_URL', '')
    MYSQL_HOST     = os.environ.get('MYSQL_HOST', 'localhost')
    MYSQL_USER     = os.environ.get('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
    MYSQL_DB       = os.environ.get('MYSQL_DB', 'salon_db')

    # SMS — Twilio
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', '')
    TWILIO_AUTH_TOKEN  = os.environ.get('TWILIO_AUTH_TOKEN', '')
    TWILIO_FROM        = os.environ.get('TWILIO_FROM', '')
    ADMIN_PHONE        = os.environ.get('ADMIN_PHONE', '')
    ADMIN_EMAIL        = os.environ.get('ADMIN_EMAIL', '')

    # Email — Resend
    RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '')
    EMAIL_FROM     = os.environ.get('EMAIL_FROM', 'New Shades <noreply@yourdomain.com>')

    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_COOKIE_HTTPONLY    = True
    SESSION_COOKIE_SAMESITE    = 'Lax'
    SESSION_COOKIE_SECURE      = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() in ('1', 'true', 'yes')
    SESSION_COOKIE_NAME        = '__Host-session' if os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() in ('1', 'true', 'yes') else 'session'

    # Limit upload size to 16 MB total per request
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
