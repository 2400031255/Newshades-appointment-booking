from flask import Flask, render_template, session, redirect, url_for, request, current_app
from flask_socketio import SocketIO, emit
from flask_wtf.csrf import CSRFProtect
from config import Config
from db import close_db
import os
import logging
from datetime import timezone

socketio = SocketIO()
csrf = CSRFProtect()
logger = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.permanent_session_lifetime = app.config['PERMANENT_SESSION_LIFETIME']
    app.config['WTF_CSRF_ENABLED'] = True

    try:
        import gevent  # noqa
        _async_mode = 'gevent'
    except ImportError:
        _async_mode = 'threading'

    socketio.init_app(app, cors_allowed_origins=app.config.get('CORS_ORIGINS', 'http://localhost:5000'),
                      async_mode=_async_mode,
                      logger=False, engineio_logger=False, manage_session=False)
    csrf.init_app(app)

    @app.after_request
    def set_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options']         = 'SAMEORIGIN'
        response.headers['X-XSS-Protection']        = '1; mode=block'
        response.headers['Referrer-Policy']          = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy']       = 'geolocation=(), microphone=(), camera=()'
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com "
            "https://cdn.socket.io https://unpkg.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com "
            "https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
            "img-src 'self' data: blob:; "
            "connect-src 'self' wss: ws:; "
            "frame-ancestors 'self';"
        )
        return response

    @app.before_request
    def make_session_permanent():
        session.permanent = True

    @app.before_request
    def check_maintenance():
        from db import query
        if not request.endpoint:
            return
        allowed_endpoints = {'auth.login', 'auth.login_post', 'auth.logout', 'static', 'ping'}
        if request.endpoint in allowed_endpoints:
            return
        if session.get('is_admin'):
            return
        # Allow env override to force maintenance OFF (useful for Render cold starts)
        if os.environ.get('MAINTENANCE_OVERRIDE') == 'off':
            return
        try:
            row = query("SELECT value FROM settings WHERE `key`='maintenance_mode'", one=True)
            if row and row['value'] == '1':
                if session.get('user_id'):
                    session.clear()
                wa = query("SELECT value FROM settings WHERE `key`='whatsapp_number'", one=True)
                return render_template('maintenance.html',
                    whatsapp=wa['value'] if wa else ''), 503
        except (OSError, RuntimeError):
            pass

    app.teardown_appcontext(close_db)

    @app.context_processor
    def inject_shop():
        from db import query
        def get_setting(key, default=''):
            try:
                row = query("SELECT value FROM settings WHERE `key`=%s", (key,), one=True)
                return row['value'] if row else default
            except (OSError, RuntimeError) as e:
                current_app.logger.warning('get_setting(%s) failed: %s', key, e)
                return default

        pending_appts = 0
        if session.get('is_admin'):
            try:
                r = query("SELECT COUNT(*) as c FROM appointments WHERE status='Pending'", one=True)
                pending_appts = r['c'] if r else 0
            except (OSError, RuntimeError) as e:
                current_app.logger.warning('pending_appts query failed: %s', e)

        today_offers = []
        try:
            from datetime import date
            today = date.today().isoformat()
            today_offers = query(
                "SELECT * FROM offers WHERE is_active=1 "
                "AND (valid_from IS NULL OR valid_from <= %s) "
                "AND (valid_until IS NULL OR valid_until >= %s)",
                (today, today)
            )
        except (OSError, RuntimeError) as e:
            current_app.logger.warning('today_offers query failed: %s', e)

        import datetime as _dt
        return dict(
            pending_appts=pending_appts,
            today_offers=today_offers,
            now_date=_dt.date.today().isoformat(),
            asset_v=current_app.config.get('APP_VERSION', '1'),
            shop={
                'name':           get_setting('shop_name', 'New Shades'),
                'tagline':        get_setting('shop_tagline', 'Premium Salon & Studio'),
                'phone':          get_setting('shop_phone', ''),
                'email':          get_setting('shop_email', ''),
                'whatsapp':       get_setting('whatsapp_number', ''),
                'address':        get_setting('shop_address', ''),
                'hours_weekday':  get_setting('shop_hours_weekday', ''),
                'hours_saturday': get_setting('shop_hours_saturday', ''),
                'hours_sunday':   get_setting('shop_hours_sunday', ''),
                'map_embed':      get_setting('map_embed', ''),
            })

    from routes.auth import auth
    from routes.customer import customer
    from routes.admin import admin
    from routes.calendar_api import cal_api
    app.register_blueprint(auth)
    app.register_blueprint(customer)
    app.register_blueprint(admin)
    app.register_blueprint(cal_api)
    try:
        from flask_wtf.csrf import exempt as csrf_exempt
        csrf_exempt(cal_api)
    except ImportError:
        pass
    csrf.exempt(cal_api)

    @app.route('/ping')
    def ping():
        return 'ok', 200

    @app.errorhandler(404)
    def not_found(e):
        try:
            return render_template('errors/404.html'), 404
        except Exception:
            return '<h1 style="color:#fff;background:#0c0b10;text-align:center;padding:80px;font-family:serif;">404 – Page Not Found</h1>', 404

    @app.errorhandler(413)
    def request_too_large(e):
        try:
            return render_template('errors/404.html'), 413
        except Exception:
            return '<h1 style="color:#fff;background:#0c0b10;text-align:center;padding:80px;font-family:serif;">413 – Request Too Large</h1>', 413

    @app.errorhandler(500)
    def server_error(e):
        try:
            import os as _os
            path = _os.path.join(app.root_path, 'templates', 'errors', '500.html')
            with open(path, 'r') as f:
                return f.read(), 500
        except Exception:
            return '<h1 style="color:#fff;background:#0c0b10;text-align:center;padding:80px;font-family:serif;">500 – Server Error</h1>', 500

    @app.errorhandler(503)
    def service_unavailable(e):
        try:
            import os as _os
            path = _os.path.join(app.root_path, 'templates', 'errors', '500.html')
            with open(path, 'r') as f:
                return f.read(), 503
        except Exception:
            return '<h1 style="color:#fff;background:#0c0b10;text-align:center;padding:80px;font-family:serif;">503 – Service Unavailable</h1>', 503

    @app.route('/')
    def index():
        if session.get('user_id'):
            if session.get('is_admin'):
                return redirect(url_for('admin.dashboard'))
            return redirect(url_for('customer.dashboard'))
        from db import query
        try:
            reviews = query(
                "SELECT r.rating, r.comment, r.created_at, u.full_name FROM reviews r "
                "JOIN users u ON r.user_id=u.id ORDER BY r.created_at DESC LIMIT 6"
            )
        except Exception:
            reviews = []
        try:
            services = query("SELECT * FROM services WHERE is_active=1 ORDER BY category, service_name LIMIT 6")
        except Exception:
            services = []
        return render_template('index.html', reviews=reviews, services=services)

    @app.route('/about')
    def about():
        return render_template('about.html')

    @app.route('/contact')
    def contact():
        return render_template('contact.html')

    @app.route('/services')
    def services():
        from db import query
        try:
            svcs = query("SELECT * FROM services WHERE is_active=1 ORDER BY category, service_name")
            categories = list(dict.fromkeys(s['category'] for s in svcs))
        except (OSError, RuntimeError):
            svcs, categories = [], []
        return render_template('services.html', services=svcs, categories=categories)

    @app.route('/gallery')
    def gallery():
        from db import query
        try:
            photos = query("SELECT * FROM gallery ORDER BY created_at DESC")
        except (OSError, RuntimeError):
            photos = []
        return render_template('gallery.html', photos=photos)

    @socketio.on('connect')
    def on_connect():
        emit('connected', {'status': 'ok'})

    @socketio.on('ping_calendar')
    def on_ping():
        import datetime as _dt
        emit('pong_calendar', {'ts': _dt.datetime.now(tz=timezone.utc).isoformat()})

    return app


if __name__ == '__main__':
    app = create_app()
    socketio.run(
        app,
        debug=os.environ.get('FLASK_DEBUG', 'false').lower() == 'true',
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000)),
        allow_unsafe_werkzeug=True
    )
