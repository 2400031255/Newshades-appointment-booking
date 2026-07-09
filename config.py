import os
import secrets
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)

    # PostgreSQL (Render) — takes priority if set
    DATABASE_URL = os.environ.get('DATABASE_URL', '')

    # MySQL fallback (local dev)
    MYSQL_HOST     = os.environ.get('MYSQL_HOST', 'localhost')
    MYSQL_USER     = os.environ.get('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
    MYSQL_DB       = os.environ.get('MYSQL_DB', 'salon_db')

    WHATSAPP_NUMBER = os.environ.get('WHATSAPP_NUMBER', '')
    ADMIN_EMAIL     = os.environ.get('ADMIN_EMAIL', 'komali@salon.com')

    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_COOKIE_HTTPONLY    = True
    SESSION_COOKIE_SAMESITE    = 'Lax'
    SESSION_COOKIE_SECURE      = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() in ('1', 'true', 'yes')
