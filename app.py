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
        if request.path.startswith('/static/'):
            response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        elif request.method == 'GET' and response.status_code == 200:
            response.headers['Cache-Control'] = 'no-cache, must-revalidate'
        return response

    @app.before_request
    def make_session_permanent():
        session.permanent = True

    @app.before_request
    def check_maintenance():
        if not request.endpoint:
            return
        allowed_endpoints = {'auth.login', 'auth.login_post', 'auth.logout', 'static', 'ping',
                              'employee.login', 'employee.login_post', 'employee.logout'}
        if request.endpoint in allowed_endpoints:
            return
        if session.get('is_admin'):
            return
        if os.environ.get('MAINTENANCE_OVERRIDE') == 'off':
            return
        try:
            import db
            if db.get_setting('maintenance_mode', '0') == '1':
                if session.get('user_id'):
                    session.clear()
                wa = db.get_setting('whatsapp_number', '')
                return render_template('maintenance.html', whatsapp=wa), 503
        except (OSError, RuntimeError):
            pass

    app.teardown_appcontext(close_db)

    @app.context_processor
    def inject_shop():
        import db
        import datetime as _dt

        try:
            settings_map = db.get_all_settings()
        except (OSError, RuntimeError):
            settings_map = {}

        def gs(key, default=''):
            return settings_map.get(key, default)

        pending_appts = 0
        if session.get('is_admin'):
            try:
                enqs = db.get_all_enquiries(status_filter='Pending')
                pending_appts = len(enqs)
            except (OSError, RuntimeError) as e:
                current_app.logger.warning('pending_appts failed: %s', e)

        today_offers = []
        endpoint = request.endpoint or ''
        if not endpoint.startswith('admin.') and endpoint != 'static':
            try:
                today_offers = db.get_active_offers(_dt.date.today().isoformat())
            except (OSError, RuntimeError) as e:
                current_app.logger.warning('today_offers failed: %s', e)

        return dict(
            pending_appts=pending_appts,
            today_offers=today_offers,
            now_date=_dt.date.today().isoformat(),
            asset_v=current_app.config.get('APP_VERSION', '1'),
            shop={
                'name':           gs('shop_name', 'New Shades'),
                'tagline':        gs('shop_tagline', 'Premium Salon & Studio'),
                'phone':          gs('shop_phone', ''),
                'email':          gs('shop_email', ''),
                'whatsapp':       gs('whatsapp_number', ''),
                'address':        gs('shop_address', ''),
                'hours_weekday':  gs('shop_hours_weekday', ''),
                'hours_saturday': gs('shop_hours_saturday', ''),
                'hours_sunday':   gs('shop_hours_sunday', ''),
                'map_embed':      gs('map_embed', ''),
            })

    from routes.auth import auth
    from routes.customer import customer
    from routes.admin import admin
    from routes.employee import employee_bp
    from routes.calendar_api import cal_api
    app.register_blueprint(auth)
    app.register_blueprint(customer)
    app.register_blueprint(admin)
    app.register_blueprint(employee_bp)
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
            path = os.path.join(app.root_path, 'templates', 'errors', '500.html')
            with open(path, 'r') as f:
                return f.read(), 500
        except Exception:
            return '<h1 style="color:#fff;background:#0c0b10;text-align:center;padding:80px;font-family:serif;">500 – Server Error</h1>', 500

    @app.errorhandler(503)
    def service_unavailable(e):
        try:
            path = os.path.join(app.root_path, 'templates', 'errors', '500.html')
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
        import db
        try:
            reviews = db.get_recent_reviews(limit=6)
        except Exception:
            reviews = []
        try:
            services = db.get_all_services(active_only=True)[:6]
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
        import db
        try:
            svcs = db.get_all_services(active_only=True)
            categories = list(dict.fromkeys(s['category'] for s in svcs))
        except (OSError, RuntimeError):
            svcs, categories = [], []
        return render_template('services.html', services=svcs, categories=categories)

    @app.route('/gallery')
    def gallery():
        import db
        try:
            photos = db.get_all_gallery()
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
